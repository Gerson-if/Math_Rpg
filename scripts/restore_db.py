"""
Restore counterpart to backup_db.py — takes a dump produced by that script
and applies it back to $DATABASE_URL. Meant to be run by a human (the
installer's "Restaurar backup" menu option) or by install.sh's automatic
rollback path during a failed update (`--yes`, non-interactive).

Postgres: pipes the gzipped plain-SQL dump into `psql`. SQLite: copies the
backup file over the instance .db file. Either way, the *current* database
is snapshotted into the backups directory first (prefixed
"pre-restore-safety-") — restoring is destructive by nature, so restoring
the wrong file should still be recoverable.

Usage:
    python scripts/restore_db.py --latest
    python scripts/restore_db.py backups/math-rpg-20260101T030000Z.sql.gz
    python scripts/restore_db.py --latest --yes   # no confirmation prompt
"""
import argparse
import gzip
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backup_db import BASE_DIR, backup_postgres, backup_sqlite  # noqa: E402
import os  # noqa: E402


def _latest_backup(out_dir: Path, database_url: str) -> Path:
    pattern = "*.sql.gz" if database_url.startswith(("postgres://", "postgresql://")) else "dev-*.db"
    candidates = sorted(out_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(f"Nenhum backup encontrado em {out_dir} (padrão {pattern}).")
    return candidates[0]


def restore_postgres(backup_path: Path, database_url: str) -> None:
    with gzip.open(backup_path, "rb") as gz_file:
        dump_bytes = gz_file.read()

    result = subprocess.run(
        ["psql", "--no-psqlrc", "-v", "ON_ERROR_STOP=1", database_url],
        input=dump_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"psql falhou (exit {result.returncode}): {result.stderr.decode(errors='replace')}"
        )


def restore_sqlite(backup_path: Path, database_url: str) -> None:
    import shutil

    db_path = Path(database_url.replace("sqlite:///", "", 1))
    if not db_path.is_absolute():
        db_path = BASE_DIR / db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup_path, db_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("backup_file", nargs="?", help="Caminho do arquivo de backup. Omitir e usar --latest.")
    parser.add_argument("--latest", action="store_true", help="Usa o backup mais recente em --dir.")
    parser.add_argument("--dir", default=str(BASE_DIR / "backups"), help="Diretório de backups (para --latest e para a cópia de segurança pré-restauração).")
    parser.add_argument("--yes", action="store_true", help="Não pedir confirmação (uso por scripts, ex.: rollback automático).")
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    is_postgres = bool(database_url) and database_url.startswith(("postgres://", "postgresql://"))
    fallback_url = database_url or f"sqlite:///{BASE_DIR / 'instance' / 'dev.db'}"
    out_dir = Path(args.dir)

    if args.latest:
        backup_path = _latest_backup(out_dir, database_url or fallback_url)
    elif args.backup_file:
        backup_path = Path(args.backup_file)
    else:
        parser.error("Informe um arquivo de backup ou use --latest.")
        return

    if not backup_path.exists():
        raise FileNotFoundError(f"Arquivo de backup não encontrado: {backup_path}")

    target = database_url if is_postgres else fallback_url
    print(f"Restaurar {backup_path} -> {target}")

    if not args.yes:
        answer = input('Isso SOBRESCREVE o banco de dados atual. Digite "RESTAURAR" para confirmar: ')
        if answer.strip() != "RESTAURAR":
            print("Cancelado.", file=sys.stderr)
            sys.exit(1)

    print("Salvando uma cópia de segurança do banco atual antes de restaurar...")
    if is_postgres:
        safety_dest = backup_postgres(database_url, out_dir)
    else:
        safety_dest = backup_sqlite(fallback_url, out_dir)
    safety_dest.rename(safety_dest.with_name(f"pre-restore-safety-{safety_dest.name}"))
    print(f"Cópia de segurança salva em {safety_dest.with_name(f'pre-restore-safety-{safety_dest.name}')}")

    if is_postgres:
        restore_postgres(backup_path, database_url)
    else:
        restore_sqlite(backup_path, fallback_url)

    print(f"Restaurado com sucesso a partir de {backup_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # surfaced to the caller (menu or install.sh rollback), not swallowed
        print(f"Restauração falhou: {exc}", file=sys.stderr)
        sys.exit(1)
