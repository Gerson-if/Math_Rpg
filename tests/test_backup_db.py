import os
import time

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.backup_db import backup_sqlite, prune_old_backups


def test_backup_sqlite_copies_the_database_file(tmp_path):
    db_path = tmp_path / "dev.db"
    db_path.write_bytes(b"fake-sqlite-content")
    out_dir = tmp_path / "backups"

    dest = backup_sqlite(f"sqlite:///{db_path}", out_dir)

    assert dest.exists()
    assert dest.read_bytes() == b"fake-sqlite-content"
    assert dest.parent == out_dir


def test_backup_sqlite_raises_when_source_is_missing(tmp_path):
    missing = tmp_path / "does-not-exist.db"
    try:
        backup_sqlite(f"sqlite:///{missing}", tmp_path / "backups")
        assert False, "expected FileNotFoundError"
    except FileNotFoundError:
        pass


def test_prune_old_backups_removes_only_files_past_the_retention_window(tmp_path):
    fresh = tmp_path / "fresh.db"
    fresh.write_text("x")

    old = tmp_path / "old.db"
    old.write_text("x")
    old_time = time.time() - 30 * 86400  # 30 days ago
    os.utime(old, (old_time, old_time))

    removed = prune_old_backups(tmp_path, keep_days=14)

    assert removed == 1
    assert fresh.exists()
    assert not old.exists()


def test_prune_old_backups_on_missing_directory_is_a_noop(tmp_path):
    assert prune_old_backups(tmp_path / "nope", keep_days=14) == 0
