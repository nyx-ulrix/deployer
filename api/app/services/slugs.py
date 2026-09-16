"""Project slugs: `^[a-z][a-z0-9-]{2,62}$`, unique across the instance."""

import re
import secrets
import string
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Project

SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{2,62}$")
_SUFFIX_LEN = 6
_MAX_BASE = 63 - 1 - _SUFFIX_LEN
_ALPHABET = string.ascii_lowercase + string.digits


def slugify(name: str) -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    if not slug:
        slug = "project"
    elif not slug[0].isalpha():
        slug = f"project-{slug}"
    slug = slug[:_MAX_BASE].rstrip("-")
    if len(slug) < 3:
        slug = f"{slug}-project"
    return slug


def _random_suffix() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(_SUFFIX_LEN))


def unique_slug(db: Session, name: str) -> str:
    base = slugify(name)
    candidate = base
    for _ in range(50):
        if db.scalar(select(Project.id).where(Project.slug == candidate)) is None:
            return candidate
        candidate = f"{base}-{_random_suffix()}"
    raise RuntimeError("Could not generate a unique project slug")
