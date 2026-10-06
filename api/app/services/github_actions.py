"""Building cloud apps on GitHub Actions (docs/CLOUD.md "C3"), so a push deploys while this PC is off.

Per cloud app the admin picks where it builds: this PC (C1: the `app.deploy` job) or GitHub Actions. For
GitHub Actions the `app.github_actions` job

- lets the repository's workflow sign in to the cloud account without a stored key (OpenID Connect):
  AWS - the account's IAM identity provider for `token.actions.githubusercontent.com` (shared, kept) and a
  role `deployer-gha-<slug>-<id8>` that only that repository's branch may assume, allowed to update only this
  app's resources; Google - a workload identity provider `gh-<id8>` (in the shared pool `deployer-github`)
  that only accepts that repository's branch, allowed to act as the connection's own service account;
- commits `.github/workflows/deployer-<slug>-<id8>.yml` (through the admin's GitHub connection), which on
  every push builds the same image the PC would and rolls it out straight to the cloud.

The workflow then reports each run to this PC's webhook endpoint, signed with a GitHub OIDC token for the
audience `deployer:<app id>` (no shared secret in the repository). A run that finishes while the PC is off is
recorded by `reconcile` (worker start, then every RECONCILE_EVERY_S) from the GitHub API, with its artifact so
rollback works, and gets the usual retention. Everything is kept in `apps.cloud_state["github"]`, so the
target's teardown removes it with the rest; the role / provider are also removed by their deterministic name
and `sweep_orphans` deletes tagged leftovers, so an app deleted during its setup leaves nothing behind.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ApiError, CloudError, conflict
from app.models import App, CloudConnection, Deployment, Job, utcnow
from app.services import audit, cloud, cloud_aws, cloud_gcp, github, jobs

log = logging.getLogger(__name__)

ISSUER = "https://token.actions.githubusercontent.com"
JWKS_URL = f"{ISSUER}/.well-known/jwks"
POOL = "deployer-github"  # one workload identity pool per Google project, shared, kept
SA_ROLE = "roles/iam.workloadIdentityUser"
REPORT_EVENT = "deployer_build"  # X-GitHub-Event of the workflow's report
RECONCILE_EVERY_S = 5 * 60  # how often the scheduler asks GitHub for runs this PC missed (one call per app)
RECONCILE_RUNS = 10  # the newest runs looked at per app and check
SETUP_WAIT_S = 5 * 60  # a teardown waits this long for the app's setup job to stop (it checks between steps)
_SHA = re.compile(r"[0-9a-f]{40}")
# The cloud resources a workflow updates: they exist once the app was deployed from this PC.
NEEDS = {
    "aws_static": ("bucket", "distribution_id", "distribution_arn"),
    "aws_app": ("service_arn", "ecr_uri", "ecr_repository", "access_role_arn"),
    "firebase_hosting": ("site", "released"),
    "firebase_app": ("run_service", "registry", "ar_package", "released"),
}
COST = (
    "GitHub bills the build minutes: free for public repositories; private ones use your GitHub account's "
    "free minutes (2,000 a month on the Free plan), then GitHub charges for more. The sign-in pieces Deployer "
    "adds to your cloud account (an IAM role, or a workload identity provider) are free; the app itself is "
    "billed as before."
)
# The "Where it builds" chooser and the MCP tool show these as-is.
LOCATIONS = {
    "pc": {
        "label": "This PC",
        "what": "Deployer clones and builds the app here, then uploads it to the cloud.",
        "when_pc_off": "Pushes wait until the PC is on again; the app keeps serving.",
        "cost": "Free.",
    },
    "github": {
        "label": "GitHub Actions",
        "what": "Deployer adds a workflow file to the repository: GitHub builds every push on its own computers "
        "and uploads it to the cloud, signing in with a short-lived token instead of a stored key.",
        "when_pc_off": "Pushes still deploy when this PC is off (the run shows up here once it is on).",
        "cost": COST,
    },
}

_key_resolver: Callable[[str], Any] | None = None  # test hook: token -> verification key
_jwks: jwt.PyJWKClient | None = None


def set_key_resolver(resolver: Callable[[str], Any] | None) -> None:
    """Test hook: verify report tokens with `resolver(token)` instead of GitHub's published keys."""
    global _key_resolver
    _key_resolver = resolver


# --- names & state -------------------------------------------------------------------------------


def workflow_path(app: App) -> str:
    return f".github/workflows/deployer-{app.slug[:30].rstrip('-')}-{app.id[:8]}.yml"


def role_name(app: App) -> str:
    """`deployer-gha-<slug>-<id8>` (IAM role names are <= 64 characters)."""
    return role_name_for(app.slug, app.id)


def role_name_for(slug: str, app_id: str) -> str:
    """The role's name from the app's slug and id alone (a teardown knows it after the app row is gone)."""
    return f"{cloud_aws.GITHUB_ROLE_PREFIX}{slug[:22].rstrip('-')}-{app_id[:8]}"


def provider_id(app_id: str) -> str:
    """`gh-<id8>`: the app's workload identity provider in the shared pool."""
    return f"gh-{app_id[:8]}"


def audience(app: App) -> str:
    return f"deployer:{app.id}"


def state_of(app: App) -> dict | None:
    return (app.cloud_state or {}).get("github")


def builds_on_github(app: App) -> bool:
    """Pushes are GitHub's to build (the PC ignores them) unless the setup failed."""
    gh = state_of(app)
    return gh is not None and gh.get("status") != "error"


def ready(app: App) -> bool:
    return (state_of(app) or {}).get("status") == "ready"


def out(app: App) -> dict:
    """`build` of an app: where it builds and, for GitHub Actions, the setup status and links."""
    gh = state_of(app)
    if gh is None:
        return {"location": "pc"}
    repo, path = gh.get("repo"), gh.get("workflow_path")
    return {
        "location": "github",
        "status": gh.get("status"),
        "message": gh.get("message"),
        "job_id": gh.get("job_id"),
        "repo": repo,
        "workflow_path": path,
        "workflow_url": f"https://github.com/{repo}/blob/{gh.get('branch')}/{path}" if repo and path else None,
        "runs_url": f"https://github.com/{repo}/actions/workflows/{path.rsplit('/', 1)[-1]}" if repo and path else None,
        "reports": gh.get("callback"),
    }


def _merge(app: App, **values) -> None:
    state = dict(app.cloud_state or {})
    gh = state.get("github")
    state["github"] = {**(gh or {}), **values}
    app.cloud_state = state


def _save(factory: jobs.SessionFactory, app_id: str, **values) -> bool:
    """False when the app no longer builds on GitHub (deleted, moved or switched back): nothing is saved."""
    with factory() as db:
        app = db.get(App, app_id, with_for_update=True)
        if app is None or state_of(app) is None:
            return False
        _merge(app, **values)
        db.commit()
        return True


def _token(db: Session, user_id: str | None) -> str | None:
    conn = github.get_connection(db, user_id)
    return github.token_of(conn) if conn else None


# --- switching -----------------------------------------------------------------------------------


def check_can_build(db: Session, app: App, user_id: str) -> None:
    """Why `app` can't build on GitHub Actions with `user_id`'s GitHub connection (raises), else nothing."""
    if app.target == "local":
        raise ApiError(
            422, "validation_error", "GitHub Actions builds are for apps on a cloud target", {"field": "location"}
        )
    if github.parse_repo(app.repo_url) is None:
        raise ApiError(
            422, "validation_error", "GitHub Actions builds need a https://github.com/<owner>/<repo> repository"
        )
    state = app.cloud_state or {}
    if not all(state.get(k) for k in NEEDS[app.target]):
        raise conflict(
            "not_deployed",
            "Deploy the app once from this PC first: that creates the cloud resources GitHub Actions then updates",
        )
    conn = github.get_connection(db, user_id)
    if conn is None:
        raise conflict("github_not_connected", "Connect GitHub first (New app → Connect GitHub)")
    if "workflow" not in (conn.scopes or "").split():
        raise conflict(
            "github_scope_missing",
            "Your GitHub connection may not add workflow files: connect GitHub again (New app → Connect GitHub) "
            "and approve the new permission",
        )


def enqueue_setup(db: Session, app: App, user_id: str) -> str:
    """Switches `app` to GitHub Actions (or repairs / updates its setup) and queues the job. Caller commits."""
    job = jobs.enqueue(
        db,
        type="app.github_actions",
        params={"app_id": app.id, "key": app.id},
        project_id=app.project_id,
        created_by_id=user_id,
    )
    _merge(app, status="setting_up", message=None, job_id=job.id, user_id=user_id)
    return job.id


def cancel_setup(db: Session, app_id: str) -> str | None:
    """A setup job still queued / running for the app is cancelled (it checks between steps, and every save
    re-checks that the app still builds on GitHub). Returns its id so the teardown waits for it to stop."""
    job = jobs.active_job(db, "app.github_actions", key=app_id)
    if job is None:
        return None
    jobs.request_cancel(db, job)
    return job.id


def wait_for_setup(factory: jobs.SessionFactory, job_id: str | None, timeout_s: float = SETUP_WAIT_S) -> None:
    """Blocks until the setup job `job_id` is no longer queued / running (at most `timeout_s`)."""
    started = time.monotonic()
    while job_id:
        with factory() as db:
            status = db.scalar(select(Job.status).where(Job.id == job_id))
        if status not in jobs.ACTIVE_STATUSES or time.monotonic() - started >= timeout_s:
            return
        time.sleep(1)


def enqueue_removal(db: Session, app: App, user_id: str) -> str | None:
    """Back to building on this PC: the workflow file, role / provider go in an `app.cloud_teardown` job."""
    state = dict(app.cloud_state or {})
    gh = state.pop("github", None)
    app.cloud_state = state
    if not gh:
        return None
    job = jobs.enqueue(
        db,
        type="app.cloud_teardown",
        params={
            "app_id": app.id,
            "name": app.name,
            "slug": app.slug,
            "target": app.target,
            "connection_id": app.cloud_connection_id,
            "state": {"github": gh},
            "domains": [],
            "setup_job_id": cancel_setup(db, app.id),
        },
        project_id=app.project_id,
        created_by_id=user_id,
    )
    return job.id


def refresh_if_needed(db: Session, app: App, changed: list[str], user_id: str) -> str | None:
    """Build settings changed on an app that builds on GitHub: the workflow (and the branch it may deploy
    from) is rewritten by the setup job. Returns its id."""
    build_fields = {"branch", "root_dir", "preset", "install_command", "build_command", "start_command", "output_dir"}
    gh = state_of(app)
    if gh is None or not build_fields & set(changed):
        return None
    if gh.get("user_id") and github.get_connection(db, gh["user_id"]) is not None:
        return enqueue_setup(db, app, gh["user_id"])
    _merge(app, status="error", message="Build settings changed: switch GitHub Actions on again to update the workflow")
    return None


def dispatch(db: Session, app: App, branch: str | None) -> dict:
    """Runs the workflow of an app that builds on GitHub ("Deploy now")."""
    gh = state_of(app) or {}
    if branch and branch != app.branch:
        raise ApiError(422, "validation_error", f"GitHub Actions deploys only the app's branch ({app.branch})")
    token = _token(db, gh.get("user_id"))
    if token is None:
        raise conflict("github_not_connected", "The GitHub connection that set up the workflow was removed")
    try:
        github.dispatch_workflow(token, gh["repo"], gh["workflow_path"], app.branch)
    except github.GitHubError as exc:
        raise ApiError(502, "github_error", exc.message) from None
    return {"github_actions": True, "status": "dispatched", "runs_url": out(app)["runs_url"]}


def runs(db: Session, app: App) -> dict:
    gh = state_of(app)
    if gh is None or not gh.get("workflow_path"):
        raise conflict("not_on_github", "This app does not build on GitHub Actions")
    token = _token(db, gh.get("user_id"))
    if token is None:
        raise conflict("github_not_connected", "The GitHub connection that set up the workflow was removed")
    try:
        found = github.workflow_runs(token, gh["repo"], gh["workflow_path"])
    except github.GitHubError as exc:
        raise ApiError(502, "github_error", exc.message) from None
    return {"runs": found, "runs_url": out(app)["runs_url"]}


# --- setup job -----------------------------------------------------------------------------------


def _cel(text: str) -> str:
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def aws_policy(target: str, state: dict, region: str, account: str) -> dict:
    """What one app's workflow may do: update exactly that app's resources."""
    if target == "aws_static":
        bucket = state["bucket"]
        statements = [
            {"Effect": "Allow", "Action": "s3:ListBucket", "Resource": f"arn:aws:s3:::{bucket}"},
            {"Effect": "Allow", "Action": "s3:PutObject", "Resource": f"arn:aws:s3:::{bucket}/d/*"},
            {
                "Effect": "Allow",
                "Action": [
                    "cloudfront:GetDistributionConfig",
                    "cloudfront:UpdateDistribution",
                    "cloudfront:CreateInvalidation",
                ],
                "Resource": state["distribution_arn"],
            },
        ]
    else:
        statements = [
            {"Effect": "Allow", "Action": "ecr:GetAuthorizationToken", "Resource": "*"},
            {
                "Effect": "Allow",
                "Action": [
                    "ecr:BatchCheckLayerAvailability",
                    "ecr:InitiateLayerUpload",
                    "ecr:UploadLayerPart",
                    "ecr:CompleteLayerUpload",
                    "ecr:PutImage",
                    "ecr:BatchGetImage",
                    "ecr:GetDownloadUrlForLayer",
                ],
                "Resource": f"arn:aws:ecr:{region}:{account}:repository/{state['ecr_repository']}",
            },
            {
                "Effect": "Allow",
                "Action": ["apprunner:DescribeService", "apprunner:UpdateService", "apprunner:ListOperations"],
                "Resource": state["service_arn"],
            },
            {
                "Effect": "Allow",
                "Action": "iam:PassRole",
                "Resource": state["access_role_arn"],
                "Condition": {"StringEquals": {"iam:PassedToService": "apprunner.amazonaws.com"}},
            },
        ]
    return {"Version": "2012-10-17", "Statement": statements}


def _aws_identity(app: App, config: dict, repo: str, save) -> dict:
    aws = cloud_aws.client(config)
    account = config.get("account_id") or aws.identity()["account"]
    provider = aws.ensure_github_oidc(account)
    host = cloud_aws.GITHUB_OIDC_HOST
    trust = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Federated": provider},
                "Action": "sts:AssumeRoleWithWebIdentity",
                "Condition": {
                    "StringEquals": {
                        f"{host}:aud": "sts.amazonaws.com",
                        f"{host}:sub": f"repo:{repo}:ref:refs/heads/{app.branch}",
                    }
                },
            }
        ],
    }
    name = role_name(app)
    save(role=name)  # before creating it: an interrupted job still tears it down
    boundary = aws.ensure_boundary(account)["arn"]  # docs/CLOUD.md "G3": the role may never reach past it
    arn = aws.ensure_github_role(
        name, trust, aws_policy(app.target, app.cloud_state, config["region"], account), boundary
    )
    save(role_arn=arn)
    return {"role_arn": arn, "region": config["region"]}


def _google_identity(app: App, config: dict, repo: dict, save) -> dict:
    gcp = cloud_gcp.client(config)
    number = str(gcp.project_info().get("projectNumber") or "")
    if not number.isdigit():
        raise CloudError("Firebase did not say the project's number")
    gcp.ensure_wif_pool(POOL)
    provider = f"gh-{app.id[:8]}"
    save(provider=provider)
    condition = (
        f"assertion.repository_id == {_cel(str(repo['id']))} && assertion.ref == {_cel('refs/heads/' + app.branch)}"
    )
    gcp.ensure_wif_provider(POOL, provider, condition)
    email = config["service_account"]["client_email"]
    member = (
        f"principalSet://iam.googleapis.com/projects/{number}/locations/global/workloadIdentityPools/{POOL}"
        f"/attribute.repository/{repo['full_name']}"
    )
    gcp.set_sa_member(email, SA_ROLE, member, True)
    save(service_account=email, member=member)
    return {
        "provider": f"projects/{number}/locations/global/workloadIdentityPools/{POOL}/providers/{provider}",
        "service_account": email,
        "project": gcp.project,
        "region": gcp.region,
    }


def _q(value: str) -> str:
    """A YAML scalar: JSON-quoted, and never a GitHub `${{ }}` expression (it would be evaluated)."""
    if "${{" in value:
        raise jobs.JobError(f"{value!r} contains '${{{{', which GitHub would evaluate: change it in the app's settings")
    return json.dumps(value)


def render_workflow(app: App, identity: dict, callback: str) -> str:
    """The workflow file. Every value the app's settings control is a JSON-quoted env value or base64 (the
    build recipe), so nothing in them can change the workflow or run in the runner's shell."""
    from app.services.deployments import generate_dockerfile

    s = app.cloud_state or {}
    recipe = generate_dockerfile(app)
    env = {
        "DEPLOYER_CALLBACK": callback,
        "DEPLOYER_AUDIENCE": audience(app),
        "DEPLOYER_ROOT": app.root_dir or ".",
        "RUN_TAG": "gh-${{ github.run_id }}-${{ github.run_attempt }}",
    }
    lines = [
        f"# Added by Deployer for the app {app.slug}: every push to {app.branch} is built here on GitHub and",
        f"# deployed straight to {cloud.TARGETS[app.target]['label']}, signing in with GitHub's short-lived",
        "# OpenID Connect token (no keys are stored), so it also works while the Deployer PC is off.",
        "# Deployer rewrites this file when the app's build settings change; edits here are overwritten.",
        f"name: {_q('Deployer: ' + app.slug)}",
        "on:",
        "  push:",
        f"    branches: [{_q(app.branch)}]",
        "  workflow_dispatch: {}",
        "permissions:",
        "  contents: read",
        "  id-token: write",
        "concurrency:",
        f"  group: deployer-{app.id[:8]}",
        "  cancel-in-progress: false",
        "jobs:",
        "  deploy:",
        "    runs-on: ubuntu-latest",
        "    timeout-minutes: 45",
        "    env:",
        *[f"      {k}: {json.dumps(v) if k == 'RUN_TAG' else _q(v)}" for k, v in env.items()],
        "    steps:",
        "      - uses: actions/checkout@v4",
        "      - name: Build (the same recipe Deployer uses on the PC)",
        "        run: |",
    ]
    if recipe is None:
        lines.append('          docker build -t deployer-build "$DEPLOYER_ROOT"')
    else:
        lines += [
            f"          echo '{base64.b64encode(recipe.encode()).decode()}' | base64 -d > \"$RUNNER_TEMP/Dockerfile\"",
            '          docker build -f "$RUNNER_TEMP/Dockerfile" -t deployer-build "$DEPLOYER_ROOT"',
        ]
    if app.target.startswith("aws"):
        lines += [
            "      - name: Sign in to AWS",
            "        uses: aws-actions/configure-aws-credentials@v4",
            "        with:",
            f"          role-to-assume: {_q(identity['role_arn'])}",
            f"          aws-region: {_q(identity['region'])}",
        ]
    else:
        lines += [
            "      - name: Sign in to Google Cloud",
            "        id: auth",
            "        uses: google-github-actions/auth@v2",
            "        with:",
            f"          workload_identity_provider: {_q(identity['provider'])}",
            f"          service_account: {_q(identity['service_account'])}",
            "          token_format: access_token",
        ]
    export = [
        '          docker cp "$(docker create deployer-build)":/usr/share/nginx/html "$RUNNER_TEMP/site"',
    ]
    if app.target == "aws_static":
        lines += [
            "      - name: Upload to S3 and switch CloudFront to it",
            "        env:",
            f"          BUCKET: {_q(s['bucket'])}",
            f"          DISTRIBUTION: {_q(s['distribution_id'])}",
            "        run: |",
            *export,
            '          PREFIX="d/$RUN_TAG"',
            '          aws s3 sync "$RUNNER_TEMP/site" "s3://$BUCKET/$PREFIX/" --exclude "*.html" '
            '--cache-control "public, max-age=3600" --no-progress',
            '          aws s3 sync "$RUNNER_TEMP/site" "s3://$BUCKET/$PREFIX/" --exclude "*" --include "*.html" '
            "--cache-control no-cache --content-type text/html --no-progress",
            '          aws cloudfront get-distribution-config --id "$DISTRIBUTION" > "$RUNNER_TEMP/dist.json"',
            "          jq --arg path \"/$PREFIX\" '.DistributionConfig | .Origins.Items[0].OriginPath = $path' "
            '"$RUNNER_TEMP/dist.json" > "$RUNNER_TEMP/config.json"',
            '          aws cloudfront update-distribution --id "$DISTRIBUTION" --if-match "$(jq -r .ETag '
            '"$RUNNER_TEMP/dist.json")" --distribution-config "file://$RUNNER_TEMP/config.json" > /dev/null',
            "          aws cloudfront create-invalidation --distribution-id \"$DISTRIBUTION\" --paths '/*' > /dev/null",
            '          echo "Live (CloudFront spreads it worldwide within minutes)"',
        ]
    elif app.target == "aws_app":
        registry = s["ecr_uri"].split("/", 1)[0]
        lines += [
            "      - name: Push the image and roll App Runner out to it",
            "        env:",
            f"          REPOSITORY: {_q(s['ecr_uri'])}",
            f"          REGISTRY: {_q(registry)}",
            f"          SERVICE: {_q(s['service_arn'])}",
            "        run: |",
            '          IMAGE="$REPOSITORY:$RUN_TAG"',
            '          aws ecr get-login-password | docker login --username AWS --password-stdin "$REGISTRY"',
            '          docker tag deployer-build "$IMAGE" && docker push "$IMAGE"',
            "          # Keeps the service's port, environment and access role; only the image changes.",
            '          aws apprunner describe-service --service-arn "$SERVICE" --query Service.SourceConfiguration '
            "--output json | jq --arg image \"$IMAGE\" '.ImageRepository.ImageIdentifier = $image' "
            '> "$RUNNER_TEMP/source.json"',
            '          OP=$(aws apprunner update-service --service-arn "$SERVICE" --source-configuration '
            '"file://$RUNNER_TEMP/source.json" --query OperationId --output text)',
            "          for i in $(seq 1 150); do",
            '            STATUS=$(aws apprunner list-operations --service-arn "$SERVICE" '
            "--query \"OperationSummaryList[?Id=='$OP'].Status | [0]\" --output text)",
            '            echo "App Runner: $STATUS"',
            '            case "$STATUS" in SUCCEEDED) exit 0;; FAILED|ROLLBACK_*) exit 1;; esac',
            "            sleep 10",
            "          done",
            "          exit 1",
        ]
    elif app.target == "firebase_hosting":
        lines += [
            "      - name: Deploy to Firebase Hosting",
            "        env:",
            f"          SITE: {_q(s['site'])}",
            f"          PROJECT: {_q(identity['project'])}",
            "          TOKEN: ${{ steps.auth.outputs.access_token }}",
            "        run: |",
            *export,
            '          mkdir -p "$RUNNER_TEMP/firebase" && cd "$RUNNER_TEMP/firebase" && mv "$RUNNER_TEMP/site" public',
            '          jq -n --arg site "$SITE" \'{hosting: {site: $site, public: "public", rewrites: [{source: "**", '
            'destination: "/index.html"}], headers: [{source: "**/*.html", headers: [{key: "Cache-Control", '
            'value: "no-cache"}]}]}}\' > firebase.json',
            '          npx --yes firebase-tools@13 deploy --only hosting --project "$PROJECT" --non-interactive',
            '          VERSION=$(curl -sSf -H "Authorization: Bearer $TOKEN" '
            '"https://firebasehosting.googleapis.com/v1beta1/sites/$SITE/channels/live" | jq -r .release.version.name)',
            '          echo "ARTIFACT=$VERSION" >> "$GITHUB_ENV"',
        ]
    else:
        lines += [
            "      - name: Push the image and deploy it to Cloud Run",
            "        env:",
            f"          IMAGE_BASE: {_q(s['registry'] + '/' + s['ar_package'])}",
            f"          SERVICE: {_q(s['run_service'])}",
            f"          REGION: {_q(s.get('run_region') or identity['region'])}",
            f"          PROJECT: {_q(identity['project'])}",
            "          TOKEN: ${{ steps.auth.outputs.access_token }}",
            "        run: |",
            '          IMAGE="$IMAGE_BASE:$RUN_TAG"',
            '          echo "$TOKEN" | docker login -u oauth2accesstoken --password-stdin "https://${IMAGE_BASE%%/*}"',
            '          docker tag deployer-build "$IMAGE" && docker push "$IMAGE"',
            "          # Keeps the service's port and environment; only the image changes.",
            '          gcloud run services update "$SERVICE" --image "$IMAGE" --region "$REGION" --project "$PROJECT" '
            "--quiet",
        ]
    lines += [
        "      - name: Tell Deployer (skipped while it has no public address; the deploy does not depend on it)",
        "        if: always() && env.DEPLOYER_CALLBACK != ''",
        "        continue-on-error: true",
        "        env:",
        "          STATUS: ${{ job.status }}",
        "        run: |",
        '          ID_TOKEN=$(curl -sSf -H "Authorization: bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" '
        '"$ACTIONS_ID_TOKEN_REQUEST_URL&audience=$DEPLOYER_AUDIENCE" | jq -r .value)',
        '          jq -n --arg status "$STATUS" --arg artifact "${ARTIFACT:-}" '
        '--arg message "$(git log -1 --pretty=%s)" '
        "'{status: $status, artifact: $artifact, message: $message}' | curl -sS --max-time 20 -X POST "
        f'"$DEPLOYER_CALLBACK" -H "Authorization: Bearer $ID_TOKEN" -H "X-GitHub-Event: {REPORT_EVENT}" '
        '-H "Content-Type: application/json" --data @- || echo "Deployer did not answer (is the PC off?)"',
    ]
    return "\n".join(lines) + "\n"


@jobs.job_handler("app.github_actions")
def _job_setup(ctx: jobs.JobContext) -> dict:
    app_id = str(ctx.params["app_id"])
    try:
        return _setup(ctx, app_id)
    except (CloudError, github.GitHubError, jobs.JobError) as exc:
        message = getattr(exc, "message", None) or str(exc)
        _save(ctx.session_factory, app_id, status="error", message=message)
        raise jobs.JobError(message) from None


def _setup(ctx: jobs.JobContext, app_id: str) -> dict:
    from app.services.deployments import webhook_url

    factory = ctx.session_factory
    with factory() as db:
        app = db.get(App, app_id)
        gh = state_of(app) if app is not None else None
        if gh is None or app.target == "local":
            return {"skipped": "GitHub Actions builds were switched off"}
        conn = db.get(CloudConnection, app.cloud_connection_id) if app.cloud_connection_id else None
        token = _token(db, gh.get("user_id"))
        if conn is None or token is None:
            raise jobs.JobError("The app's cloud connection or the GitHub connection that set this up was removed")
        provider, config = conn.provider, cloud.config_of(conn)
        callback = webhook_url(db, app)
        db.expunge(app)
    callback = "" if github.unreachable_reason(callback) else callback

    def save(**values) -> None:
        if not _save(factory, app_id, **values):  # deleted, moved or switched back meanwhile: stop here
            raise jobs.JobCancelled()

    ctx.progress(0.1, "Checking the repository", force=True)
    repo = github.repo_for_actions(token, app.repo_url)
    save(repo=repo["full_name"], repo_id=repo["id"], branch=app.branch)
    ctx.check_cancelled()
    ctx.progress(0.3, "Letting GitHub Actions sign in to your cloud account", force=True)
    if provider == "aws":
        identity = _aws_identity(app, config, repo["full_name"], save)
    else:
        identity = _google_identity(app, config, repo, save)
    ctx.check_cancelled()
    path = workflow_path(app)
    ctx.progress(0.7, f"Adding {path} to {repo['full_name']}", force=True)
    text = render_workflow(app, identity, callback)
    save(workflow_path=path)  # before the commit: an interrupted job still removes the file
    commit = github.put_file(
        token, repo["full_name"], path, app.branch, text, f"Deployer: build and deploy {app.slug} on GitHub Actions"
    )
    old = gh.get("branch")
    if old and old != app.branch and gh.get("workflow_path"):  # the branch changed: its old copy goes
        try:
            github.delete_file(
                token, repo["full_name"], gh["workflow_path"], old, "Deployer: the app now deploys from " + app.branch
            )
        except github.GitHubError:
            pass  # best effort: without the old trust the old copy can no longer sign in anyway
    message = None if callback else "Deployer has no public address, so runs can't report back here; they still deploy"
    save(status="ready", message=message, commit=commit, callback=bool(callback))
    return {"repo": repo["full_name"], "workflow": path, "commit": commit}


# --- teardown ------------------------------------------------------------------------------------


def teardown_steps(
    client,
    target: str,
    gh: dict,
    token: str | None,
    keep_member: bool,
    slug: str | None = None,
    app_id: str | None = None,
) -> list[tuple[str, object]]:
    """(label, call) removing what the setup made; the shared OIDC provider / pool stay. The role / provider
    are named from `slug` / `app_id` when the state never recorded them (the setup was interrupted, or the app
    row was already gone when it tried to), so a delete during the setup leaves nothing behind."""
    steps: list[tuple[str, object]] = []
    gh = dict(gh)
    if slug and app_id:
        if target.startswith("aws"):
            gh.setdefault("role", role_name_for(slug, app_id))
        else:
            gh.setdefault("provider", provider_id(app_id))
    repo, path = gh.get("repo"), gh.get("workflow_path")
    if repo and path:

        def remove_file() -> None:
            if token is None:
                raise CloudError("the GitHub connection that added it was removed; delete the file on GitHub")
            try:
                github.delete_file(
                    token, repo, path, gh.get("branch") or "main", "Deployer: stop building on GitHub Actions"
                )
            except github.GitHubError as exc:
                raise CloudError(exc.message) from None

        steps.append((f"Workflow file {path} in {repo}", remove_file))
    if target.startswith("aws") and gh.get("role"):
        steps.append(
            (f"IAM role {gh['role']}", lambda: client.delete_instance_role(gh["role"], cloud_aws.GITHUB_ROLE_POLICY))
        )
    if target.startswith("firebase"):
        if gh.get("provider"):
            steps.append(
                (
                    f"Workload identity provider {gh['provider']}",
                    lambda: client.delete_wif_provider(POOL, gh["provider"]),
                )
            )
        if gh.get("member") and not keep_member:
            steps.append(
                (
                    f"GitHub Actions access to {gh['service_account']}",
                    lambda: client.set_sa_member(gh["service_account"], SA_ROLE, gh["member"], False),
                )
            )
    return steps


def teardown_context(db: Session, app_id: str, connection_id: str | None, gh: dict) -> tuple[str | None, bool]:
    """(GitHub token, keep the service-account binding: another app of the same repository still uses it)."""
    others = db.scalars(select(App).where(App.cloud_connection_id == connection_id, App.id != app_id))
    keep = any((state_of(o) or {}).get("member") == gh.get("member") for o in others) if gh.get("member") else False
    return _token(db, gh.get("user_id")), keep


def sweep_orphans(db: Session, client, provider: str) -> list[str]:
    """Removes the `deployer-gha-*` roles (tagged managed-by=deployer) / `gh-*` providers and pool members of
    the shared pool that belong to no app building on GitHub Actions any more - leftovers of an app deleted
    while its setup ran, or of a failed teardown. Returns what was removed. Bounded: one list call per kind."""
    apps = [a for a in db.scalars(select(App).where(App.target != "local")) if state_of(a) is not None]
    removed: list[str] = []
    if provider == "aws":
        known = {role_name(a) for a in apps}
        for name in client.github_roles() or []:
            if name not in known:
                client.delete_instance_role(name, cloud_aws.GITHUB_ROLE_POLICY)
                removed.append(f"IAM role {name}")
        return removed
    known = {provider_id(a.id) for a in apps}
    for name in client.wif_providers(POOL) or []:
        if name.startswith("gh-") and name not in known:
            client.delete_wif_provider(POOL, name)
            removed.append(f"Workload identity provider {name}")
    members = {(state_of(a) or {}).get("member") for a in apps}
    marker = f"/workloadIdentityPools/{POOL}/attribute.repository/"
    email = client.service_account_email
    for member in (client.sa_members(email, SA_ROLE) or []) if isinstance(email, str) else []:
        if marker in member and member not in members:
            client.set_sa_member(email, SA_ROLE, member, False)
            removed.append(f"GitHub Actions access of {member.split(marker, 1)[1]} to {email}")
    return removed


def resources(gh: dict | None) -> list[str]:
    gh = gh or {}
    out = []
    if gh.get("workflow_path"):
        out.append(f"Workflow file {gh['workflow_path']} in the GitHub repository {gh.get('repo')}")
    if gh.get("role"):
        out.append(f"IAM role {gh['role']} (GitHub Actions deploys)")
    if gh.get("provider"):
        out.append(f"Workload identity provider {gh['provider']} (GitHub Actions sign-in)")
    return out


# --- reports from the workflow -------------------------------------------------------------------


def _verify(app: App, gh: dict, authorization: str) -> dict:
    token = authorization.removeprefix("Bearer ").strip()
    try:
        if _key_resolver is not None:
            key = _key_resolver(token)
        else:
            global _jwks
            _jwks = _jwks or jwt.PyJWKClient(JWKS_URL, cache_keys=True, lifespan=3600, timeout=10)
            key = _jwks.get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=audience(app),
            issuer=ISSUER,
            options={"require": ["exp", "iat", "aud", "iss", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise ApiError(
            401, "bad_signature", f"The GitHub Actions token was not accepted ({type(exc).__name__})"
        ) from None
    repo, path = str(gh.get("repo") or ""), str(gh.get("workflow_path") or "")
    if (
        str(claims.get("repository_id")) != str(gh.get("repo_id"))
        or str(claims.get("repository", "")).lower() != repo.lower()
        or claims.get("ref") != f"refs/heads/{gh.get('branch')}"
        or not str(claims.get("workflow_ref", "")).lower().startswith(f"{repo}/{path}@".lower())
        or not str(claims.get("run_id", "")).isdigit()
        or not str(claims.get("run_attempt", "")).isdigit()
        or not re.fullmatch(r"[0-9a-f]{40}", str(claims.get("sha", "")))
    ):
        raise ApiError(401, "bad_signature", "The token is not from this app's workflow")
    return claims


def artifact_for(app: App, run: str, reported: str) -> str | None:
    """What a rollback republishes. Deployer derives it from the run (only Hosting's version comes from the
    report, and must be one of the app's own site's versions), so a report can't point the app elsewhere."""
    s = app.cloud_state or {}
    if app.target == "aws_static":
        return f"d/gh-{run}"
    if app.target == "aws_app":
        return f"{s['ecr_uri']}:gh-{run}"
    if app.target == "firebase_app":
        return f"{s['registry']}/{s['ar_package']}:gh-{run}"
    site = re.escape(str(s.get("site")))
    return reported if re.fullmatch(rf"(projects/[\w-]+/)?sites/{site}/versions/[\w-]+", reported or "") else None


def record_report(db: Session, app: App, authorization: str, body: Any) -> Deployment | None:
    """A run's result (signed by GitHub for this app's workflow) becomes a deployment; a success goes live.
    Caller commits. None when the app no longer builds on GitHub."""
    gh = state_of(app)
    if gh is None or not gh.get("workflow_path"):
        raise ApiError(409, "not_on_github", "This app does not build on GitHub Actions")
    claims = _verify(app, gh, authorization)
    body = body if isinstance(body, dict) else {}
    outcome = str(body.get("status"))
    if outcome not in ("success", "failure", "cancelled"):
        raise ApiError(400, "invalid_payload", "status must be success, failure or cancelled")
    return _record(
        db,
        app,
        gh,
        run_id=str(claims["run_id"]),
        attempt=str(claims["run_attempt"]),
        sha=str(claims["sha"]),
        outcome=outcome,
        artifact=str(body.get("artifact") or ""),
        message=str(body.get("message") or ""),
    )


def _record(
    db: Session,
    app: App,
    gh: dict,
    *,
    run_id: str,
    attempt: str,
    sha: str,
    outcome: str,
    artifact: str,
    message: str,
    go_live: bool = True,
    created_at: datetime | None = None,
    finished_at: datetime | None = None,
    note: str = "",
) -> Deployment | None:
    """One run (reported, or found by `reconcile`) becomes one deployment; a recorded run is skipped (None).
    `outcome` is GitHub's conclusion: success -> live (superseded instead when `go_live` is False: something
    newer is live already), cancelled -> cancelled, anything else -> failed. Caller commits."""
    from app.services import cloud_deploy

    run = f"{run_id}-{attempt}"
    url = f"https://github.com/{gh['repo']}/actions/runs/{run_id}/attempts/{attempt}"
    header = f"Built on GitHub Actions: {url}"
    if db.scalar(select(Deployment.id).where(Deployment.app_id == app.id, Deployment.log.startswith(header))):
        return None  # already recorded
    status = {"success": "live" if go_live else "superseded", "cancelled": "cancelled"}.get(outcome, "failed")
    dep = Deployment(
        app_id=app.id,
        status=status,
        trigger="github",
        branch=gh.get("branch") or app.branch,
        commit_sha=sha,
        commit_message=message.splitlines()[0][:200] if message else None,
        finished_at=finished_at or utcnow(),
        log=header + note,
    )
    if created_at is not None:
        dep.created_at = created_at
    if outcome == "success":
        dep.image_tag = artifact_for(app, run, artifact)
        dep.target_url = cloud_deploy.cloud_url(app)
    else:
        dep.error = f"The run on GitHub Actions ended {outcome}: its log is at {url}"
    db.add(dep)
    db.flush()
    if status == "live":
        previous = db.get(Deployment, app.live_deployment_id) if app.live_deployment_id else None
        if previous is not None:
            previous.status = "superseded"
        app.live_deployment_id = dep.id
    return dep


# --- runs this PC missed (it was off) -----------------------------------------------------------

_last_reconcile = float("-inf")


def _when(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC).replace(tzinfo=None)
    except ValueError:
        return None


def reconcile(factory: jobs.SessionFactory, *, force: bool = False) -> list[str]:
    """Scheduler tick (worker start, then every RECONCILE_EVERY_S): runs of each app's workflow that finished
    while this PC was off - never reported - become deployments with their commit, result and artifact (so
    rollback works) and get the usual retention (`app.cloud_prune`). One GitHub call per app that builds there
    (plus one Hosting call when a Hosting site has a new live run); safe to repeat. Returns the deployment ids."""
    global _last_reconcile
    if not force and time.monotonic() - _last_reconcile < RECONCILE_EVERY_S:
        return []
    _last_reconcile = time.monotonic()
    with factory() as db:
        ids = [a.id for a in db.scalars(select(App).where(App.target != "local")) if ready(a)]
    recorded: list[str] = []
    for app_id in ids:
        try:
            recorded += _reconcile_app(factory, app_id)
        except (github.GitHubError, CloudError, jobs.JobError) as exc:
            log.info("could not check the GitHub Actions runs of app %s: %s", app_id, getattr(exc, "message", exc))
    return recorded


def _reconcile_app(factory: jobs.SessionFactory, app_id: str) -> list[str]:
    from app.services import cloud_deploy

    with factory() as db:
        app = db.get(App, app_id)
        gh = state_of(app) if app is not None else None
        if gh is None or not gh.get("workflow_path"):
            return []
        token = _token(db, gh.get("user_id"))
        if token is None:
            return []
        runs = [
            r
            for r in github.workflow_runs(token, gh["repo"], gh["workflow_path"], limit=RECONCILE_RUNS)
            if r.get("status") == "completed"
            and r.get("branch") == gh.get("branch")
            and r.get("event") in ("push", "workflow_dispatch")
            and str(r.get("id")).isdigit()
            and str(r.get("attempt")).isdigit()
            and _SHA.fullmatch(str(r.get("sha")))
            and _when(r.get("updated_at")) is not None
        ]
        newest = next((r for r in runs if r.get("conclusion") == "success"), None)  # newest first from GitHub
        recorded: list[str] = []
        prune = False
        for r in reversed(runs):  # oldest first: successes supersede each other in order
            finished = _when(r.get("updated_at"))
            live = db.get(Deployment, app.live_deployment_id) if app.live_deployment_id else None
            go_live = live is None or (live.finished_at or live.created_at) < finished
            artifact = ""
            if r is newest and go_live and app.target == "firebase_hosting":
                # The workflow reports the version it released; afterwards only the live one is known, and it
                # is the newest run's (older runs stay without one: no rollback to them).
                _, config = cloud_deploy._connection(factory, app)
                artifact = cloud_gcp.client(config).live_version(app.cloud_state["site"]) or ""
            dep = _record(
                db,
                app,
                gh,
                run_id=str(r["id"]),
                attempt=str(r["attempt"]),
                sha=str(r["sha"]),
                outcome=str(r.get("conclusion") or "failure"),
                artifact=artifact,
                message=str(r.get("message") or ""),
                go_live=go_live,
                created_at=_when(r.get("created_at")),
                finished_at=finished,
                note="\nRecorded by Deployer afterwards: the run finished while this PC was off.",
            )
            if dep is None:
                continue
            recorded.append(dep.id)
            prune = prune or dep.status == "live"
            audit.record(
                db, "app.deploy", project_id=app.project_id, app_id=app.id, deployment_id=dep.id, trigger="github"
            )
        job = None
        if prune:  # old artifacts go, like after a report
            job = jobs.enqueue(db, type="app.cloud_prune", params={"app_id": app.id}, project_id=app.project_id)
        db.commit()
        if job is not None:
            jobs.dispatch(job.id)
    return recorded
