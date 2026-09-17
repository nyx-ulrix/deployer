"""Remote access & custom domains via Cloudflare (docs/REMOTE_ACCESS.md). Instance owner only."""

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.deps import DbSession, InstanceOwner
from app.routers.instance import settings_out
from app.services import remote_access as ra

router = APIRouter(tags=["remote-access"])
# Re-create /tunnel/desired.json from the database if the volume was reset.
router.add_event_handler("startup", ra.sync_on_startup)

PREFIX = "/instance/remote-access"


@router.get(PREFIX)
def get_remote_access(owner: InstanceOwner, db: DbSession) -> dict:
    ra.sync_desired(db)
    db.commit()
    return ra.remote_access_out(db)


class VerifyBody(BaseModel):
    api_token: str = Field(min_length=1, max_length=512)


@router.post(f"{PREFIX}/cloudflare/verify")
def verify_token(body: VerifyBody, owner: InstanceOwner) -> dict:
    return ra.verify(body.api_token.strip())


class LinkBody(BaseModel):
    api_token: str = Field(min_length=1, max_length=512)
    account_id: str = Field(min_length=1, max_length=64, pattern=r"^\s*[A-Za-z0-9]+\s*$")


@router.post(f"{PREFIX}/cloudflare/link")
def link(body: LinkBody, request: Request, owner: InstanceOwner, db: DbSession) -> dict:
    return ra.link(db, body.api_token, body.account_id, request=request, user_id=owner.id)


class HostnameBody(BaseModel):
    zone_id: str = Field(min_length=1, max_length=64, pattern=r"^\s*[A-Za-z0-9]+\s*$")
    hostname: str = Field(min_length=1, max_length=300)
    overwrite: bool = False


@router.post(f"{PREFIX}/cloudflare/hostnames")
def add_hostname(body: HostnameBody, request: Request, owner: InstanceOwner, db: DbSession) -> dict:
    return ra.add_hostname(db, body.zone_id, body.hostname, body.overwrite, request=request, user_id=owner.id)


@router.delete(f"{PREFIX}/cloudflare/hostnames/{{domain_id}}")
def remove_hostname(domain_id: str, request: Request, owner: InstanceOwner, db: DbSession) -> dict:
    ra.remove_hostname(db, domain_id, request=request, user_id=owner.id)
    return {"ok": True}


class UnlinkBody(BaseModel):
    delete_dns: bool = False
    delete_tunnel: bool = False


@router.post(f"{PREFIX}/cloudflare/unlink")
def unlink(body: UnlinkBody, request: Request, owner: InstanceOwner, db: DbSession) -> dict:
    return ra.unlink(db, body.delete_dns, body.delete_tunnel, request=request, user_id=owner.id)


class QuickBody(BaseModel):
    enabled: bool


@router.post(f"{PREFIX}/quick")
def quick(body: QuickBody, request: Request, owner: InstanceOwner, db: DbSession) -> dict:
    return ra.set_quick(db, body.enabled, request=request, user_id=owner.id)


class PublicUrlBody(BaseModel):
    domain_id: str | None = Field(default=None, max_length=36)
    quick: bool = False
    local: bool = False


@router.post(f"{PREFIX}/public-url")
def switch_public_url(body: PublicUrlBody, request: Request, owner: InstanceOwner, db: DbSession) -> dict:
    previous, _new = ra.switch_public_url(
        db, domain_id=body.domain_id, quick=body.quick, local=body.local, request=request, user_id=owner.id
    )
    return {"settings": settings_out(db), "oauth_callbacks": ra.oauth_callbacks(db), "previous_public_url": previous}
