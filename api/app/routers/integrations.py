"""The signed-in user's GitHub connection (docs/DEPLOYMENTS.md "Connect a Git repository")."""

from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from app.deps import CurrentUser, DbSession
from app.services import audit, github, oauth

router = APIRouter(tags=["integrations"])


@router.get("/integrations/github")
def github_status(user: CurrentUser, db: DbSession) -> dict:
    return github.status_out(db, user.id)


@router.post("/integrations/github/connect")
def github_connect(response: Response, user: CurrentUser, db: DbSession) -> dict:
    url, nonce = oauth.begin(
        db, "github", intent="github_connect", redirect=None, user_id=user.id, scope=github.CONNECT_SCOPE
    )
    # Sent with this same-origin fetch; the browser presents it on GitHub's redirect back.
    oauth.set_browser_cookie(response, db, nonce)
    return {"url": url}


@router.delete("/integrations/github")
def github_disconnect(request: Request, user: CurrentUser, db: DbSession) -> dict:
    conn = github.get_connection(db, user.id)
    apps = github.apps_using(db, user.id)
    if conn is not None:
        db.delete(conn)
        audit.record(db, "github.disconnect", request=request, user_id=user.id, login=conn.github_login)
        db.commit()
    return {"ok": True, "apps_using_connection": apps, "message": github.REVOKE_HINT}


@router.get("/integrations/github/repos")
def github_repos(
    user: CurrentUser,
    db: DbSession,
    q: Annotated[str, Query(max_length=100)] = "",
    page: Annotated[int, Query(ge=1, le=50)] = 1,
) -> list[dict]:
    return github.list_repos(github.require_token(db, user.id), q, page)
