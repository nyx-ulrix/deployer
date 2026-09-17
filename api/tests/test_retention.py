"""GFS retention and log-segment pruning with a compressed clock (pure functions of app.services.backups)."""

from datetime import datetime, timedelta

from app.models import Backup, BackupLogSegment, BackupPolicy, new_id
from app.services.backups import gfs_keep, segments_to_prune

START = datetime(2025, 1, 1, 0, 30)


def policy(**kw) -> BackupPolicy:
    values = dict(keep_hourly=24, keep_daily=7, keep_weekly=4, keep_monthly=12, pitr_enabled=True, pitr_window_days=7)
    values.update(kw)
    return BackupPolicy(data_source_id="s", **values)


def snap(at: datetime, trigger="scheduled", **kw) -> Backup:
    seq = int((at - START).total_seconds() // 3600) + 1
    return Backup(
        id=new_id(),
        data_source_id="s",
        scope="source",
        engine="mariadb",
        trigger=trigger,
        status=kw.pop("status", "succeeded"),
        pinned=kw.pop("pinned", False),
        started_at=at,
        consistent_point={"binlog_file": f"mysql-bin.{seq:06d}", "binlog_pos": 4, "consistent_at": at.isoformat()},
        **kw,
    )


def test_gfs_over_400_days_hourly_snapshots():
    pol = policy()
    kept: list[Backup] = []
    pinned = special_safety_old = special_safety_new = None
    now = START
    for hour in range(400 * 24):
        now = START + timedelta(hours=hour)
        kept.append(snap(now))
        if hour == 10 * 24:
            pinned = snap(now + timedelta(minutes=5), trigger="manual", pinned=True, label="before migration")
            kept.append(pinned)
        if hour == 400 * 24 - 40 * 24:
            special_safety_old = snap(now + timedelta(minutes=5), trigger="pre_drop")
            kept.append(special_safety_old)
        if hour == 400 * 24 - 20 * 24:
            special_safety_new = snap(now + timedelta(minutes=5), trigger="pre_restore")
            kept.append(special_safety_new)
        keep = gfs_keep(kept, pol, now + timedelta(minutes=10))
        kept = [s for s in kept if s.id in keep]

    ids = {s.id for s in kept}
    assert pinned.id in ids
    assert special_safety_new.id in ids and special_safety_old.id not in ids
    scheduled = sorted((s for s in kept if s.trigger == "scheduled"), key=lambda s: s.started_at, reverse=True)
    times = [s.started_at for s in scheduled]
    # The newest 24 hourly snapshots are all kept.
    assert times[:24] == [now - timedelta(hours=i) for i in range(24)]
    days = {(t.year, t.month, t.day) for t in times}
    months = {(t.year, t.month) for t in times}
    assert len(days) >= 7 and len(months) == 12
    # Never more than one snapshot per bucket combination beyond the limits.
    assert len(scheduled) <= 24 + 7 + 4 + 12
    assert min(times) >= now - timedelta(days=366)


def test_running_recent_failures_and_latest_are_kept():
    now = START + timedelta(days=3)
    pol = policy(keep_hourly=0, keep_daily=0, keep_weekly=0, keep_monthly=0)
    old = snap(START)
    newest = snap(now - timedelta(hours=1))
    running = snap(now, status="running")
    failed_recent = snap(now - timedelta(hours=2), status="failed")
    failed_old = snap(now - timedelta(days=2), status="failed")
    keep = gfs_keep([old, newest, running, failed_recent, failed_old], pol, now)
    assert set(keep) == {newest.id, running.id, failed_recent.id}
    assert keep[newest.id] == "latest"


def seg(first: int, last: int, end_at: datetime, *, gap: bool = False) -> BackupLogSegment:
    start = {"binlog_file": f"mysql-bin.{first:06d}"}
    if gap:
        start["gap"] = True
    return BackupLogSegment(
        id=new_id(),
        data_source_id="s",
        kind="binlog",
        start_at=end_at - timedelta(minutes=5),
        end_at=end_at,
        start_point=start,
        end_point={"binlog_file": f"mysql-bin.{last:06d}"},
        size_bytes=10,
        created_at=end_at,
    )


def test_segments_kept_for_pitr_window_from_the_base_snapshot():
    now = START + timedelta(days=30)
    pol = policy(pitr_window_days=7)
    # Daily snapshots; binlog file numbers follow the hour offset used by snap().
    snaps = [snap(START + timedelta(days=d)) for d in range(0, 30, 1)]
    segments = [seg(h, h, START + timedelta(hours=h)) for h in range(1, 30 * 24)]
    prune = segments_to_prune(snaps, segments, pol, now)
    window_start = now - timedelta(days=7)
    base = max(s.started_at for s in snaps if s.started_at <= window_start)
    base_seq = int((base - START).total_seconds() // 3600) + 1
    pruned_seqs = {int(s.start_point["binlog_file"][-6:]) for s in prune}
    assert pruned_seqs == set(range(1, base_seq))
    # PITR disabled -> every segment goes; no usable snapshot -> nothing is pruned.
    assert len(segments_to_prune(snaps, segments, policy(pitr_enabled=False), now)) == len(segments)
    assert segments_to_prune([], segments, pol, now) == []
