"""Host devices on the main Deployer (docs/DEVICES.md).

User endpoints (bearer): enrollment lookup/approval, device management, placement options, moving
a database between hosts. Device endpoints (`Authorization: Device <token>` only): enrollment
create/poll (unauthenticated device flow), the control WebSocket and bulk transfers.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import threading
import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.db import get_sessionmaker
from app.deps import CurrentUser, DbSession, ProjectAccess, client_ip, require_role
from app.errors import ApiError, forbidden, not_found
from app.models import DataSource, Device, DeviceEnrollment, Job, User, utcnow
from app.services import audit, device_executor, device_moves, device_rpc, devices, jobs, rate_limit
from app.services.instance_settings import public_url
from app.services.sources import get_source

router = APIRouter(tags=["devices"])
log = logging.getLogger(__name__)
# Backups for device-hosted databases in the API process. Registered at startup (not import) so the
# process-wide hooks don't leak into code that merely imports the app (e.g. unit tests).
router.add_event_handler("startup", device_executor.register)
router.add_event_handler("shutdown", device_executor.unregister)

Admin = Annotated[ProjectAccess, Depends(require_role("admin"))]

MAX_TRANSFER_BYTES = int(os.environ.get("DEVICE_MAX_TRANSFER_BYTES") or 64 * 1024**3)
HELLO_TIMEOUT_SECONDS = 20
CALL_QUEUE_SIZE = 64


# =============================================================================================
# enrollment (device flow)
# =============================================================================================


class EnrollmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    hostname: str | None = Field(default=None, max_length=255)
    os: str | None = Field(default=None, max_length=120)
    version: str | None = Field(default=None, max_length=32)
    capabilities: dict[str, Any] | None = None


class EnrollmentPoll(BaseModel):
    poll_secret: str = Field(min_length=1, max_length=200)


class EnrollmentApprove(BaseModel):
    user_code: str | None = None
    name: str | None = Field(default=None, max_length=80)
    roles: list[Literal["database_host", "backup_storage"]] | None = None
    sharing_mode: Literal["my_projects", "selected"] = "my_projects"
    project_ids: list[str] = Field(default_factory=list, max_length=1000)


class EnrollmentDeny(BaseModel):
    user_code: str | None = None


@router.post("/devices/enrollments")
def create_enrollment(body: EnrollmentCreate, request: Request, db: DbSession) -> dict:
    allowed, retry_after = rate_limit.hit(f"rl:device-enroll:{client_ip(request) or '-'}", 20, 3600)
    if not allowed:
        raise ApiError(429, "rate_limited", "Too many enrollment attempts", {"retry_after": retry_after})
    row, poll_secret = devices.create_enrollment(
        db,
        name=body.name,
        hostname=body.hostname,
        os=body.os,
        version=body.version,
        capabilities=body.capabilities,
    )
    audit.record(db, "device.enrollment_create", request=request, enrollment_id=row.id, name=row.name)
    db.commit()
    return {
        "enrollment_id": row.id,
        "user_code": row.user_code,
        "verification_uri": f"{public_url(db)}/devices/approve?code={row.user_code}",
        "poll_secret": poll_secret,
        "expires_in": devices.ENROLLMENT_TTL_SECONDS,
        "interval": devices.POLL_INTERVAL_SECONDS,
    }


@router.post("/devices/enrollments/{enrollment_id}/poll")
def poll_enrollment(enrollment_id: str, body: EnrollmentPoll, db: DbSession) -> dict:
    result = devices.poll_enrollment(db, enrollment_id, body.poll_secret)
    db.commit()
    return result


def _lookup_rate_limit(user: User) -> None:
    allowed, retry_after = rate_limit.hit(f"rl:device-code:{user.id}", 30, 600)
    if not allowed:
        raise ApiError(429, "rate_limited", "Too many code lookups", {"retry_after": retry_after})


@router.get("/devices/enrollments")
def enrollment_by_code_query(user: CurrentUser, db: DbSession, code: str = Query(max_length=20)) -> dict:
    _lookup_rate_limit(user)
    row = devices.enrollment_by_code(db, code)
    db.commit()
    return devices.enrollment_out(row)


@router.get("/devices/enrollments/by-code/{code}")
def enrollment_by_code(code: str, user: CurrentUser, db: DbSession) -> dict:
    return enrollment_by_code_query(user, db, code)


def _enrollment_for_action(db: DbSession, enrollment_id: str, user_code: str | None) -> DeviceEnrollment:
    row = db.get(DeviceEnrollment, enrollment_id)
    if row is None:
        raise not_found("Enrollment")
    if user_code is not None and devices.normalize_user_code(user_code) != row.user_code:
        raise not_found("Enrollment")
    return row


@router.post("/devices/enrollments/{enrollment_id}/approve")
def approve_enrollment(
    enrollment_id: str, body: EnrollmentApprove, user: CurrentUser, db: DbSession, request: Request
) -> dict:
    row = _enrollment_for_action(db, enrollment_id, body.user_code)
    device = devices.approve_enrollment(
        db,
        row,
        user,
        name=body.name,
        roles=body.roles,
        sharing_mode=body.sharing_mode,
        project_ids=body.project_ids,
    )
    audit.record(
        db,
        "device.approve",
        request=request,
        user_id=user.id,
        device_id=device.id,
        name=device.name,
        roles=device.roles,
        sharing_mode=device.sharing_mode,
    )
    db.commit()
    return devices.device_out(db, device, hosted=0, user=user)


@router.post("/devices/enrollments/{enrollment_id}/deny")
def deny_enrollment(
    enrollment_id: str, user: CurrentUser, db: DbSession, request: Request, body: EnrollmentDeny | None = None
) -> dict:
    row = _enrollment_for_action(db, enrollment_id, body.user_code if body else None)
    devices.deny_enrollment(row, user)
    audit.record(db, "device.deny", request=request, user_id=user.id, enrollment_id=row.id)
    db.commit()
    return {"ok": True}


# =============================================================================================
# device management (users)
# =============================================================================================


class DeviceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    roles: list[Literal["database_host", "backup_storage"]] | None = None
    sharing_mode: Literal["my_projects", "selected"] | None = None
    project_ids: list[str] | None = Field(default=None, max_length=1000)
    status: Literal["active", "disabled"] | None = None


@router.get("/devices")
def list_devices(user: CurrentUser, db: DbSession, scope: Literal["mine", "all"] = "mine") -> list[dict]:
    stmt = select(Device).order_by(Device.created_at)
    if scope != "all" or not user.is_instance_owner:
        stmt = stmt.where(Device.owner_id == user.id)
    counts = devices.hosted_counts(db)
    return [devices.device_out(db, d, hosted=counts.get(d.id, 0), user=user) for d in db.scalars(stmt)]


@router.get("/devices/{device_id}")
def get_device(device_id: str, user: CurrentUser, db: DbSession) -> dict:
    device = devices.get_device_for(db, user, device_id)
    return devices.device_out(db, device, user=user)


@router.patch("/devices/{device_id}")
def update_device(device_id: str, body: DeviceUpdate, user: CurrentUser, db: DbSession, request: Request) -> dict:
    device = devices.get_device_for(db, user, device_id)
    fields = body.model_fields_set
    if not devices.can_manage(user, device):
        raise forbidden("Only the device owner or the instance owner can change this device")
    if "status" in fields and body.status is not None and body.status != device.status:
        if not user.is_instance_owner:
            raise forbidden("Only the instance owner can disable or enable devices")
        device.status = body.status
    if "name" in fields and body.name:
        device.name = body.name.strip()[:80] or device.name
    if "roles" in fields and body.roles is not None:
        device.roles = devices.normalize_roles(body.roles)
    if "sharing_mode" in fields and body.sharing_mode:
        device.sharing_mode = body.sharing_mode
    if "project_ids" in fields and body.project_ids is not None:
        devices.set_grants(db, device, user, body.project_ids)
    audit.record(
        db,
        "device.update",
        request=request,
        user_id=user.id,
        device_id=device.id,
        fields=sorted(fields),
    )
    db.commit()
    if device.status != "active":
        device_rpc.publish_control(device.id, "close", reason="disabled")
    return devices.device_out(db, device, user=user)


@router.delete("/devices/{device_id}")
def remove_device(device_id: str, user: CurrentUser, db: DbSession, request: Request, force: bool = False) -> dict:
    device = devices.get_device_for(db, user, device_id)
    if not devices.can_manage(user, device):
        raise forbidden("Only the device owner or the instance owner can remove this device")
    hosted = devices.hosted_sources(db, device.id)
    active = [ds for ds in hosted if ds.deleted_at is None]
    if active and not force:
        raise ApiError(
            409,
            "device_in_use",
            "This device still hosts databases. Move them to another host first.",
            {"data_sources": [{"id": ds.id, "project_id": ds.project_id, "name": ds.name} for ds in active]},
        )
    if force and active and not user.is_instance_owner:
        raise forbidden("Only the instance owner can force-remove a device that hosts databases")
    for ds in hosted:
        ds.status = "error"
        ds.status_message = "device removed"
        ds.device_id = None
    if not active and device_rpc.is_online(device.id):
        try:
            # Old copies of databases moved away are only kept for rollback; the device is leaving.
            device_moves.drop_copies_on_device(device.id)
            device_rpc.call(device.id, "device.detach", {}, timeout=15)
        except ApiError as exc:
            log.info("device %s did not detach cleanly: %s", device.id, exc.message)
    audit.record(
        db,
        "device.remove",
        request=request,
        user_id=user.id,
        device_id=device.id,
        name=device.name,
        forced=bool(force and active),
        orphaned_sources=[ds.id for ds in active],
    )
    db.delete(device)
    db.commit()
    device_rpc.publish_control(device_id, "close", reason="removed")
    return {"ok": True}


# =============================================================================================
# placement & moving databases
# =============================================================================================


class MoveInput(BaseModel):
    device_id: str | None = None


@router.get("/projects/{project_id}/placement-options")
def placement_options(access: Admin, db: DbSession) -> list[dict]:
    return devices.placement_options(db, access.project)


@router.post("/projects/{project_id}/data-sources/{source_id}/move")
def move_data_source(source_id: str, body: MoveInput, access: Admin, db: DbSession, request: Request) -> dict:
    ds = get_source(db, access.project.id, source_id)  # soft-deleted sources are already 404 here
    if ds.mode != "managed":
        raise ApiError(400, "not_managed", "Only managed databases can be moved between hosts")
    target = body.device_id or None
    if (ds.device_id or None) == target:
        raise ApiError(409, "already_there", "The database is already hosted there")
    devices.validate_placement(db, access.project, target, ds.kind)
    for dev in {ds.device_id, target} - {None}:
        if not device_rpc.is_online(dev):
            raise device_rpc.offline_error("The source or target host device is offline")
    running = db.scalar(
        select(Job.id).where(
            Job.data_source_id == ds.id, Job.type == device_moves.MOVE_JOB, Job.status.in_(("queued", "running"))
        )
    )
    if running:
        raise ApiError(409, "move_in_progress", "This database is already being moved")
    from app.models import SourceReplica

    if db.scalar(select(SourceReplica.id).where(SourceReplica.data_source_id == ds.id)):
        # docs/COHOSTING.md: copies follow the main server's database; remove them before moving it.
        raise ApiError(409, "has_replicas", "Remove this database's co-host copies before moving it")
    job = device_moves.create_move_job(db, ds, target, access.user)
    audit.record(
        db,
        "data_source.move",
        request=request,
        user_id=access.user.id,
        project_id=access.project.id,
        data_source_id=ds.id,
        from_device_id=ds.device_id,
        to_device_id=target,
        job_id=job.id,
    )
    db.commit()
    device_moves.start_move(job.id)
    return {"job": jobs.job_out(job)}


# =============================================================================================
# device authentication helpers
# =============================================================================================


def _authenticate(header: str | None) -> tuple[str, str]:
    session = get_sessionmaker()()
    try:
        device = devices.authenticate_device(session, header)
        return device.id, device.name
    finally:
        session.close()


def require_device(request: Request, db: DbSession) -> Device:
    return devices.authenticate_device(db, request.headers.get("Authorization"))


CurrentDevice = Annotated[Device, Depends(require_device)]


# =============================================================================================
# transfers
# =============================================================================================


def _transfer_for(device_id: str, transfer_id: str, mode: str) -> dict:
    meta = device_rpc.get_transfer(transfer_id)
    if meta is None or meta.get("device_id") != device_id or meta.get("mode") != mode:
        raise not_found("Transfer")
    return meta


@router.put("/devices/transfers/{transfer_id}")
async def upload_transfer(transfer_id: str, request: Request) -> dict:
    device_id, _ = await run_in_threadpool(_authenticate, request.headers.get("Authorization"))
    meta = await run_in_threadpool(_transfer_for, device_id, transfer_id, "put")
    if meta.get("complete"):
        raise ApiError(409, "transfer_complete", "This transfer was already uploaded")
    path = device_rpc.transfer_path(transfer_id)
    tmp = path.with_name(path.name + ".part")
    digest = hashlib.sha256()
    size = 0
    fh = await run_in_threadpool(open, tmp, "wb")
    try:
        async for chunk in request.stream():
            if not chunk:
                continue
            size += len(chunk)
            if size > MAX_TRANSFER_BYTES:
                raise ApiError(413, "file_too_large", "Transfer exceeds the size limit")
            digest.update(chunk)
            await run_in_threadpool(fh.write, chunk)
        await run_in_threadpool(fh.close)
        os.replace(tmp, path)
    except BaseException:
        fh.close()
        tmp.unlink(missing_ok=True)
        raise
    await run_in_threadpool(
        device_rpc.update_transfer, transfer_id, complete=True, size=size, sha256=digest.hexdigest()
    )
    return {"ok": True, "size": size, "sha256": digest.hexdigest()}


@router.get("/devices/transfers/{transfer_id}")
def download_transfer(transfer_id: str, device: CurrentDevice) -> StreamingResponse:
    meta = _transfer_for(device.id, transfer_id, "get")
    path = device_rpc.transfer_path(transfer_id)
    if not path.exists():
        raise not_found("Transfer")
    keep = bool(meta.get("keep"))
    size = path.stat().st_size

    def iterate():
        completed = False
        try:
            with open(path, "rb") as fh:
                while chunk := fh.read(1 << 20):
                    yield chunk
            completed = True
        finally:
            if completed and not keep:
                device_rpc.finish_transfer(transfer_id)

    return StreamingResponse(iterate(), media_type="application/octet-stream", headers={"Content-Length": str(size)})


# =============================================================================================
# control channel
# =============================================================================================


def _record_hello(device_id: str, msg: dict, ip: str | None) -> bool:
    session = get_sessionmaker()()
    try:
        device = session.get(Device, device_id)
        if device is None or device.status != "active":
            return False
        if isinstance(msg.get("version"), str):
            device.version = msg["version"][:32]
        if isinstance(msg.get("capabilities"), dict):
            device.capabilities = msg["capabilities"]
        if isinstance(msg.get("metrics"), dict):
            device.metrics = msg["metrics"]
        if isinstance(msg.get("hostname"), str) and msg["hostname"]:
            device.hostname = msg["hostname"][:255]
        device.last_seen_at = utcnow()
        session.commit()
        return True
    finally:
        session.close()


def _record_heartbeat(device_id: str, metrics: Any) -> bool:
    session = get_sessionmaker()()
    try:
        device = session.get(Device, device_id)
        if device is None or device.status != "active":
            return False
        if isinstance(metrics, dict):
            device.metrics = metrics
        device.last_seen_at = utcnow()
        session.commit()
        return True
    finally:
        session.close()


def _record_progress(device_id: str, msg: dict) -> None:
    job_id = msg.get("job_id")
    if not isinstance(job_id, str):
        return
    session = get_sessionmaker()()
    try:
        job = session.get(Job, job_id)
        if job is None or job.status not in ("queued", "running"):
            return
        if job.device_id != device_id:
            source = session.get(DataSource, job.data_source_id) if job.data_source_id else None
            if source is None or source.device_id != device_id:
                return
        try:
            job.progress = max(0.0, min(1.0, float(msg.get("progress") or 0.0)))
        except (TypeError, ValueError):
            pass
        if isinstance(msg.get("message"), str):
            job.message = msg["message"][:1000]
        session.commit()
    finally:
        session.close()


def _record_disconnect(device_id: str) -> None:
    session = get_sessionmaker()()
    try:
        device = session.get(Device, device_id)
        if device is not None:
            device.last_seen_at = utcnow()
            session.commit()
    except Exception:  # noqa: BLE001
        log.debug("could not record device disconnect", exc_info=True)
    finally:
        session.close()


async def _deny(websocket: WebSocket, status: int, code: str, message: str) -> None:
    try:
        await websocket.send_denial_response(
            JSONResponse(status_code=status, content={"error": {"code": code, "message": message, "details": {}}})
        )
    except Exception:  # noqa: BLE001 - server without the denial-response extension
        await websocket.close(code=4000 + status)


@router.websocket("/devices/connect")
async def device_connect(websocket: WebSocket) -> None:
    try:
        device_id, _name = await run_in_threadpool(_authenticate, websocket.headers.get("authorization"))
    except ApiError as exc:
        await _deny(websocket, exc.status_code, exc.code, exc.message)
        return
    await websocket.accept()
    conn_id = uuid.uuid4().hex
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=CALL_QUEUE_SIZE)
    ip = websocket.client.host if websocket.client else None

    def enqueue(data: str | None) -> None:
        try:
            queue.put_nowait(data)
        except asyncio.QueueFull:
            try:
                call_id = json.loads(data or "{}").get("id")
            except ValueError:
                call_id = None
            if call_id:
                loop.run_in_executor(
                    None,
                    device_rpc.publish_reply,
                    call_id,
                    {"ok": False, "error": {"status": 503, "code": "device_busy", "message": "Device is busy"}},
                )

    # Replace any older connection of the same device, then start listening for calls.
    await run_in_threadpool(device_rpc.publish_control, device_id, "close", reason="replaced", except_conn=conn_id)
    listener = await run_in_threadpool(
        device_rpc.CallListener, device_id, lambda data: loop.call_soon_threadsafe(enqueue, data)
    )
    listener.start()
    close_code = 1000
    try:
        try:
            raw = await asyncio.wait_for(websocket.receive_text(), timeout=HELLO_TIMEOUT_SECONDS)
            hello = json.loads(raw)
        except (TimeoutError, ValueError):
            await websocket.close(code=1008)
            return
        if not isinstance(hello, dict) or hello.get("type") != "hello":
            await websocket.close(code=1008)
            return
        if not await run_in_threadpool(_record_hello, device_id, hello, ip):
            await websocket.close(code=4403)
            return
        await run_in_threadpool(device_rpc.mark_online, device_id, conn_id)

        async def forward_calls() -> int:
            while True:
                data = await queue.get()
                if data is None:
                    return 1011
                try:
                    msg = json.loads(data)
                except ValueError:
                    continue
                if msg.get("type") == "control":
                    if msg.get("action") == "close" and msg.get("except_conn") != conn_id:
                        return 4403 if msg.get("reason") in ("disabled", "removed") else 4000
                    continue
                if msg.get("type") == "call":
                    await websocket.send_text(data)

        async def receive_messages() -> int:
            while True:
                try:
                    raw = await asyncio.wait_for(websocket.receive_text(), timeout=device_rpc.ONLINE_TTL_SECONDS)
                except TimeoutError:
                    return 4408
                if len(raw) > device_rpc.MAX_MESSAGE_BYTES:
                    return 1009
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue
                if not isinstance(msg, dict):
                    continue
                kind = msg.get("type")
                if kind == "heartbeat":
                    if not await run_in_threadpool(_record_heartbeat, device_id, msg.get("metrics")):
                        return 4403
                    await run_in_threadpool(device_rpc.mark_online, device_id, conn_id)
                elif kind == "result" and isinstance(msg.get("id"), str):
                    reply = {"ok": bool(msg.get("ok"))}
                    reply["result" if reply["ok"] else "error"] = msg.get("result" if reply["ok"] else "error")
                    await run_in_threadpool(device_rpc.publish_reply, msg["id"][:64], reply)
                elif kind == "progress" and isinstance(msg.get("job_id"), str):
                    progress_id = msg["job_id"][:64]
                    await run_in_threadpool(
                        device_rpc.publish_progress,
                        f"{device_id}:{progress_id}",
                        msg.get("progress"),
                        msg.get("message"),
                    )
                    await run_in_threadpool(_record_progress, device_id, msg)

        tasks = [asyncio.create_task(forward_calls()), asyncio.create_task(receive_messages())]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        for task in done:
            exc = task.exception()
            if exc is None:
                close_code = task.result()
            elif not isinstance(exc, WebSocketDisconnect):
                log.warning("device %s connection error: %s", device_id, exc)
                close_code = 1011
            else:
                close_code = 0
        if close_code:
            try:
                await websocket.close(code=close_code)
            except Exception:  # noqa: BLE001
                pass
    except WebSocketDisconnect:
        pass
    finally:
        # No awaits here: this block also runs while the task is being cancelled (server shutdown,
        # client teardown) and an awaited cleanup could be skipped, leaving the device "online".
        listener.stop()
        device_rpc.mark_offline(device_id, conn_id)
        threading.Thread(target=_record_disconnect, args=(device_id,), daemon=True).start()
