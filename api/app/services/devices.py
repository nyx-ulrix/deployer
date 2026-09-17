"""Host devices on the main Deployer (docs/DEVICES.md): enrollment, device tokens, permissions and
placement eligibility.

- Enrollment follows the device authorization flow: the device creates an enrollment and receives
  a short `user_code` (8 chars from an unambiguous alphabet, shown as `ABCD-EFGH`) plus a
  `poll_secret`; a signed-in user approves the code on the main Deployer; the device polls and
  receives its raw `dpd_…` token exactly once.
- Only SHA-256 hashes of device tokens and poll secrets are stored. Between approval and the
  device's poll the raw token is kept encrypted with MASTER_KEY and wiped when delivered.
"""

from __future__ import annotations

import logging
import re
import secrets
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.crypto import decrypt_secret, encrypt_secret, random_token, sha256_hex
from app.errors import ApiError, not_found, unauthorized
from app.models import (
    DataSource,
    Device,
    DeviceEnrollment,
    DeviceProjectGrant,
    Project,
    ProjectMember,
    User,
    role_rank,
    utcnow,
)
from app.redis_client import get_redis

log = logging.getLogger(__name__)

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I
CODE_LENGTH = 8
ENROLLMENT_TTL_SECONDS = 15 * 60
POLL_INTERVAL_SECONDS = 5
POLL_MIN_INTERVAL_SECONDS = 4
TOKEN_PREFIX = "dpd_"
DEVICE_ROLES = ("database_host", "backup_storage")
SHARING_MODES = ("my_projects", "selected")
_CODE_RE = re.compile(rf"^[{CODE_ALPHABET}]{{{CODE_LENGTH}}}$")


# ---------------------------------------------------------------------------------------------
# codes & tokens
# ---------------------------------------------------------------------------------------------


def generate_user_code() -> str:
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
    return f"{raw[:4]}-{raw[4:]}"


def normalize_user_code(code: str | None) -> str | None:
    """Accepts `abcd-efgh`, `ABCDEFGH`, `ABCD EFGH`; returns `ABCD-EFGH` or None if malformed."""
    raw = re.sub(r"[\s-]", "", (code or "")).upper()
    if not _CODE_RE.fullmatch(raw):
        return None
    return f"{raw[:4]}-{raw[4:]}"


def generate_device_token() -> str:
    return TOKEN_PREFIX + random_token(32)


def hash_token(token: str) -> str:
    return sha256_hex(token)


# ---------------------------------------------------------------------------------------------
# enrollment
# ---------------------------------------------------------------------------------------------


def _clean(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:limit] or None


def expire_if_needed(enrollment: DeviceEnrollment) -> DeviceEnrollment:
    if enrollment.status in ("pending", "approved") and enrollment.expires_at <= utcnow():
        enrollment.status = "expired"
        enrollment.device_token_encrypted = None
    return enrollment


def create_enrollment(
    db: Session,
    *,
    name: str,
    hostname: str | None = None,
    os: str | None = None,
    version: str | None = None,
    capabilities: dict | None = None,
) -> tuple[DeviceEnrollment, str]:
    """Adds a pending enrollment (caller commits). Returns (row, raw poll secret)."""
    poll_secret = random_token(32)
    for _ in range(10):
        code = generate_user_code()
        if db.scalar(select(DeviceEnrollment.id).where(DeviceEnrollment.user_code == code)) is None:
            break
    else:  # pragma: no cover - 32^8 codes
        raise ApiError(500, "enrollment_failed", "Could not allocate an enrollment code")
    row = DeviceEnrollment(
        user_code=code,
        poll_secret_hash=sha256_hex(poll_secret),
        name=_clean(name, 80) or "Host device",
        hostname=_clean(hostname, 255),
        os=_clean(os, 120),
        version=_clean(version, 32),
        capabilities=capabilities if isinstance(capabilities, dict) else None,
        status="pending",
        expires_at=utcnow() + timedelta(seconds=ENROLLMENT_TTL_SECONDS),
    )
    db.add(row)
    db.flush()
    return row, poll_secret


def _poll_allowed(enrollment_id: str) -> bool:
    try:
        return bool(
            get_redis().set(f"device:enroll:poll:{enrollment_id}", "1", nx=True, px=POLL_MIN_INTERVAL_SECONDS * 1000)
        )
    except Exception:  # noqa: BLE001 - fail open when Redis is unavailable
        return True


def poll_enrollment(db: Session, enrollment_id: str, poll_secret: str) -> dict:
    """Device-side poll. Delivers the raw device token once. Caller commits."""
    row = db.get(DeviceEnrollment, enrollment_id)
    if row is None or not poll_secret or not secrets.compare_digest(row.poll_secret_hash, sha256_hex(poll_secret)):
        raise not_found("Enrollment")
    if not _poll_allowed(row.id):
        raise ApiError(429, "slow_down", "Polling too fast", {"interval": POLL_INTERVAL_SECONDS})
    expire_if_needed(row)
    if row.status == "approved" and row.device_token_encrypted:
        token = decrypt_secret(row.device_token_encrypted)
        row.device_token_encrypted = None
        row.status = "consumed"
        device = db.get(Device, row.device_id) if row.device_id else None
        return {
            "status": "approved",
            "device_id": row.device_id,
            "device_token": token,
            "device_name": device.name if device else row.name,
        }
    return {"status": row.status, "interval": POLL_INTERVAL_SECONDS}


def enrollment_by_code(db: Session, code: str) -> DeviceEnrollment:
    normalized = normalize_user_code(code)
    if normalized is None:
        raise not_found("Enrollment")
    row = db.scalar(select(DeviceEnrollment).where(DeviceEnrollment.user_code == normalized))
    if row is None:
        raise not_found("Enrollment")
    expire_if_needed(row)
    return row


def enrollment_out(row: DeviceEnrollment) -> dict:
    from app.serializers import iso

    return {
        "id": row.id,
        "user_code": row.user_code,
        "name": row.name,
        "hostname": row.hostname,
        "os": row.os,
        "version": row.version,
        "capabilities": row.capabilities or {},
        "status": row.status,
        "expires_at": iso(row.expires_at),
        "created_at": iso(row.created_at),
    }


def _require_pending(row: DeviceEnrollment) -> None:
    expire_if_needed(row)
    if row.status != "pending":
        raise ApiError(409, "enrollment_not_pending", f"This enrollment is {row.status}")


def normalize_roles(roles: list[str] | None) -> list[str]:
    if roles is None:
        return ["database_host"]
    out = []
    for role in roles:
        if role not in DEVICE_ROLES:
            raise ApiError(422, "validation_error", f"Unknown device role: {role}")
        if role not in out:
            out.append(role)
    return out


def set_grants(db: Session, device: Device, user: User, project_ids: list[str]) -> None:
    """Replaces the device's project grants. Every project must be one the user is a member of."""
    wanted = list(dict.fromkeys(project_ids))
    for pid in wanted:
        member = db.scalar(
            select(ProjectMember).where(ProjectMember.project_id == pid, ProjectMember.user_id == device.owner_id)
        )
        if member is None and not user.is_instance_owner:
            raise ApiError(422, "validation_error", "Device can only be shared with projects its owner belongs to")
        if db.get(Project, pid) is None:
            raise not_found("Project")
    existing = {
        g.project_id: g for g in db.scalars(select(DeviceProjectGrant).where(DeviceProjectGrant.device_id == device.id))
    }
    for pid, grant in existing.items():
        if pid not in wanted:
            db.delete(grant)
    for pid in wanted:
        if pid not in existing:
            db.add(DeviceProjectGrant(device_id=device.id, project_id=pid))


def approve_enrollment(
    db: Session,
    row: DeviceEnrollment,
    user: User,
    *,
    name: str | None = None,
    roles: list[str] | None = None,
    sharing_mode: str = "my_projects",
    project_ids: list[str] | None = None,
) -> Device:
    """Creates the device owned by `user` and stores its token for the device's next poll."""
    _require_pending(row)
    if sharing_mode not in SHARING_MODES:
        raise ApiError(422, "validation_error", "sharing_mode must be my_projects or selected")
    token = generate_device_token()
    device = Device(
        name=_clean(name, 80) or row.name,
        owner_id=user.id,
        status="active",
        roles=normalize_roles(roles),
        sharing_mode=sharing_mode,
        token_hash=hash_token(token),
        hostname=row.hostname,
        os=row.os,
        version=row.version,
        capabilities=row.capabilities,
    )
    db.add(device)
    db.flush()
    if sharing_mode == "selected":
        set_grants(db, device, user, project_ids or [])
    row.status = "approved"
    row.approved_by_id = user.id
    row.device_id = device.id
    row.device_token_encrypted = encrypt_secret(token)
    return device


def deny_enrollment(row: DeviceEnrollment, user: User) -> None:
    _require_pending(row)
    row.status = "denied"
    row.approved_by_id = user.id


# ---------------------------------------------------------------------------------------------
# device auth & permissions
# ---------------------------------------------------------------------------------------------


def device_token_from_header(header: str | None) -> str | None:
    scheme, _, token = (header or "").partition(" ")
    if scheme != "Device" or not token.startswith(TOKEN_PREFIX) or len(token) > 200:
        return None
    return token.strip()


def authenticate_device(db: Session, header: str | None) -> Device:
    token = device_token_from_header(header)
    if not token:
        raise unauthorized("Device token required")
    device = db.scalar(select(Device).where(Device.token_hash == hash_token(token)))
    if device is None:
        raise unauthorized("Unknown device token")
    if device.status != "active":
        raise ApiError(403, "device_disabled", "This device is disabled")
    return device


def can_manage(user: User, device: Device) -> bool:
    """Who may see and change a device: its owner and the instance owner."""
    return user.is_instance_owner or device.owner_id == user.id


def get_device_for(db: Session, user: User, device_id: str) -> Device:
    device = db.get(Device, device_id)
    if device is None or not can_manage(user, device):
        raise not_found("Device")
    return device


def hosted_sources(db: Session, device_id: str) -> list[DataSource]:
    """Every source placed on the device, including soft-deleted ones (their database may still exist)."""
    return list(db.scalars(select(DataSource).where(DataSource.device_id == device_id)))


def hosted_counts(db: Session) -> dict[str, int]:
    """Live (not soft-deleted) sources per device, for `hosted_sources_count`."""
    return dict(
        db.execute(
            select(DataSource.device_id, func.count())
            .where(DataSource.device_id.is_not(None), DataSource.deleted_at.is_(None))
            .group_by(DataSource.device_id)
        ).all()
    )


def device_grants(db: Session, device_id: str) -> list[str]:
    return list(db.scalars(select(DeviceProjectGrant.project_id).where(DeviceProjectGrant.device_id == device_id)))


def engines_of(device: Device) -> dict[str, bool]:
    caps = device.capabilities or {}
    metrics = device.metrics or {}
    engines = metrics.get("engines") or caps.get("engines") or {}
    return {"mariadb": bool(engines.get("mariadb", True)), "mongodb": bool(engines.get("mongodb", False))}


def device_out(db: Session, device: Device, *, hosted: int | None = None, user: User | None = None) -> dict:
    from app.serializers import iso
    from app.services import device_rpc

    owner = db.get(User, device.owner_id)
    if hosted is None:
        hosted = hosted_counts(db).get(device.id, 0)
    metrics = device.metrics or {}
    return {
        "id": device.id,
        "name": device.name,
        "owner_id": device.owner_id,
        "owner_email": owner.email if owner else None,
        "owner_name": owner.display_name if owner else None,
        "status": device.status,
        "roles": list(device.roles or []),
        "sharing_mode": device.sharing_mode,
        "project_ids": device_grants(db, device.id) if device.sharing_mode == "selected" else [],
        "hostname": device.hostname,
        "os": device.os,
        "version": device.version,
        "capabilities": device.capabilities or {},
        "metrics": metrics or None,
        "engines": engines_of(device),
        "online": device.status == "active" and device_rpc.is_online(device.id),
        "last_seen_at": iso(device.last_seen_at),
        "hosted_sources_count": hosted,
        "can_manage": bool(user and can_manage(user, device)),
        "created_at": iso(device.created_at),
    }


# ---------------------------------------------------------------------------------------------
# placement
# ---------------------------------------------------------------------------------------------


def placement_problem(db: Session, device: Device, project: Project, *, role: str = "database_host") -> str | None:
    """None when `device` may serve `project` in `role` (docs/DEVICES.md "Rules"), else the reason:
    the device owner is developer+ in the project and either sharing_mode is my_projects (owner is
    admin/owner there) or the project is explicitly granted. `role="backup_storage"` applies the same
    sharing rules to backup copy targets."""
    if device.status != "active":
        return "Device is disabled"
    if role not in (device.roles or []):
        return f"Device does not have the {role} role"
    member = db.scalar(
        select(ProjectMember).where(ProjectMember.project_id == project.id, ProjectMember.user_id == device.owner_id)
    )
    if member is None or role_rank(member.role) < role_rank("developer"):
        return "The device owner is not a developer (or higher) in this project"
    if device.sharing_mode == "my_projects":
        if role_rank(member.role) < role_rank("admin"):
            return "The device is shared only with projects its owner administers"
        return None
    granted = db.scalar(
        select(DeviceProjectGrant.id).where(
            DeviceProjectGrant.device_id == device.id, DeviceProjectGrant.project_id == project.id
        )
    )
    return None if granted else "The device is not shared with this project"


def device_can_host(db: Session, device: Device, project: Project) -> bool:
    return placement_problem(db, device, project) is None


def _member_devices(db: Session, project: Project) -> list[Device]:
    return list(
        db.scalars(
            select(Device)
            .join(ProjectMember, ProjectMember.user_id == Device.owner_id)
            .where(ProjectMember.project_id == project.id)
            .order_by(Device.name)
        )
    )


def placement_options(db: Session, project: Project) -> list[dict]:
    """Main server first, then every device owned by a project member (with eligibility)."""
    import shutil

    from app.config import get_settings
    from app.services import device_rpc

    try:
        disk_free = shutil.disk_usage("/").free
    except OSError:
        disk_free = None
    out: list[dict] = [
        {
            "device_id": None,
            "name": "Main server",
            "online": True,
            "eligible": True,
            "reason": None,
            "disk_free_bytes": disk_free,
            "engines": {"mariadb": True, "mongodb": bool(get_settings().managed_mongodb_enabled)},
            "roles": ["database_host", "backup_storage"],
        }
    ]
    for device in _member_devices(db, project):
        problem = placement_problem(db, device, project)
        online = device.status == "active" and device_rpc.is_online(device.id)
        out.append(
            {
                "device_id": device.id,
                "name": device.name,
                "online": online,
                "eligible": problem is None,
                "reason": problem or (None if online else "Device is offline"),
                "disk_free_bytes": (device.metrics or {}).get("disk_free_bytes"),
                "engines": engines_of(device),
                "roles": list(device.roles or []),
            }
        )
    return out


def validate_placement(db: Session, project: Project, device_id: str | None, kind: str | None = None) -> Device | None:
    """Returns the target device (None = main server) or raises if it may not host this project."""
    if not device_id:
        return None
    device = db.get(Device, device_id)
    if device is None or not device_can_host(db, device, project):
        raise ApiError(422, "device_not_eligible", "That device can't host databases for this project")
    if kind == "nosql" and not engines_of(device)["mongodb"]:
        raise ApiError(
            409, "managed_mongodb_unavailable", f"Managed MongoDB is not available on device '{device.name}'"
        )
    return device
