#!/usr/bin/env python3
"""Safely diagnose or remove one stale remote-ChatGPT catalog entry on macOS."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from datetime import datetime
from urllib.parse import quote


REQUIRED_COLUMNS = {
    "local_thread_catalog": {
        "host_id",
        "thread_id",
        "display_title",
        "source_kind",
        "missing_candidate",
    },
    "local_thread_catalog_hosts": {"host_id", "host_kind"},
    "local_thread_catalog_metadata": {"id", "catalog_revision"},
    "thread_timeline_ledger": {"host_id", "thread_id"},
}


class SafetyStop(RuntimeError):
    """Raised when a safety invariant prevents the requested operation."""


def emit(payload: dict) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def resolve_database(value: str | None) -> Path:
    if value:
        path = Path(value).expanduser().resolve()
        if not path.is_file():
            raise SafetyStop("The selected database does not exist.")
        return path

    codex_root = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()
    sqlite_root = codex_root / "sqlite"
    preferred = sqlite_root / "codex-dev.db"
    if preferred.is_file():
        return preferred.resolve()

    candidates = sorted(sqlite_root.glob("*.db")) if sqlite_root.is_dir() else []
    if len(candidates) != 1:
        raise SafetyStop("Could not resolve exactly one local catalog database.")
    return candidates[0].resolve()


def connect_read_only(path: Path) -> sqlite3.Connection:
    uri = f"file:{quote(str(path), safe='/')}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=5.0)
    connection.row_factory = sqlite3.Row
    return connection


def verify_schema(connection: sqlite3.Connection) -> None:
    for table, required in REQUIRED_COLUMNS.items():
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        ).fetchone()
        if not exists:
            raise SafetyStop("The local catalog schema is unsupported.")
        columns = {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}
        if not required.issubset(columns):
            raise SafetyStop("The local catalog schema is unsupported.")

    metadata_rows = connection.execute(
        "SELECT COUNT(*) FROM local_thread_catalog_metadata WHERE id = 1"
    ).fetchone()[0]
    if metadata_rows != 1:
        raise SafetyStop("Catalog metadata is not in the expected state.")


def integrity_result(connection: sqlite3.Connection) -> str:
    rows = [row[0] for row in connection.execute("PRAGMA integrity_check")]
    return "ok" if rows == ["ok"] else "failed"


def selection_token(host_id: str, thread_id: str) -> str:
    material = f"{host_id}\0{thread_id}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:20]


def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def candidate_rows(
    connection: sqlite3.Connection, title: str, prefix: bool
) -> list[sqlite3.Row]:
    if prefix:
        predicate = "c.display_title LIKE ? ESCAPE '\\'"
        title_parameter = escape_like(title) + "%"
    else:
        predicate = "c.display_title = ?"
        title_parameter = title

    return list(
        connection.execute(
            f"""
            SELECT
              c.host_id,
              c.thread_id,
              c.display_title,
              c.source_kind,
              c.missing_candidate,
              h.host_kind,
              (
                SELECT COUNT(*)
                FROM thread_timeline_ledger AS l
                WHERE l.host_id = c.host_id AND l.thread_id = c.thread_id
              ) AS timeline_record_count
            FROM local_thread_catalog AS c
            LEFT JOIN local_thread_catalog_hosts AS h ON h.host_id = c.host_id
            WHERE c.source_kind = 'chatgpt' AND {predicate}
            ORDER BY c.host_id, c.thread_id
            """,
            (title_parameter,),
        )
    )


def sanitized_candidate(row: sqlite3.Row) -> dict:
    reasons: list[str] = []
    if row["source_kind"] != "chatgpt":
        reasons.append("source_kind_not_chatgpt")
    if row["host_kind"] != "chatgpt":
        reasons.append("host_kind_not_chatgpt")
    if row["missing_candidate"] != 0:
        reasons.append("already_marked_missing")
    if row["timeline_record_count"] != 0:
        reasons.append("local_timeline_records_exist")
    return {
        "eligible": not reasons,
        "host_kind": row["host_kind"],
        "missing_candidate": row["missing_candidate"],
        "reasons": reasons,
        "selection_token": selection_token(row["host_id"], row["thread_id"]),
        "source_kind": row["source_kind"],
        "timeline_record_count": row["timeline_record_count"],
    }


def inspect_database(path: Path, title: str, prefix: bool) -> tuple[dict, list[sqlite3.Row]]:
    with connect_read_only(path) as connection:
        verify_schema(connection)
        integrity = integrity_result(connection)
        rows = candidate_rows(connection, title, prefix)
    return (
        {
            "candidate_count": len(rows),
            "candidates": [sanitized_candidate(row) for row in rows],
            "database_name": path.name,
            "integrity_check": integrity,
            "match_mode": "prefix" if prefix else "exact",
        },
        rows,
    )


def create_backup(source_path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = source_path.with_name(
        f"{source_path.name}.ghost-entry-backup-{timestamp}.sqlite"
    )
    if backup_path.exists():
        raise SafetyStop("The backup target already exists.")

    source = connect_read_only(source_path)
    destination = sqlite3.connect(backup_path)
    try:
        source.backup(destination)
        destination.commit()
        if integrity_result(destination) != "ok":
            raise SafetyStop("The backup failed its integrity check.")
    except Exception:
        destination.close()
        source.close()
        if backup_path.exists():
            backup_path.unlink()
        raise
    else:
        destination.close()
        source.close()
    os.chmod(backup_path, 0o600)
    return backup_path


def repair_database(
    path: Path, title: str, prefix: bool, token: str, confirmed: bool, apply: bool
) -> dict:
    if not confirmed or not apply:
        raise SafetyStop("Repair requires both explicit confirmation flags.")

    inspection, rows = inspect_database(path, title, prefix)
    if inspection["integrity_check"] != "ok":
        raise SafetyStop("The database failed its integrity check.")
    if len(rows) != 1:
        raise SafetyStop("Repair requires exactly one candidate.")
    row = rows[0]
    candidate = sanitized_candidate(row)
    if not candidate["eligible"]:
        raise SafetyStop("The candidate failed one or more safety invariants.")
    if candidate["selection_token"] != token:
        raise SafetyStop("The selection token does not match the candidate.")

    backup_path = create_backup(path)
    connection = sqlite3.connect(path, timeout=5.0, isolation_level=None)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("BEGIN IMMEDIATE")
        verify_schema(connection)
        current_rows = candidate_rows(connection, title, prefix)
        if len(current_rows) != 1:
            raise SafetyStop("The candidate changed before the transaction began.")
        current = current_rows[0]
        current_candidate = sanitized_candidate(current)
        if not current_candidate["eligible"] or current_candidate["selection_token"] != token:
            raise SafetyStop("The candidate changed before the transaction began.")

        deleted = connection.execute(
            """
            DELETE FROM local_thread_catalog
            WHERE host_id = ?
              AND thread_id = ?
              AND display_title = ?
              AND source_kind = 'chatgpt'
              AND missing_candidate = 0
            """,
            (current["host_id"], current["thread_id"], current["display_title"]),
        ).rowcount
        if deleted != 1:
            raise SafetyStop("The targeted delete did not affect exactly one row.")

        revised = connection.execute(
            """
            UPDATE local_thread_catalog_metadata
            SET catalog_revision = catalog_revision + 1
            WHERE id = 1
            """
        ).rowcount
        if revised != 1:
            raise SafetyStop("The catalog revision was not updated exactly once.")
        connection.execute("COMMIT")
    except Exception:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()

    with connect_read_only(path) as verification:
        remaining = verification.execute(
            """
            SELECT COUNT(*) FROM local_thread_catalog
            WHERE host_id = ? AND thread_id = ?
            """,
            (row["host_id"], row["thread_id"]),
        ).fetchone()[0]
        final_integrity = integrity_result(verification)
    if remaining != 0 or final_integrity != "ok":
        raise SafetyStop("Post-repair verification failed; preserve the backup.")

    return {
        "backup_file": str(backup_path),
        "deleted_rows": 1,
        "integrity_check": final_integrity,
        "remaining_matches": remaining,
        "status": "repaired",
    }


def add_title_selector(parser: argparse.ArgumentParser) -> None:
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--title", help="Match the complete visible title exactly.")
    selector.add_argument(
        "--title-prefix", help="Match a literal title prefix; wildcard characters stay literal."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="Override the local catalog database path.")
    commands = parser.add_subparsers(dest="command", required=True)

    inspect_parser = commands.add_parser("inspect", help="Inspect candidates read-only.")
    add_title_selector(inspect_parser)

    repair_parser = commands.add_parser("repair", help="Repair one confirmed candidate.")
    add_title_selector(repair_parser)
    repair_parser.add_argument("--selection-token", required=True)
    repair_parser.add_argument("--confirm-cloud-deleted", action="store_true")
    repair_parser.add_argument("--apply", action="store_true")
    return parser


def selected_title(args: argparse.Namespace) -> tuple[str, bool]:
    if args.title is not None:
        return args.title, False
    return args.title_prefix, True


def main() -> int:
    args = build_parser().parse_args()
    try:
        database = resolve_database(args.db)
        title, prefix = selected_title(args)
        if not title:
            raise SafetyStop("The title selector cannot be empty.")
        if args.command == "inspect":
            result, _ = inspect_database(database, title, prefix)
        else:
            result = repair_database(
                database,
                title,
                prefix,
                args.selection_token,
                args.confirm_cloud_deleted,
                args.apply,
            )
        emit(result)
        return 0
    except SafetyStop as error:
        emit({"status": "stopped", "reason": str(error)})
        return 2
    except (OSError, sqlite3.Error) as error:
        emit({"status": "error", "reason": error.__class__.__name__})
        return 1


if __name__ == "__main__":
    sys.exit(main())
