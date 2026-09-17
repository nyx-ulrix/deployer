"""Diff two `SourceSchema` dicts (docs/BACKUPS.md "Version history", `SchemaDiff`). Pure functions."""

from __future__ import annotations

from typing import Any

# Field attributes that count as a change. Mongo `occurrence` is sampled and noisy, so it is ignored.
FIELD_KEYS = ("data_type", "nullable", "default", "primary_key", "unique", "indexed", "foreign_key")


def _by_name(items: list[dict] | None) -> dict[str, dict]:
    return {str(item.get("name")): item for item in (items or []) if isinstance(item, dict)}


def _field_view(field: dict | None) -> dict | None:
    if field is None:
        return None
    return {"name": field.get("name"), **{k: field.get(k) for k in FIELD_KEYS}, "occurrence": field.get("occurrence")}


def _index_view(index: dict) -> tuple:
    return (tuple(index.get("fields") or []), bool(index.get("unique")))


def diff_entities(before: dict | None, after: dict | None) -> dict | None:
    """Returns the entity entry, or None when nothing changed."""
    name = (after or before or {}).get("name")
    if before is None and after is None:
        return None
    fields_before, fields_after = _by_name((before or {}).get("fields")), _by_name((after or {}).get("fields"))
    fields: list[dict] = []
    for fname in sorted(set(fields_before) | set(fields_after)):
        fb, fa = fields_before.get(fname), fields_after.get(fname)
        if fb is None:
            change = "added"
        elif fa is None:
            change = "removed"
        elif any(fb.get(k) != fa.get(k) for k in FIELD_KEYS):
            change = "changed"
        else:
            continue
        fields.append({"name": fname, "change": change, "before": _field_view(fb), "after": _field_view(fa)})

    idx_before, idx_after = _by_name((before or {}).get("indexes")), _by_name((after or {}).get("indexes"))
    indexes: list[dict] = []
    for iname in sorted(set(idx_before) | set(idx_after)):
        ib, ia = idx_before.get(iname), idx_after.get(iname)
        if ib is None:
            indexes.append({"name": iname, "change": "added"})
        elif ia is None:
            indexes.append({"name": iname, "change": "removed"})
        elif _index_view(ib) != _index_view(ia):
            indexes.append({"name": iname, "change": "changed"})

    validator_changed = (before or {}).get("validator") != (after or {}).get("validator")
    rc_before = before.get("row_count") if before else None
    rc_after = after.get("row_count") if after else None

    if before is None:
        change = "added"
    elif after is None:
        change = "removed"
    elif fields or indexes or validator_changed or rc_before != rc_after:
        change = "changed"
    else:
        return None
    return {
        "name": name,
        "change": change,
        "fields": fields,
        "indexes": indexes,
        "validator_changed": bool(validator_changed and before is not None and after is not None),
        "row_count": {"before": rc_before, "after": rc_after},
    }


def apply_row_counts(schema: dict | None, row_counts: dict[str, Any] | None) -> dict | None:
    """Overrides the (often estimated) entity row counts with exact counts recorded for a snapshot."""
    if not schema or not row_counts:
        return schema
    out = dict(schema)
    out["entities"] = [
        {**entity, "row_count": int(row_counts[entity.get("name")])}
        if isinstance(row_counts.get(entity.get("name")), int)
        else entity
        for entity in schema.get("entities") or []
    ]
    return out


def diff_schemas(before: dict | None, after: dict | None) -> list[dict]:
    """Entity-level changes from `before` to `after`, sorted by entity name."""
    eb, ea = _by_name((before or {}).get("entities")), _by_name((after or {}).get("entities"))
    out = []
    for name in sorted(set(eb) | set(ea)):
        entry = diff_entities(eb.get(name), ea.get(name))
        if entry is not None:
            out.append(entry)
    return out
