"""Row counting from mariadb-dump output must handle both extended-INSERT layouts."""

from app.services.backup_engine import DumpScanner, count_insert_rows


def _scan(dump: bytes) -> dict[str, int]:
    scanner = DumpScanner()
    for line in dump.splitlines(keepends=True):
        scanner.feed(line)
    return scanner.row_counts


def test_single_line_extended_insert():
    dump = b"-- Table structure for table `items`\n" b"INSERT INTO `items` VALUES (1,'a'),(2,'b'),(3,'c');\n"
    assert _scan(dump) == {"items": 3}


def test_multi_line_extended_insert_as_written_by_mariadb_11():
    dump = (
        b"-- Table structure for table `items`\n"
        b"INSERT INTO `items` VALUES\n"
        b"(1,'one'),\n"
        b"(2,'tw),(o'),\n"  # a string containing '),(' must not be counted as two rows
        b"(3,'three');\n"
        b"-- Table structure for table `empty`\n"
        b"INSERT INTO `other` VALUES\n"
        b"(1,'x');\n"
    )
    assert _scan(dump) == {"items": 3, "empty": 0, "other": 1}


def test_count_insert_rows_first_line_only():
    assert count_insert_rows(b"INSERT INTO `t` VALUES (1),(2);\n") == ("t", 2)
    assert count_insert_rows(b"INSERT INTO `t` VALUES\n") == ("t", 0)
    assert count_insert_rows(b"-- not an insert\n") is None
