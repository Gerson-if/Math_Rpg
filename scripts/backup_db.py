"""
Database backup, meant to be run by an external scheduler (cron, systemd
timer, Windows Task Scheduler) — same reasoning as the leaderboard
recompute command: nothing runs itself inside the app process, so nothing
duplicates across Gunicorn workers or needs the app up at all.

Postgres (production): shells out to `pg_dump`, using DATABASE_URL
directly as the connection string, and gzips the result. SQLite (dev):
just copies the .db file — a plain file copy is a perfectly good backup
for a single-file database.

Usage:
    python scripts/backup_db.py                  # uses $DATABASE_URL
    python scripts/backup_db.py --out /var/backups/math-rpg
    python scripts/backup_db.py --keep-days 30

Example cron entry (daily at 3am):
    0 3 * * * cd /path/to/project && .venv/bin/python scripts/backup_db.py
"""
import argparse
import gzip
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent.parent


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def backup_postgres(database_url: str, out_dir: Path) -> Path:
    dest = out_dir / f"math-rpg-{_timestamp()}.sql.gz"
    out_dir.mkdir(parents=True, exist_ok=True)

    # pg_dump writes the plain-text dump to stdout; gzip it as we go
    # instead of writing an intermediate .sql file to disk.
    with gzip.open(dest, "wb") as gz_file:
        result = subprocess.run(
            ["pg_dump", "--no-owner", "--no-privileges", database_url],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        if result.returncode != 0:
            dest.unlink(missing_ok=True)
            raise RuntimeError(
                f"pg_dump failed (exit {result.returncode}): "
                f"{result.stderr.decode(errors='replace')}"
            )
        gz_file.write(result.stdout)

    return dest


def backup_sqlite(database_url: str, out_dir: Path) -> Path:
    # sqlite:///relative/path or sqlite:////absolute/path
    db_path = Path(database_url.replace("sqlite:///", "", 1))
    if not db_path.is_absolute():
        db_path = BASE_DIR / db_path
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite database not found at {db_path}")

    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"dev-{_timestamp()}.db"
    shutil.copy2(db_path, dest)
    return dest


def prune_old_backups(out_dir: Path, keep_days: int) -> int:
    if not out_dir.exists():
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
    removed = 0
    for path in out_dir.glob("*"):
        if path.is_file() and datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc) < cutoff:
            path.unlink()
            removed += 1
    return removed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=str(BASE_DIR / "backups"), help="Backup output directory.")
    parser.add_argument("--keep-days", type=int, default=int(os.environ.get("BACKUP_RETENTION_DAYS", 14)))
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    out_dir = Path(args.out)

    if database_url and database_url.startswith(("postgres://", "postgresql://")):
        dest = backup_postgres(database_url, out_dir)
    else:
        fallback_url = database_url or f"sqlite:///{BASE_DIR / 'instance' / 'dev.db'}"
        dest = backup_sqlite(fallback_url, out_dir)

    size_kb = dest.stat().st_size / 1024
    print(f"Backup salvo em {dest} ({size_kb:.1f} KB)")

    removed = prune_old_backups(out_dir, args.keep_days)
    if removed:
        print(f"{removed} backup(s) com mais de {args.keep_days} dias removido(s).")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # surfaced to cron's mail/log, not swallowed
        print(f"Backup falhou: {exc}", file=sys.stderr)
        sys.exit(1)
