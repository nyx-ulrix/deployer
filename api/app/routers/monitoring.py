"""Instance monitoring: metrics, alerts, alert webhook test (docs/MONITORING.md). Instance owner only."""

import time
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.deps import DbSession, InstanceOwner
from app.errors import ApiError
from app.services import alerts, audit, metrics
from app.services.instance_settings import get_value, public_url

router = APIRouter(tags=["monitoring"])


@router.get("/instance/metrics")
def get_metrics(owner: InstanceOwner, window: Literal["1h", "6h", "24h"] = "1h") -> dict:
    return metrics.metrics(window)


@router.get("/instance/metrics/summary")
def get_summary(owner: InstanceOwner) -> dict:
    active = alerts.active()
    shown = alerts.visible(active)
    return {
        **metrics.summary(),
        "alerts": {
            "active": len(active),
            "visible": len(shown),
            "critical": sum(1 for a in shown if a["severity"] == "critical"),
            "top": shown[0] if shown else None,
        },
    }


@router.get("/instance/alerts")
def list_alerts(owner: InstanceOwner) -> list[dict]:
    return alerts.active()


@router.post("/instance/alerts/{alert_id}/dismiss")
def dismiss_alert(alert_id: str, owner: InstanceOwner) -> dict:
    return alerts.mute(alert_id[:200], dismissed=True)


class SnoozeBody(BaseModel):
    minutes: int = Field(ge=5, le=7 * 24 * 60)


@router.post("/instance/alerts/{alert_id}/snooze")
def snooze_alert(alert_id: str, body: SnoozeBody, owner: InstanceOwner) -> dict:
    return alerts.mute(alert_id[:200], snooze_minutes=body.minutes)


class WebhookTestBody(BaseModel):
    url: str | None = Field(default=None, max_length=500)  # test an unsaved URL; default: the saved one


@router.post("/instance/alerts/webhook-test")
def test_webhook(body: WebhookTestBody, request: Request, owner: InstanceOwner, db: DbSession) -> dict:
    url = alerts.validate_webhook_url(body.url) if body.url else get_value(db, "alert_webhook_url")
    if not url:
        raise ApiError(422, "validation_error", "Set an alert webhook URL first", {"field": "alert_webhook_url"})
    payload = {
        "alert": "test",
        "severity": "info",
        "message": "Test alert from Deployer: the webhook works.",
        "status": "test",
        "started_at": metrics._iso(time.time()),
        "resolved_at": None,
        "instance": public_url(db),
        "text": "[test] Test alert from Deployer: the webhook works.",
    }
    ok, detail = alerts.post_webhook(str(url), payload)
    audit.record(db, "instance.alert_webhook_test", request=request, user_id=owner.id, ok=ok)
    db.commit()
    return {"ok": ok, "detail": detail}
