"""The AWS calls behind the AWS hosting targets (docs/CLOUD.md), one small method per operation.

Everything AWS goes through `AwsClient` so the deploy/teardown/domain logic in `cloud_deploy` can be
tested against a fake (`set_factory`); tests never reach AWS. Rules:

- credentials come from the decrypted connection config only (never the worker's environment or
  `~/.aws`), and are never logged or put in exception messages (`CloudError` carries AWS's own
  error code/message, which never contains the secret);
- every resource Deployer creates is named `deployer-...`, which is what the IAM policy the dashboard
  shows (`cloud.AWS_POLICY`) is scoped to.
"""

from __future__ import annotations

import base64
import functools
import json
import re
import time
from collections.abc import Callable
from typing import Any

from app.errors import CloudError

ACCESS_ROLE = "deployer-apprunner-ecr-access"  # shared by every App Runner service of the account
INSTANCE_ROLE_PREFIX = "deployer-app-"  # one instance role per App Runner app that uses DynamoDB tables
INSTANCE_ROLE_POLICY = "deployer-databases"
# docs/CLOUD.md "C3": GitHub Actions signs in with OpenID Connect and assumes one role per app.
GITHUB_OIDC_HOST = "token.actions.githubusercontent.com"
GITHUB_ROLE_PREFIX = "deployer-gha-"
GITHUB_ROLE_POLICY = "deployer-deploy"
ECR_ACCESS_POLICY = "arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess"
CACHING_OPTIMIZED = "658327ea-f89d-4fab-a63d-7e88639e58f6"  # AWS managed cache policy
CERT_REGION = "us-east-1"  # CloudFront only uses ACM certificates from us-east-1
CHECKIP_URL = "https://checkip.amazonaws.com"
# On every security group, RDS instance and VPC connector Deployer creates; the IAM policy only lets
# Deployer change security groups that carry it (cloud.AWS_POLICY).
TAG = {"Key": "managed-by", "Value": "deployer"}
# CloudFront Function (viewer request): `/docs/` and `/docs` -> `/docs/index.html` like nginx's
# `try_files $uri $uri/`; missing files fall back to /index.html through the 403/404 error responses.
INDEX_FUNCTION = """function handler(event) {
  var r = event.request;
  if (r.uri.endsWith('/')) { r.uri += 'index.html'; }
  else if (r.uri.split('/').pop().indexOf('.') === -1) { r.uri += '/index.html'; }
  return r;
}
"""

_factory: Callable[[dict], Any] | None = None


def client(config: dict) -> AwsClient:
    return (_factory or AwsClient)(config)


def set_factory(factory: Callable[[dict], Any] | None) -> None:
    """Test hook: `client(config)` returns `factory(config)` (None restores the real client)."""
    global _factory
    _factory = factory


def _code(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    return str(response.get("Error", {}).get("Code", "")) if isinstance(response, dict) else ""


def _wrap(fn):
    """botocore errors -> CloudError with AWS's code and message (no request data, no credentials)."""

    @functools.wraps(fn)
    def inner(*args, **kwargs):
        from botocore.exceptions import BotoCoreError, ClientError

        try:
            return fn(*args, **kwargs)
        except ClientError as exc:
            err = exc.response.get("Error", {})
            raise CloudError(f"AWS {err.get('Code') or 'error'}: {err.get('Message') or ''}", code=_code(exc)) from None
        except BotoCoreError as exc:
            raise CloudError(f"AWS could not be reached ({type(exc).__name__})") from None

    return inner


class AwsClient:
    def __init__(self, config: dict):
        import boto3
        from botocore.config import Config

        self.region = str(config["region"])
        self._config = Config(retries={"max_attempts": 5, "mode": "standard"}, connect_timeout=10, read_timeout=60)
        session = boto3.session.Session(
            aws_access_key_id=config["access_key_id"],
            aws_secret_access_key=config["secret_access_key"],
            region_name=self.region,
        )
        if config.get("role_arn"):
            creds = self._assume(session, config["role_arn"])
            session = boto3.session.Session(
                aws_access_key_id=creds["AccessKeyId"],
                aws_secret_access_key=creds["SecretAccessKey"],
                aws_session_token=creds["SessionToken"],
                region_name=self.region,
            )
        self._session = session

    def __repr__(self) -> str:
        return f"AwsClient(region={self.region!r}, <credentials hidden>)"

    @_wrap
    def _assume(self, session, role_arn: str) -> dict:
        sts = session.client("sts", config=self._config)
        return sts.assume_role(RoleArn=role_arn, RoleSessionName="deployer", DurationSeconds=3600)["Credentials"]

    def _c(self, service: str, region: str | None = None):
        return self._session.client(service, region_name=region or self.region, config=self._config)

    # --- identity ------------------------------------------------------------------------------

    @_wrap
    def identity(self) -> dict:
        out = self._c("sts").get_caller_identity()
        return {"account": out["Account"], "arn": out["Arn"]}

    # --- S3 ------------------------------------------------------------------------------------

    @_wrap
    def create_bucket(self, bucket: str) -> None:
        s3 = self._c("s3")
        kwargs = (
            {} if self.region == "us-east-1" else {"CreateBucketConfiguration": {"LocationConstraint": self.region}}
        )
        try:
            s3.create_bucket(Bucket=bucket, **kwargs)
        except Exception as exc:  # noqa: BLE001 - re-raised unless it is our own bucket already
            if _code(exc) != "BucketAlreadyOwnedByYou":
                raise
        s3.put_public_access_block(
            Bucket=bucket,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": True,
                "IgnorePublicAcls": True,
                "BlockPublicPolicy": True,
                "RestrictPublicBuckets": True,
            },
        )

    @_wrap
    def upload_file(self, bucket: str, key: str, path: str, content_type: str, cache_control: str) -> None:
        self._c("s3").upload_file(
            path, bucket, key, ExtraArgs={"ContentType": content_type, "CacheControl": cache_control}
        )

    @_wrap
    def delete_prefix(self, bucket: str, prefix: str) -> int:
        """Deletes every object under `prefix` ("" = the whole bucket). Returns the count."""
        s3 = self._c("s3")
        count = 0
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
            keys = [{"Key": o["Key"]} for o in page.get("Contents") or []]
            if keys:
                s3.delete_objects(Bucket=bucket, Delete={"Objects": keys, "Quiet": True})
                count += len(keys)
        return count

    def delete_bucket(self, bucket: str) -> None:
        try:
            self.delete_prefix(bucket, "")
            self._delete_empty_bucket(bucket)
        except CloudError as exc:
            if exc.code != "NoSuchBucket":
                raise

    @_wrap
    def _delete_empty_bucket(self, bucket: str) -> None:
        self._c("s3").delete_bucket(Bucket=bucket)

    @_wrap
    def allow_distribution(self, bucket: str, distribution_arn: str) -> None:
        """Bucket policy: only this CloudFront distribution (through its OAC) may read objects."""
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "CloudFrontRead",
                    "Effect": "Allow",
                    "Principal": {"Service": "cloudfront.amazonaws.com"},
                    "Action": "s3:GetObject",
                    "Resource": f"arn:aws:s3:::{bucket}/*",
                    "Condition": {"StringEquals": {"AWS:SourceArn": distribution_arn}},
                }
            ],
        }
        self._c("s3").put_bucket_policy(Bucket=bucket, Policy=json.dumps(policy))

    # --- CloudFront ------------------------------------------------------------------------------

    def _cf(self):
        return self._c("cloudfront", "us-east-1")

    @_wrap
    def create_oac(self, name: str) -> str:
        out = self._cf().create_origin_access_control(
            OriginAccessControlConfig={
                "Name": name,
                "Description": "Deployer static site",
                "SigningProtocol": "sigv4",
                "SigningBehavior": "always",
                "OriginAccessControlOriginType": "s3",
            }
        )
        return out["OriginAccessControl"]["Id"]

    @_wrap
    def create_index_function(self, name: str) -> str:
        cf = self._cf()
        out = cf.create_function(
            Name=name,
            FunctionConfig={"Comment": "Deployer: directory index", "Runtime": "cloudfront-js-2.0"},
            FunctionCode=INDEX_FUNCTION.encode("utf-8"),
        )
        published = cf.publish_function(Name=name, IfMatch=out["ETag"])
        return published["FunctionSummary"]["FunctionMetadata"]["FunctionARN"]

    @_wrap
    def create_distribution(self, bucket: str, origin_path: str, oac_id: str, function_arn: str, comment: str) -> dict:
        both = {"Quantity": 2, "Items": ["GET", "HEAD"]}
        errors = [
            {"ErrorCode": code, "ResponsePagePath": "/index.html", "ResponseCode": "200", "ErrorCachingMinTTL": 10}
            for code in (403, 404)
        ]
        config = {
            "CallerReference": f"{bucket}-{time.time_ns()}",
            "Comment": comment[:128],
            "Enabled": True,
            "DefaultRootObject": "index.html",
            "PriceClass": "PriceClass_100",
            "HttpVersion": "http2and3",
            "IsIPV6Enabled": True,
            "Origins": {
                "Quantity": 1,
                "Items": [
                    {
                        "Id": "s3",
                        "DomainName": f"{bucket}.s3.{self.region}.amazonaws.com",
                        "OriginPath": origin_path,
                        "S3OriginConfig": {"OriginAccessIdentity": ""},
                        "OriginAccessControlId": oac_id,
                    }
                ],
            },
            "DefaultCacheBehavior": {
                "TargetOriginId": "s3",
                "ViewerProtocolPolicy": "redirect-to-https",
                "CachePolicyId": CACHING_OPTIMIZED,
                "Compress": True,
                "AllowedMethods": {**both, "CachedMethods": both},
                "FunctionAssociations": {
                    "Quantity": 1,
                    "Items": [{"FunctionARN": function_arn, "EventType": "viewer-request"}],
                },
            },
            "CustomErrorResponses": {"Quantity": len(errors), "Items": errors},
        }
        dist = self._cf().create_distribution(DistributionConfig=config)["Distribution"]
        return {"id": dist["Id"], "domain": dist["DomainName"], "arn": dist["ARN"]}

    def _update_distribution(self, distribution_id: str, change: Callable[[dict], None]) -> None:
        cf = self._cf()
        out = cf.get_distribution_config(Id=distribution_id)
        config = out["DistributionConfig"]
        change(config)
        cf.update_distribution(Id=distribution_id, IfMatch=out["ETag"], DistributionConfig=config)

    @_wrap
    def set_origin_path(self, distribution_id: str, origin_path: str) -> None:
        def change(config: dict) -> None:
            config["Origins"]["Items"][0]["OriginPath"] = origin_path

        self._update_distribution(distribution_id, change)

    @_wrap
    def set_aliases(self, distribution_id: str, aliases: list[str], certificate_arn: str | None) -> None:
        def change(config: dict) -> None:
            config["Aliases"] = {"Quantity": len(aliases), "Items": aliases} if aliases else {"Quantity": 0}
            config["ViewerCertificate"] = (
                {
                    "ACMCertificateArn": certificate_arn,
                    "SSLSupportMethod": "sni-only",
                    "MinimumProtocolVersion": "TLSv1.2_2021",
                }
                if certificate_arn
                else {"CloudFrontDefaultCertificate": True}
            )

        self._update_distribution(distribution_id, change)

    @_wrap
    def invalidate(self, distribution_id: str) -> str:
        out = self._cf().create_invalidation(
            DistributionId=distribution_id,
            InvalidationBatch={"Paths": {"Quantity": 1, "Items": ["/*"]}, "CallerReference": str(time.time_ns())},
        )
        return out["Invalidation"]["Id"]

    @_wrap
    def delete_distribution(self, distribution_id: str) -> None:
        """Disables the distribution, waits until CloudFront has rolled that out (up to 30 min), deletes."""
        cf = self._cf()
        try:
            out = cf.get_distribution_config(Id=distribution_id)
        except Exception as exc:  # noqa: BLE001
            if _code(exc) == "NoSuchDistribution":
                return
            raise
        config = out["DistributionConfig"]
        if config["Enabled"]:
            config["Enabled"] = False
            cf.update_distribution(Id=distribution_id, IfMatch=out["ETag"], DistributionConfig=config)
        cf.get_waiter("distribution_deployed").wait(Id=distribution_id, WaiterConfig={"Delay": 30, "MaxAttempts": 60})
        etag = cf.get_distribution_config(Id=distribution_id)["ETag"]
        cf.delete_distribution(Id=distribution_id, IfMatch=etag)

    @_wrap
    def delete_oac(self, oac_id: str) -> None:
        cf = self._cf()
        try:
            etag = cf.get_origin_access_control(Id=oac_id)["ETag"]
            cf.delete_origin_access_control(Id=oac_id, IfMatch=etag)
        except Exception as exc:  # noqa: BLE001
            if _code(exc) != "NoSuchOriginAccessControl":
                raise

    @_wrap
    def delete_function(self, name: str) -> None:
        cf = self._cf()
        try:
            etag = cf.describe_function(Name=name)["ETag"]
            cf.delete_function(Name=name, IfMatch=etag)
        except Exception as exc:  # noqa: BLE001
            if _code(exc) != "NoSuchFunctionExists":
                raise

    # --- ACM (us-east-1, for CloudFront) ---------------------------------------------------------

    @_wrap
    def request_certificate(self, hostname: str) -> str:
        token = re.sub(r"[^A-Za-z0-9]", "", hostname)[:32] or "deployer"
        out = self._c("acm", CERT_REGION).request_certificate(
            DomainName=hostname, ValidationMethod="DNS", IdempotencyToken=token
        )
        return out["CertificateArn"]

    @_wrap
    def certificate(self, arn: str) -> dict:
        """`{status, records: [{type, name, value}]}` (records appear a few seconds after the request)."""
        cert = self._c("acm", CERT_REGION).describe_certificate(CertificateArn=arn)["Certificate"]
        records = []
        for option in cert.get("DomainValidationOptions") or []:
            rr = option.get("ResourceRecord")
            if rr:
                records.append({"type": rr["Type"], "name": rr["Name"].rstrip("."), "value": rr["Value"].rstrip(".")})
        return {"status": cert.get("Status"), "records": records}

    @_wrap
    def delete_certificate(self, arn: str) -> None:
        try:
            self._c("acm", CERT_REGION).delete_certificate(CertificateArn=arn)
        except Exception as exc:  # noqa: BLE001
            if _code(exc) != "ResourceNotFoundException":
                raise

    # --- ECR -------------------------------------------------------------------------------------

    @_wrap
    def ensure_repository(self, name: str) -> str:
        ecr = self._c("ecr")
        try:
            repo = ecr.create_repository(repositoryName=name)["repository"]
        except Exception as exc:  # noqa: BLE001
            if _code(exc) != "RepositoryAlreadyExistsException":
                raise
            repo = ecr.describe_repositories(repositoryNames=[name])["repositories"][0]
        return repo["repositoryUri"]

    @_wrap
    def registry_login(self) -> tuple[str, str, str]:
        """(registry host, username, password) for `docker login --password-stdin`."""
        data = self._c("ecr").get_authorization_token()["authorizationData"][0]
        user, _, password = base64.b64decode(data["authorizationToken"]).decode("utf-8").partition(":")
        return data["proxyEndpoint"].removeprefix("https://"), user, password

    @_wrap
    def delete_images(self, name: str, tags: list[str]) -> None:
        if tags:
            self._c("ecr").batch_delete_image(repositoryName=name, imageIds=[{"imageTag": t} for t in tags])

    @_wrap
    def delete_repository(self, name: str) -> None:
        try:
            self._c("ecr").delete_repository(repositoryName=name, force=True)
        except Exception as exc:  # noqa: BLE001
            if _code(exc) != "RepositoryNotFoundException":
                raise

    # --- IAM: the role App Runner pulls images from ECR with --------------------------------------

    @_wrap
    def ensure_access_role(self) -> str:
        iam = self._c("iam")
        try:
            return iam.get_role(RoleName=ACCESS_ROLE)["Role"]["Arn"]
        except Exception as exc:  # noqa: BLE001
            if _code(exc) != "NoSuchEntity":
                raise
        trust = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "build.apprunner.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ],
        }
        arn = iam.create_role(
            RoleName=ACCESS_ROLE,
            AssumeRolePolicyDocument=json.dumps(trust),
            Description="Lets App Runner pull images Deployer pushed to ECR",
        )["Role"]["Arn"]
        iam.attach_role_policy(RoleName=ACCESS_ROLE, PolicyArn=ECR_ACCESS_POLICY)
        return arn

    # --- App Runner ------------------------------------------------------------------------------

    @staticmethod
    def _source(image: str, port: int, env: dict[str, str], role_arn: str) -> dict:
        image_config: dict[str, Any] = {"Port": str(port)}
        if env:
            image_config["RuntimeEnvironmentVariables"] = env
        return {
            "ImageRepository": {
                "ImageIdentifier": image,
                "ImageRepositoryType": "ECR",
                "ImageConfiguration": image_config,
            },
            "AutoDeploymentsEnabled": False,
            "AuthenticationConfiguration": {"AccessRoleArn": role_arn},
        }

    @staticmethod
    def _instance(role_arn: str | None) -> dict:
        out = {"Cpu": "0.25 vCPU", "Memory": "0.5 GB"}
        return {**out, "InstanceRoleArn": role_arn} if role_arn else out

    @staticmethod
    def _network(connector_arn: str | None) -> dict:
        """Egress through the VPC connector when the app uses a cloud database, else App Runner's default."""
        egress = {"EgressType": "VPC", "VpcConnectorArn": connector_arn} if connector_arn else {"EgressType": "DEFAULT"}
        return {"EgressConfiguration": egress}

    @_wrap
    def create_service(
        self,
        name: str,
        image: str,
        port: int,
        env: dict[str, str],
        role_arn: str,
        connector_arn: str | None = None,
        instance_role_arn: str | None = None,
    ) -> dict:
        ar = self._c("apprunner")
        for attempt in range(6):
            try:
                out = ar.create_service(
                    ServiceName=name,
                    SourceConfiguration=self._source(image, port, env, role_arn),
                    InstanceConfiguration=self._instance(instance_role_arn),
                    NetworkConfiguration=self._network(connector_arn),
                )
                break
            except Exception as exc:  # noqa: BLE001
                # A role created seconds ago is not assumable yet (IAM is eventually consistent).
                if _code(exc) != "InvalidRequestException" or attempt == 5:
                    raise
                time.sleep(10)
        service = out["Service"]
        return {
            "arn": service["ServiceArn"],
            "url": f"https://{service['ServiceUrl']}",
            "operation_id": out["OperationId"],
        }

    @_wrap
    def update_service(
        self,
        arn: str,
        image: str,
        port: int,
        env: dict[str, str],
        role_arn: str,
        connector_arn: str | None = None,
        instance_role_arn: str | None = None,
    ) -> str:
        out = self._c("apprunner").update_service(
            ServiceArn=arn,
            SourceConfiguration=self._source(image, port, env, role_arn),
            InstanceConfiguration=self._instance(instance_role_arn),
            NetworkConfiguration=self._network(connector_arn),
        )
        return out["OperationId"]

    @_wrap
    def operation(self, arn: str, operation_id: str) -> str:
        """PENDING | IN_PROGRESS | SUCCEEDED | FAILED | ROLLBACK_IN_PROGRESS | ROLLBACK_SUCCEEDED | ROLLBACK_FAILED"""
        ops = self._c("apprunner").list_operations(ServiceArn=arn, MaxResults=20)["OperationSummaryList"]
        return next((o["Status"] for o in ops if o["Id"] == operation_id), "PENDING")

    @_wrap
    def delete_service(self, arn: str) -> None:
        try:
            self._c("apprunner").delete_service(ServiceArn=arn)
        except Exception as exc:  # noqa: BLE001
            if _code(exc) != "ResourceNotFoundException":
                raise

    @_wrap
    def associate_domain(self, arn: str, hostname: str) -> str:
        """Returns the DNS target the hostname's CNAME must point at."""
        out = self._c("apprunner").associate_custom_domain(
            ServiceArn=arn, DomainName=hostname, EnableWWWSubdomain=False
        )
        return out["DNSTarget"]

    @_wrap
    def domain_status(self, arn: str, hostname: str) -> dict:
        """`{status, target, records}`; status `active` once App Runner validated the certificate."""
        out = self._c("apprunner").describe_custom_domains(ServiceArn=arn)
        domain = next((d for d in out.get("CustomDomains") or [] if d["DomainName"] == hostname), None)
        if domain is None:
            return {"status": "missing", "target": out.get("DNSTarget"), "records": []}
        records = [
            {"type": r["Type"], "name": r["Name"].rstrip("."), "value": r["Value"].rstrip(".")}
            for r in domain.get("CertificateValidationRecords") or []
        ]
        return {"status": domain.get("Status"), "target": out.get("DNSTarget"), "records": records}

    @_wrap
    def disassociate_domain(self, arn: str, hostname: str) -> None:
        try:
            self._c("apprunner").disassociate_custom_domain(ServiceArn=arn, DomainName=hostname)
        except Exception as exc:  # noqa: BLE001
            if _code(exc) not in ("ResourceNotFoundException", "InvalidRequestException"):
                raise

    # --- RDS + the firewall around it (cloud databases, docs/CLOUD.md "C2") ---------------------------

    def public_ip(self) -> str:
        """This PC's public IPv4 address as AWS sees it (AWS's own checkip service, no credentials)."""
        import ipaddress

        import httpx

        try:
            resp = httpx.get(CHECKIP_URL, timeout=10)
            resp.raise_for_status()
            return str(ipaddress.IPv4Address(resp.text.strip()))
        except (httpx.HTTPError, ValueError):
            raise CloudError("Could not find this PC's public IP address (checkip.amazonaws.com)") from None

    @_wrap
    def db_resources(self) -> list[dict]:
        """RDS instances (not part of a cluster) and Aurora / RDS clusters of the region."""
        rds = self._c("rds")
        instances = [i for page in rds.get_paginator("describe_db_instances").paginate() for i in page["DBInstances"]]
        clusters = [c for page in rds.get_paginator("describe_db_clusters").paginate() for c in page["DBClusters"]]
        out, cluster_net = [], {}
        for i in instances:
            vpc = (i.get("DBSubnetGroup") or {}).get("VpcId")
            if i.get("DBClusterIdentifier"):
                cluster_net.setdefault(i["DBClusterIdentifier"], (vpc, bool(i.get("PubliclyAccessible"))))
                continue
            endpoint = i.get("Endpoint") or {}
            out.append(
                {
                    "id": i["DBInstanceIdentifier"],
                    "kind": "instance",
                    "engine": i["Engine"],
                    "status": i.get("DBInstanceStatus"),
                    "host": endpoint.get("Address"),
                    "port": endpoint.get("Port"),
                    "public": bool(i.get("PubliclyAccessible")),
                    "vpc_id": vpc,
                    "security_groups": [g["VpcSecurityGroupId"] for g in i.get("VpcSecurityGroups") or []],
                    "database": i.get("DBName"),
                    "username": i.get("MasterUsername"),
                }
            )
        for c in clusters:
            vpc, public = cluster_net.get(c["DBClusterIdentifier"], (None, False))
            out.append(
                {
                    "id": c["DBClusterIdentifier"],
                    "kind": "cluster",
                    "engine": c["Engine"],
                    "status": c.get("Status"),
                    "host": c.get("Endpoint"),
                    "port": c.get("Port"),
                    "public": public,
                    "vpc_id": vpc,
                    "security_groups": [g["VpcSecurityGroupId"] for g in c.get("VpcSecurityGroups") or []],
                    "database": c.get("DatabaseName"),
                    "username": c.get("MasterUsername"),
                }
            )
        return out

    @_wrap
    def db_instance(self, instance_id: str) -> dict | None:
        """`{status, host, port}`, None once the instance is gone."""
        try:
            i = self._c("rds").describe_db_instances(DBInstanceIdentifier=instance_id)["DBInstances"][0]
        except Exception as exc:  # noqa: BLE001
            if _code(exc) == "DBInstanceNotFound":
                return None
            raise
        endpoint = i.get("Endpoint") or {}
        return {"status": i.get("DBInstanceStatus"), "host": endpoint.get("Address"), "port": endpoint.get("Port")}

    @_wrap
    def create_db_instance(self, params: dict) -> None:
        try:
            self._c("rds").create_db_instance(**params, Tags=[TAG])
        except Exception as exc:  # noqa: BLE001 - an interrupted job already created it
            if _code(exc) != "DBInstanceAlreadyExists":
                raise

    @_wrap
    def delete_db_instance(self, instance_id: str, final_snapshot: str) -> bool:
        """Switches deletion protection off and deletes with a final snapshot. False when already gone."""
        rds = self._c("rds")
        try:
            rds.modify_db_instance(DBInstanceIdentifier=instance_id, DeletionProtection=False, ApplyImmediately=True)
            rds.delete_db_instance(
                DBInstanceIdentifier=instance_id,
                SkipFinalSnapshot=False,
                FinalDBSnapshotIdentifier=final_snapshot,
                DeleteAutomatedBackups=True,  # the final snapshot is the copy that is kept
            )
        except Exception as exc:  # noqa: BLE001
            if _code(exc) == "DBInstanceNotFound":
                return False
            raise
        return True

    @_wrap
    def default_vpc(self) -> str | None:
        vpcs = self._c("ec2").describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])["Vpcs"]
        return vpcs[0]["VpcId"] if vpcs else None

    @_wrap
    def ensure_security_group(self, name: str, vpc_id: str, description: str) -> str:
        ec2 = self._c("ec2")
        try:
            return ec2.create_security_group(
                GroupName=name,
                VpcId=vpc_id,
                Description=description,
                TagSpecifications=[{"ResourceType": "security-group", "Tags": [TAG]}],
            )["GroupId"]
        except Exception as exc:  # noqa: BLE001
            if _code(exc) != "InvalidGroup.Duplicate":
                raise
        filters = [{"Name": "group-name", "Values": [name]}, {"Name": "vpc-id", "Values": [vpc_id]}]
        return ec2.describe_security_groups(Filters=filters)["SecurityGroups"][0]["GroupId"]

    @staticmethod
    def _permission(port: int, cidr: str | None, source_group: str | None) -> list[dict]:
        rule: dict[str, Any] = {"IpProtocol": "tcp", "FromPort": port, "ToPort": port}
        if cidr:
            rule["IpRanges"] = [{"CidrIp": cidr, "Description": "Deployer PC"}]
        if source_group:
            rule["UserIdGroupPairs"] = [{"GroupId": source_group, "Description": "Deployer App Runner apps"}]
        return [rule]

    @_wrap
    def allow_ingress(self, group_id: str, port: int, *, cidr: str | None = None, source_group: str | None = None):
        try:
            self._c("ec2").authorize_security_group_ingress(
                GroupId=group_id, IpPermissions=self._permission(port, cidr, source_group)
            )
        except Exception as exc:  # noqa: BLE001
            if _code(exc) != "InvalidPermission.Duplicate":
                raise

    @_wrap
    def revoke_ingress(self, group_id: str, port: int, *, cidr: str) -> None:
        try:
            self._c("ec2").revoke_security_group_ingress(
                GroupId=group_id, IpPermissions=self._permission(port, cidr, None)
            )
        except Exception as exc:  # noqa: BLE001
            if _code(exc) not in ("InvalidPermission.NotFound", "InvalidGroup.NotFound"):
                raise

    @_wrap
    def delete_security_group(self, group_id: str) -> None:
        try:
            self._c("ec2").delete_security_group(GroupId=group_id)
        except Exception as exc:  # noqa: BLE001
            if _code(exc) != "InvalidGroup.NotFound":
                raise

    @_wrap
    def ensure_vpc_connector(self, vpc_id: str) -> dict:
        """`{arn, group_id}` of the App Runner VPC connector Deployer keeps per VPC (created once, shared
        by every app of the account that uses a database in that VPC; connectors cost nothing)."""
        name = f"deployer-{vpc_id}"[:40]
        group = self.ensure_security_group(
            f"deployer-apprunner-{vpc_id}", vpc_id, "Deployer: App Runner apps that use a database in this VPC"
        )
        ar = self._c("apprunner")
        for page in ar.get_paginator("list_vpc_connectors").paginate():
            for c in page.get("VpcConnectors") or []:
                if c["VpcConnectorName"] == name and c.get("Status") == "ACTIVE":
                    return {"arn": c["VpcConnectorArn"], "group_id": group}
        subnets = self._c("ec2").describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])["Subnets"]
        out = ar.create_vpc_connector(
            VpcConnectorName=name, Subnets=[s["SubnetId"] for s in subnets], SecurityGroups=[group], Tags=[TAG]
        )
        return {"arn": out["VpcConnector"]["VpcConnectorArn"], "group_id": group}

    @_wrap
    def ensure_dynamodb_endpoint(self, vpc_id: str) -> str:
        """A DynamoDB gateway endpoint in the VPC (free, created once, shared): an App Runner app whose
        traffic goes through the VPC (it also uses an RDS database) still reaches DynamoDB without a NAT."""
        ec2 = self._c("ec2")
        service = f"com.amazonaws.{self.region}.dynamodb"
        filters = [{"Name": "vpc-id", "Values": [vpc_id]}, {"Name": "service-name", "Values": [service]}]
        for e in ec2.describe_vpc_endpoints(Filters=filters)["VpcEndpoints"]:
            if str(e.get("State", "")).lower() not in ("deleting", "deleted", "failed", "rejected", "expired"):
                return e["VpcEndpointId"]
        routes = ec2.describe_route_tables(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])["RouteTables"]
        return ec2.create_vpc_endpoint(
            VpcEndpointType="Gateway",
            VpcId=vpc_id,
            ServiceName=service,
            RouteTableIds=[r["RouteTableId"] for r in routes],
            TagSpecifications=[{"ResourceType": "vpc-endpoint", "Tags": [TAG]}],
        )["VpcEndpoint"]["VpcEndpointId"]

    # --- DynamoDB (docs/CLOUD.md "C2-2"; services/dynamo.py) --------------------------------------------

    @_wrap
    def ddb(self, operation: str, **params) -> dict:
        """One DynamoDB API call by its AWS name (`Query`, `PutItem`, `CreateTable`...) with low-level
        (typed) attribute values. The DynamoDB engine's browser, console, schema, backups and the create /
        delete jobs all go through here, so tests fake this one method."""
        from botocore import xform_name
        from botocore.exceptions import ParamValidationError

        try:
            out = getattr(self._c("dynamodb"), xform_name(operation))(**params)
        except ParamValidationError as exc:  # a console request with a wrong parameter: say which
            raise CloudError(f"Invalid request: {exc}", code="ValidationException") from None
        out.pop("ResponseMetadata", None)
        return out

    @_wrap
    def ensure_instance_role(self, name: str, policy: dict | None) -> str:
        """The App Runner instance role `name` (created once) the app's code runs as; its one inline policy
        is `policy` (the DynamoDB tables it may use), removed when None. Returns the role ARN."""
        iam = self._c("iam")
        try:
            arn = iam.get_role(RoleName=name)["Role"]["Arn"]
        except Exception as exc:  # noqa: BLE001
            if _code(exc) != "NoSuchEntity":
                raise
            trust = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"Service": "tasks.apprunner.amazonaws.com"},
                        "Action": "sts:AssumeRole",
                    }
                ],
            }
            arn = iam.create_role(
                RoleName=name,
                AssumeRolePolicyDocument=json.dumps(trust),
                Description="Deployer: what this App Runner app's code may use",
                Tags=[TAG],
            )["Role"]["Arn"]
        if policy:
            iam.put_role_policy(RoleName=name, PolicyName=INSTANCE_ROLE_POLICY, PolicyDocument=json.dumps(policy))
        else:
            try:
                iam.delete_role_policy(RoleName=name, PolicyName=INSTANCE_ROLE_POLICY)
            except Exception as exc:  # noqa: BLE001
                if _code(exc) != "NoSuchEntity":
                    raise
        return arn

    @_wrap
    def delete_instance_role(self, name: str, policy_name: str = INSTANCE_ROLE_POLICY) -> None:
        """Deletes a role Deployer made (its one inline policy first); also the GitHub Actions roles."""
        iam = self._c("iam")
        for call in (
            lambda: iam.delete_role_policy(RoleName=name, PolicyName=policy_name),
            lambda: iam.delete_role(RoleName=name),
        ):
            try:
                call()
            except Exception as exc:  # noqa: BLE001
                if _code(exc) != "NoSuchEntity":
                    raise

    # --- GitHub Actions builds (docs/CLOUD.md "C3") -------------------------------------------------

    @_wrap
    def ensure_github_oidc(self, account_id: str) -> str:
        """The account's IAM identity provider for GitHub Actions tokens (one per account, shared, kept)."""
        iam = self._c("iam")
        try:
            return iam.create_open_id_connect_provider(
                Url=f"https://{GITHUB_OIDC_HOST}", ClientIDList=["sts.amazonaws.com"], Tags=[TAG]
            )["OpenIDConnectProviderArn"]
        except Exception as exc:  # noqa: BLE001
            if _code(exc) != "EntityAlreadyExists":
                raise
        return f"arn:aws:iam::{account_id}:oidc-provider/{GITHUB_OIDC_HOST}"

    @_wrap
    def ensure_github_role(self, name: str, trust: dict, policy: dict) -> str:
        """The role one app's workflow assumes: `trust` (its repository and branch) is (re)written, and
        its one inline policy `policy` (that app's resources only). Returns the role ARN."""
        iam = self._c("iam")
        try:
            arn = iam.get_role(RoleName=name)["Role"]["Arn"]
            iam.update_assume_role_policy(RoleName=name, PolicyDocument=json.dumps(trust))
        except Exception as exc:  # noqa: BLE001
            if _code(exc) != "NoSuchEntity":
                raise
            arn = iam.create_role(
                RoleName=name,
                AssumeRolePolicyDocument=json.dumps(trust),
                Description="Deployer: GitHub Actions deploys of one app",
                MaxSessionDuration=3600,
                Tags=[TAG],
            )["Role"]["Arn"]
        iam.put_role_policy(RoleName=name, PolicyName=GITHUB_ROLE_POLICY, PolicyDocument=json.dumps(policy))
        return arn
