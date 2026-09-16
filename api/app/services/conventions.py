"""Schema convention checks (docs/CONVENTIONS.md rules N1-N6, S1-S8, X1-X3).

Everything here is a pure function over the `SourceSchema` / `SchemaLink` dicts described in
docs/API.md, so it can be unit-tested without any database.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

# --------------------------------------------------------------------------------------------
# English inflection heuristics (deliberately simple)
# --------------------------------------------------------------------------------------------

UNCOUNTABLE = {
    "data",
    "metadata",
    "media",
    "information",
    "equipment",
    "news",
    "series",
    "species",
    "feedback",
    "software",
    "hardware",
    "staff",
    "audio",
    "video",
    "music",
    "money",
    "rice",
    "sheep",
    "fish",
    "deer",
    "aircraft",
    "inventory",
    "analytics",
    "auth",
    "history",
    "traffic",
    "content",
    "advice",
    "evidence",
    "knowledge",
    "luggage",
    "furniture",
    "weather",
    "cache",
    "stock",
}

IRREGULAR_PLURALS = {
    "person": "people",
    "child": "children",
    "man": "men",
    "woman": "women",
    "mouse": "mice",
    "goose": "geese",
    "foot": "feet",
    "tooth": "teeth",
    "ox": "oxen",
    "datum": "data",
    "medium": "media",
    "analysis": "analyses",
    "index": "indices",
    "matrix": "matrices",
    "vertex": "vertices",
    "criterion": "criteria",
    "leaf": "leaves",
    "life": "lives",
    "knife": "knives",
    "wife": "wives",
    "half": "halves",
    "shelf": "shelves",
}
IRREGULAR_SINGULARS = {v: k for k, v in IRREGULAR_PLURALS.items()}

_WORD_SPLIT = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|[_\-\s.]+")


def _last_word(name: str) -> tuple[str, str]:
    """Splits "order_items" -> ("order_", "items"), "orderItems" -> ("order", "Items")."""
    parts = [p for p in _WORD_SPLIT.split(name) if p]
    if not parts:
        return "", name
    last = parts[-1]
    idx = name.rfind(last)
    return name[:idx], last


def _match_case(template: str, word: str) -> str:
    if template.isupper() and len(template) > 1:
        return word.upper()
    if template[:1].isupper():
        return word[:1].upper() + word[1:]
    return word


def pluralize(name: str) -> str:
    prefix, word = _last_word(name)
    lower = word.lower()
    if not lower:
        return name
    if lower in UNCOUNTABLE or lower in IRREGULAR_SINGULARS:
        return name
    if lower in IRREGULAR_PLURALS:
        return prefix + _match_case(word, IRREGULAR_PLURALS[lower])
    if re.search(r"[^aeiou]y$", lower):
        plural = lower[:-1] + "ies"
    elif re.search(r"(s|x|z|ch|sh)$", lower):
        plural = lower + "es"
    else:
        plural = lower + "s"
    return prefix + _match_case(word, plural)


def singularize(name: str) -> str:
    prefix, word = _last_word(name)
    lower = word.lower()
    if not lower or lower in UNCOUNTABLE:
        return name
    if lower in IRREGULAR_SINGULARS:
        return prefix + _match_case(word, IRREGULAR_SINGULARS[lower])
    if lower in IRREGULAR_PLURALS:
        return name
    if lower.endswith("ies") and len(lower) > 3:
        single = lower[:-3] + "y"
    elif re.search(r"(sses|xes|zzes|ches|shes|uses)$", lower):
        single = lower[:-2]
    elif lower.endswith("s") and not re.search(r"(ss|us|is)$", lower):
        single = lower[:-1]
    else:
        return name
    return prefix + _match_case(word, single)


def is_plural(name: str) -> bool:
    _, word = _last_word(name)
    lower = word.lower()
    if not lower:
        return True
    if lower in UNCOUNTABLE or lower in IRREGULAR_SINGULARS:
        return True
    if lower in IRREGULAR_PLURALS:
        return False
    return lower.endswith("s") and not re.search(r"(ss|us|is)$", lower)


def plural_candidates(singular: str) -> set[str]:
    """Entity names a `<singular>_id` reference may point to."""
    return {singular, pluralize(singular), singular + "s"}


REFERENCE_SUFFIX = re.compile(r"^(?P<base>.+?)(?:_id|Id|ID)$")


def reference_base(field_name: str) -> str | None:
    """`user_id` / `userId` -> `user`; nested paths use the last segment. `id` / `_id` -> None."""
    last = field_name.rsplit(".", 1)[-1]
    if last in ("id", "_id", "Id", "ID"):
        return None
    m = REFERENCE_SUFFIX.match(last)
    if not m:
        return None
    base = m.group("base").rstrip("_")
    return base or None


def match_entity(field_name: str, entity_names: Iterable[str], *, snake_only: bool = False) -> str | None:
    """Returns the entity that a `<singular>_id` (or `<singular>Id`) field refers to, if any."""
    last = field_name.rsplit(".", 1)[-1]
    if snake_only and not last.endswith("_id"):
        return None
    base = reference_base(field_name)
    if base is None:
        return None
    names = list(entity_names)
    lookup = {n.lower(): n for n in names}
    candidates = plural_candidates(base) | plural_candidates(base.lower())
    # camelCase base ("orderItem") also matches snake_case entity names ("order_items").
    snake = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", base).lower()
    candidates |= plural_candidates(snake)
    for cand in candidates:
        if cand.lower() in lookup:
            return lookup[cand.lower()]
    return None


# --------------------------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------------------------

SNAKE_CASE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")

SQL_RESERVED_WORDS = frozenset(
    """
    accessible add all alter analyze and as asc asensitive before between bigint binary blob both by
    call cascade case change char character check collate column condition constraint continue convert
    create cross current_date current_time current_timestamp current_user cursor database databases
    day_hour day_microsecond day_minute day_second dec decimal declare default delayed delete desc
    describe deterministic distinct distinctrow div do double drop dual each else elseif enclosed
    end escaped except exists exit explain false fetch float for force foreign from fulltext grant
    group having high_priority hour_microsecond hour_minute hour_second if ignore in index infile
    inner inout insensitive insert int integer intersect interval into is iterate join key keys kill
    lateral leading leave left like limit linear lines load localtime localtimestamp lock long
    longblob longtext loop low_priority match mediumblob mediumint mediumtext minute_microsecond
    minute_second mod modifies natural not null numeric offset on optimize option optionally or
    order out outer outfile over partition precision primary procedure purge range read reads real
    recursive references regexp release rename repeat replace require restrict return returning
    revoke right rlike rows schema schemas select sensitive separator set show signal smallint
    spatial specific sql sqlexception sqlstate sqlwarning ssl starting straight_join table
    terminated then tinyblob tinyint tinytext to trailing trigger true undo union unique unlock
    unsigned update usage use using utc_date utc_time utc_timestamp values varbinary varchar
    varcharacter varying when where while window with write xor year_month zerofill
    analyse array asymmetric authorization both collation concurrently current_catalog
    current_role current_schema deferrable do freeze full ilike initially isnull notnull only
    overlaps placing session_user similar some symmetric user variadic verbose
    """.split()
)

BOOLEAN_PREFIXES = ("is_", "has_", "can_")
TIMESTAMP_FIELDS = ("created_at", "updated_at")


def _issue(
    rule: str, severity: str, source_id: str | None, entity: str | None, field: str | None, message: str
) -> dict:
    return {
        "rule": rule,
        "severity": severity,
        "source_id": source_id,
        "entity": entity,
        "field": field,
        "message": message,
    }


def split_type_union(data_type: str) -> list[str]:
    """Splits "int|array<int|string>|null" on top-level `|` only."""
    parts, depth, cur = [], 0, []
    for ch in data_type:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth = max(0, depth - 1)
        if ch == "|" and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]


def is_boolean_type(data_type: str, kind: str) -> bool:
    t = (data_type or "").strip().lower()
    if kind == "nosql":
        return t in ("bool", "boolean")
    return t in ("tinyint(1)", "tinyint(1) unsigned", "boolean", "bool", "bit(1)", "bit")


def _field_is_indexed(field: dict) -> bool:
    return bool(field.get("indexed") or field.get("primary_key") or field.get("unique"))


def check_naming(source: dict) -> list[dict]:
    issues: list[dict] = []
    sid, kind = source.get("source_id"), source.get("kind")
    for entity in source.get("entities", []):
        ename = entity["name"]
        noun = "Table" if entity.get("type") == "table" else "Collection"
        if not SNAKE_CASE.match(ename):
            issues.append(_issue("N1", "warning", sid, ename, None, f"{noun} name '{ename}' is not snake_case"))
        if not is_plural(ename):
            issues.append(
                _issue(
                    "N2",
                    "info",
                    sid,
                    ename,
                    None,
                    f"{noun} name '{ename}' should be plural (e.g. '{pluralize(ename)}')",
                )
            )
        if kind == "sql" and ename.lower() in SQL_RESERVED_WORDS:
            issues.append(_issue("N4", "warning", sid, ename, None, f"{noun} name '{ename}' is an SQL reserved word"))
        for field in entity.get("fields", []):
            fname = field["name"]
            if kind == "nosql" and fname == "_id":
                continue
            segments = fname.split(".") if kind == "nosql" else [fname]
            if not all(SNAKE_CASE.match(seg) for seg in segments):
                issues.append(_issue("N3", "warning", sid, ename, fname, f"Field name '{fname}' is not snake_case"))
            if kind == "sql" and fname.lower() in SQL_RESERVED_WORDS:
                issues.append(
                    _issue("N4", "warning", sid, ename, fname, f"Column name '{fname}' is an SQL reserved word")
                )
            if is_boolean_type(field.get("data_type", ""), kind or "sql"):
                last = segments[-1]
                if not last.startswith(BOOLEAN_PREFIXES):
                    issues.append(
                        _issue(
                            "N6",
                            "info",
                            sid,
                            ename,
                            fname,
                            f"Boolean field '{fname}' should start with is_, has_ or can_",
                        )
                    )
            fk = field.get("foreign_key")
            if kind == "sql" and fk and fk.get("field") == "id":
                expected = f"{singularize(fk['entity'])}_id"
                ok_names = {f"{c}_id" for c in _singular_forms(fk["entity"])}
                if fname not in ok_names and not any(fname.endswith("_" + n) for n in ok_names):
                    issues.append(
                        _issue(
                            "N5",
                            "info",
                            sid,
                            ename,
                            fname,
                            f"Foreign-key column '{fname}' references {fk['entity']}.id; name it '{expected}'",
                        )
                    )
    return issues


def _singular_forms(entity: str) -> set[str]:
    forms = {singularize(entity), entity}
    if entity.endswith("s"):
        forms.add(entity[:-1])
    return forms


def check_structure(source: dict) -> list[dict]:
    issues: list[dict] = []
    sid, kind = source.get("source_id"), source.get("kind")
    entities = source.get("entities", [])
    entity_names = [e["name"] for e in entities]
    s4_reported: set[tuple[str, str]] = set()

    for entity in entities:
        ename = entity["name"]
        fields = entity.get("fields", [])
        by_name = {f["name"]: f for f in fields}
        if kind == "sql":
            pk = [f for f in fields if f.get("primary_key")]
            if not pk:
                issues.append(_issue("S1", "warning", sid, ename, None, f"Table '{ename}' has no primary key"))
            elif len(pk) == 1 and pk[0]["name"] != "id":
                issues.append(
                    _issue("S2", "info", sid, ename, pk[0]["name"], f"Primary key of '{ename}' should be named 'id'")
                )
            for f in pk:
                if f.get("nullable"):
                    issues.append(
                        _issue("S6", "warning", sid, ename, f["name"], f"Primary-key column '{f['name']}' is nullable")
                    )
            missing = [t for t in TIMESTAMP_FIELDS if t not in by_name]
            if missing:
                issues.append(
                    _issue("S5", "info", sid, ename, None, f"Table '{ename}' is missing {' and '.join(missing)}")
                )

        for f in fields:
            fname = f["name"]
            if kind == "sql":
                if f.get("foreign_key") and not _field_is_indexed(f):
                    issues.append(
                        _issue("S3", "warning", sid, ename, fname, f"Foreign-key column '{fname}' is not indexed")
                    )
                if not f.get("foreign_key") and not f.get("primary_key"):
                    target = match_entity(fname, entity_names, snake_only=True)
                    if target:
                        issues.append(
                            _issue(
                                "S4",
                                "info",
                                sid,
                                ename,
                                fname,
                                f"Column '{fname}' looks like a reference to '{target}' "
                                "but has no foreign-key constraint",
                            )
                        )
            else:
                if fname != "_id" and not _field_is_indexed(f):
                    target = match_entity(fname, entity_names, snake_only=True)
                    if target:
                        s4_reported.add((ename, fname))
                        issues.append(
                            _issue(
                                "S4",
                                "info",
                                sid,
                                ename,
                                fname,
                                f"Field '{fname}' looks like a reference to '{target}' but is not indexed",
                            )
                        )
                types = [t for t in split_type_union(f.get("data_type") or "") if t != "null"]
                if len(types) > 1:
                    issues.append(
                        _issue(
                            "S7",
                            "warning",
                            sid,
                            ename,
                            fname,
                            f"Field '{fname}' has mixed types across sampled documents ({'|'.join(types)})",
                        )
                    )

    if kind == "nosql":
        entity_map = {e["name"]: e for e in entities}
        for rel in source.get("relationships", []):
            ent = entity_map.get(rel.get("from_entity"))
            if not ent or not rel.get("from_fields"):
                continue
            fname = rel["from_fields"][0]
            if (ent["name"], fname) in s4_reported:
                continue
            field = next((f for f in ent.get("fields", []) if f["name"] == fname), None)
            if field is not None and not _field_is_indexed(field):
                issues.append(
                    _issue(
                        "S8",
                        "info",
                        sid,
                        ent["name"],
                        fname,
                        f"'{ent['name']}' references '{rel['to_entity']}' through '{fname}'; add an index on it",
                    )
                )
    return issues


# --- cross-database links ------------------------------------------------------------------

_INT_SQL = re.compile(r"^(tiny|small|medium|big)?int(eger)?\b|^(small|big)?serial\b|^int[248]\b")


def type_family(data_type: str, kind: str) -> set[str]:
    """Maps a column/field type to coarse families used for compatibility checks (X2)."""
    families: set[str] = set()
    for t in split_type_union(data_type or ""):
        t = t.strip().lower()
        if t == "null" or not t:
            continue
        if kind == "nosql":
            if t in ("int", "long"):
                families |= {"integer", "number"}
            elif t in ("double", "decimal"):
                families.add("number")
            elif t == "string":
                families |= {"string", "uuid", "objectid"}
            elif t == "objectid":
                families.add("objectid")
            elif t in ("bool", "boolean"):
                families.add("bool")
            elif t in ("date", "timestamp"):
                families.add("date")
            elif t in ("bindata", "uuid"):
                families |= {"binary", "uuid"}
            elif t.startswith("array"):
                families.add("array")
            elif t == "object":
                families.add("json")
            else:
                families.add(t)
            continue
        if t in ("tinyint(1)", "boolean", "bool", "bit(1)"):
            families |= {"bool", "integer", "number"}
        elif _INT_SQL.match(t):
            families |= {"integer", "number"}
        elif re.match(r"^(decimal|numeric|float|double|real)", t):
            families.add("number")
        elif re.match(r"^(char|varchar|character|text|tinytext|mediumtext|longtext|enum|set|citext|name)", t):
            families.add("string")
            m = re.match(r"^(char|character|varchar|character varying)\((\d+)\)", t)
            if m and m.group(2) == "36":
                families.add("uuid")
            if m and m.group(2) == "24":
                families.add("objectid")
        elif t == "uuid":
            families |= {"uuid", "string"}
        elif re.match(r"^(date|datetime|timestamp|time)", t):
            families.add("date")
        elif re.match(r"^(binary|varbinary|blob|tinyblob|mediumblob|longblob|bytea)", t):
            families |= {"binary"}
            if re.match(r"^binary\(16\)", t):
                families.add("uuid")
        elif t in ("json", "jsonb"):
            families.add("json")
        else:
            families.add(t)
    return families


def types_compatible(a_type: str, a_kind: str, b_type: str, b_kind: str) -> bool:
    fa, fb = type_family(a_type, a_kind), type_family(b_type, b_kind)
    if not fa or not fb:
        return True  # unknown -> don't warn
    if fa & fb:
        return True
    return False


def _find_field(
    sources: dict[str, dict], source_id: str, entity: str, field: str
) -> tuple[dict | None, dict | None, dict | None]:
    src = sources.get(source_id)
    if src is None:
        return None, None, None
    ent = next((e for e in src.get("entities", []) if e["name"] == entity), None)
    if ent is None:
        return src, None, None
    fld = next((f for f in ent.get("fields", []) if f["name"] == field), None)
    return src, ent, fld


def check_links(sources: list[dict], links: list[dict]) -> list[dict]:
    issues: list[dict] = []
    by_id = {s["source_id"]: s for s in sources}
    for link in links:
        label = f"{link['from_entity']}.{link['from_field']} -> {link['to_entity']}.{link['to_field']}"
        ends = []
        missing = False
        for side in ("from", "to"):
            sid = link[f"{side}_source_id"]
            src, ent, fld = _find_field(by_id, sid, link[f"{side}_entity"], link[f"{side}_field"])
            ends.append((src, ent, fld))
            if src is None:
                missing = True
                issues.append(
                    _issue(
                        "X1",
                        "warning",
                        sid,
                        link[f"{side}_entity"],
                        link[f"{side}_field"],
                        f"Link {label}: data source is not part of this schema",
                    )
                )
            elif src.get("status") == "error":
                missing = True  # can't verify
            elif ent is None or fld is None:
                missing = True
                what = "entity" if ent is None else "field"
                missing_name = link[f"{side}_entity"] if ent is None else link[f"{side}_field"]
                issues.append(
                    _issue(
                        "X1",
                        "warning",
                        sid,
                        link[f"{side}_entity"],
                        link[f"{side}_field"],
                        f"Link {label}: {what} '{missing_name}' does not exist",
                    )
                )
        if missing:
            continue
        (fs, _, ff), (ts, _, tf) = ends
        if not types_compatible(ff.get("data_type", ""), fs.get("kind"), tf.get("data_type", ""), ts.get("kind")):
            issues.append(
                _issue(
                    "X2",
                    "warning",
                    link["from_source_id"],
                    link["from_entity"],
                    link["from_field"],
                    f"Link {label}: types '{ff.get('data_type')}' and '{tf.get('data_type')}' are not compatible",
                )
            )
        card = link.get("cardinality")
        many_sides = {
            "many_to_one": ["from"],
            "one_to_many": ["to"],
            "many_to_many": ["from", "to"],
        }.get(card, [])
        for side in many_sides:
            src, ent, fld = ends[0] if side == "from" else ends[1]
            if not _field_is_indexed(fld):
                issues.append(
                    _issue(
                        "X3",
                        "info",
                        src["source_id"],
                        ent["name"],
                        fld["name"],
                        f"Link {label}: '{ent['name']}.{fld['name']}' is on the many side and is not indexed",
                    )
                )
    return issues


def check_conventions(sources: list[dict], links: list[dict] | None = None) -> list[dict]:
    issues: list[dict] = []
    for source in sources:
        if source.get("status") == "error":
            continue
        issues.extend(check_naming(source))
        issues.extend(check_structure(source))
    issues.extend(check_links(sources, links or []))
    return issues


def issues_by_rule(issues: list[dict[str, Any]]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for i in issues:
        out.setdefault(i["rule"], []).append(i)
    return out
