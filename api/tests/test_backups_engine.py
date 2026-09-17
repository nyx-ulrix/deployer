"""Pure helpers of app.services.backup_engine (no database servers or tools needed)."""

import struct

import pytest
from bson import Timestamp

from app.services import backup_engine as be


def test_count_insert_rows_ignores_parens_inside_strings():
    line = b"INSERT INTO `t` VALUES (1,'a),(b',NULL),(2,'it\\'s),(x',0x0102),(3,'',_binary 'x');\n"
    assert be.count_insert_rows(line) == ("t", 3)
    assert be.count_insert_rows(b"INSERT INTO `we``ird` VALUES (1);\n") == ("we`ird", 1)
    assert be.count_insert_rows(b"CREATE TABLE `t` (id int);") is None


def test_dump_scanner_collects_point_and_counts():
    scanner = be.DumpScanner()
    for line in [
        b"-- CHANGE MASTER TO MASTER_LOG_FILE='mysql-bin.000002', MASTER_LOG_POS=2115;\n",
        b"-- Table structure for table `empty`\n",
        b"-- Table structure for table `users`\n",
        b"INSERT INTO `users` VALUES (1,'a'),(2,'b');\n",
        b"INSERT INTO `users` VALUES (3,'c');\n",
        b"-- SET GLOBAL gtid_slave_pos='0-1-10';\n",
    ]:
        scanner.feed(line)
    assert (scanner.binlog_file, scanner.binlog_pos, scanner.gtid) == ("mysql-bin.000002", 2115, "0-1-10")
    assert scanner.row_counts == {"empty": 0, "users": 3}


def test_rewrite_dump_line():
    rename = be.name_rewriter("p_shop_abc123", "rtmp_1")
    definer = b"DEFINER=`u_new`@`%`"
    line = b"/*!50003 CREATE*/ /*!50017 DEFINER=`u_old`@`%`*/ /*!50003 TRIGGER t BEFORE INSERT ON p_shop_abc123.x */;"
    out = be.rewrite_dump_line(line, definer=definer, rename=rename)
    assert b"DEFINER=`u_new`@`%`" in out and b"rtmp_1.x" in out and b"u_old" not in out
    data = b"INSERT INTO `x` VALUES ('DEFINER=`u_old`@`%` p_shop_abc123');"
    assert be.rewrite_dump_line(data, definer=definer, rename=rename) == data  # data is never rewritten
    assert rename(b"use `p_shop_abc123_2`; p_shop_abc123.t") == b"use `p_shop_abc123_2`; rtmp_1.t"


def _event(ts, etype, body):
    size = 19 + len(body)
    return struct.pack("<IBIIIH", ts, etype, 1, size, 0, 0) + body


def test_parse_binlog_extracts_databases_and_times():
    fde = _event(1000, 15, b"\x04\x00" + b"\x00" * 60)
    query_body = struct.pack("<IIBHH", 7, 0, len(b"p_a"), 0, 2) + b"\x00\x00" + b"p_a\x00" + b"CREATE TABLE t (x int)"
    table_map = b"\x01\x00\x00\x00\x00\x00" + b"\x00\x00" + bytes([3]) + b"p_b\x00" + bytes([1]) + b"t\x00"
    data = b"\xfebin" + fde + _event(1005, 2, query_body) + _event(1010, 19, table_map)
    parsed = be.parse_binlog(data)
    assert parsed["dbs"] == ["p_a", "p_b"] and parsed["events"] == 3
    assert parsed["first_at"] == "1970-01-01T00:16:40Z" and parsed["last_at"] == "1970-01-01T00:16:50Z"
    assert be.parse_binlog(b"not a binlog")["dbs"] == ["*"]
    assert "*" in be.parse_binlog(data[:-3])["dbs"]  # truncated tail -> treat as touching everything


def test_binlog_names():
    assert be.binlog_seq("mysql-bin.000012") == 12
    assert be.binlog_name_with_seq("mysql-bin.000012", 11) == "mysql-bin.000011"
    with pytest.raises(ValueError):
        be.binlog_seq("../etc/passwd")


def test_rename_oplog_entry():
    ui = b"uuid"
    insert = {"ts": Timestamp(5, 1), "op": "i", "ns": "p_src.items", "ui": ui, "o": {"_id": 1}}
    out = be.rename_oplog_entry(insert, "p_src", "rtmp_x")
    assert out["ns"] == "rtmp_x.items" and "ui" not in out and insert["ns"] == "p_src.items"
    assert be.rename_oplog_entry({**insert, "ns": "p_src2.items"}, "p_src", "rtmp_x") is None
    assert be.rename_oplog_entry({"op": "n", "ns": "", "o": {}}, "p_src", "t") is None
    rename = {"op": "c", "ns": "p_src.$cmd", "o": {"renameCollection": "p_src.a", "to": "p_src.b"}}
    assert be.rename_oplog_entry(rename, "p_src", "t")["o"] == {"renameCollection": "t.a", "to": "t.b"}
    txn = {
        "op": "c",
        "ns": "admin.$cmd",
        "o": {
            "applyOps": [
                {"op": "i", "ns": "p_src.items", "ui": ui, "o": {"_id": 2}},
                {"op": "i", "ns": "other.x", "o": {"a": 1}},
            ]
        },
    }
    out = be.rename_oplog_entry(txn, "p_src", "t")
    assert out["o"]["applyOps"] == [{"op": "i", "ns": "t.items", "o": {"_id": 2}}]
    only_other = {"op": "c", "ns": "admin.$cmd", "o": {"applyOps": [{"op": "i", "ns": "other.x", "o": {}}]}}
    assert be.rename_oplog_entry(only_other, "p_src", "t") is None


def test_parse_mongodump_counts_and_compare():
    text = (
        "2026-09-16T09:28:42.759+0000\tdone dumping `p_src.items` (5 documents)\n"
        "2026-09-16T09:28:42.760+0000\tdone dumping `p_src.one` (1 document)\n"
        "2026-09-16T09:28:42.760+0000\tdone dumping `p_other.x` (9 documents)\n"
    )
    assert be.parse_mongodump_counts(text, "p_src") == {"items": 5, "one": 1}
    assert be.compare_counts({"a": 1}, {"a": 1})["ok"]
    res = be.compare_counts({"a": 1, "b": 2}, {"a": 1, "c": 0})
    assert not res["ok"] and {m["entity"] for m in res["mismatches"]} == {"b", "c"}


def test_identifier_and_temp_database_guards():
    with pytest.raises(ValueError):
        be.check_db_name("p_x; DROP DATABASE deployer")
    assert be.check_db_name("deployer", platform=True) == "deployer"
    with pytest.raises(ValueError):
        be._mariadb_drop_db("p_live_db")  # only temporary databases can be dropped by the engine
    with pytest.raises(ValueError):
        be._mongo_drop_tmp("p_live_db")


def test_credentials_never_in_arguments(monkeypatch):
    import secrets
    from urllib.parse import quote

    from app.config import get_settings

    settings = get_settings()
    token = secrets.token_hex(8)
    tricky = token[:4] + '"' + token[4:8] + "\\" + token[8:]
    mongo_secret = token[:6] + "@" + token[6:10] + ":" + token[10:] + "/"
    monkeypatch.setattr(settings, "mariadb_root_password", tricky)
    monkeypatch.setattr(settings, "mongo_root_password", mongo_secret)
    with be.mariadb_defaults_file() as cnf:
        escaped = tricky.replace("\\", "\\\\").replace('"', '\\"')
        assert f'password="{escaped}"' in cnf.read_text()
    assert not cnf.exists()
    with be.mongo_config_file() as cfg:
        assert quote(mongo_secret, safe="") in cfg.read_text()
    assert not cfg.exists()
    env = be._tool_env()
    assert not any(k.startswith(("MARIADB_", "MONGO_")) for k in env) and env["TZ"] == "UTC"
