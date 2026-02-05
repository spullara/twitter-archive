#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Tuple

import duckdb


DEFAULT_ARCHIVE_DIR = Path("archive/data")
DEFAULT_DB_PATH = "twitter.db"
DEFAULT_BATCH_SIZE = 1000


def load_ytd_json_array(path: Path) -> List[dict]:
    raw = path.read_text(encoding="utf-8")
    if "=" in raw:
        raw = raw.split("=", 1)[1].strip()
    if raw.endswith(";"):
        raw = raw[:-1]
    return json.loads(raw)


def batched_insert(
    conn: duckdb.DuckDBPyConnection,
    sql: str,
    rows: Iterable[Tuple[Optional[str], ...]],
    batch_size: int,
) -> int:
    batch: List[Tuple[Optional[str], ...]] = []
    count = 0
    for row in rows:
        batch.append(row)
        if len(batch) >= batch_size:
            conn.executemany(sql, batch)
            count += len(batch)
            batch.clear()
    if batch:
        conn.executemany(sql, batch)
        count += len(batch)
    return count


def like_rows(entries: List[dict]) -> Iterator[Tuple[Optional[str], ...]]:
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        like = entry.get("like")
        if not isinstance(like, dict):
            continue
        tweet_id = like.get("tweetId")
        if not tweet_id:
            continue
        yield (
            tweet_id,
            like.get("fullText"),
            like.get("expandedUrl"),
            like.get("likedAt") or like.get("liked_at") or like.get("timestamp"),
        )


def follow_rows(entries: List[dict], key: str) -> Iterator[Tuple[Optional[str], ...]]:
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        follow = entry.get(key)
        if not isinstance(follow, dict):
            continue
        account_id = follow.get("accountId")
        if not account_id:
            continue
        yield (
            account_id,
            follow.get("userLink"),
            follow.get("followedAt") or follow.get("followed_at"),
        )


def account_rows(entries: List[dict]) -> Iterator[Tuple[Optional[str], ...]]:
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        account = entry.get("account")
        if not isinstance(account, dict):
            continue
        account_id = account.get("accountId")
        username = account.get("username")
        if not account_id or not username:
            continue
        yield (
            account_id,
            username,
            account.get("accountDisplayName"),
            account.get("email"),
            account.get("createdVia"),
            account.get("createdAt"),
        )


def import_likes(
    conn: duckdb.DuckDBPyConnection, archive_dir: Path, batch_size: int
) -> int:
    path = archive_dir / "like.js"
    if not path.exists():
        print(f"Skipping likes; file not found: {path}")
        return 0
    entries = load_ytd_json_array(path)
    sql = (
        "INSERT INTO likes (tweet_id, full_text, expanded_url, liked_at) "
        "VALUES (?, ?, ?, ?)"
    )
    return batched_insert(conn, sql, like_rows(entries), batch_size)


def import_followers(
    conn: duckdb.DuckDBPyConnection, archive_dir: Path, batch_size: int
) -> int:
    path = archive_dir / "follower.js"
    if not path.exists():
        print(f"Skipping followers; file not found: {path}")
        return 0
    entries = load_ytd_json_array(path)
    sql = (
        "INSERT INTO followers (account_id, user_link, followed_at) "
        "VALUES (?, ?, ?)"
    )
    return batched_insert(conn, sql, follow_rows(entries, "follower"), batch_size)


def import_following(
    conn: duckdb.DuckDBPyConnection, archive_dir: Path, batch_size: int
) -> int:
    path = archive_dir / "following.js"
    if not path.exists():
        print(f"Skipping following; file not found: {path}")
        return 0
    entries = load_ytd_json_array(path)
    sql = (
        "INSERT INTO following (account_id, user_link, followed_at) "
        "VALUES (?, ?, ?)"
    )
    return batched_insert(conn, sql, follow_rows(entries, "following"), batch_size)


def import_account(
    conn: duckdb.DuckDBPyConnection, archive_dir: Path, batch_size: int
) -> int:
    path = archive_dir / "account.js"
    if not path.exists():
        print(f"Skipping account; file not found: {path}")
        return 0
    entries = load_ytd_json_array(path)
    sql = (
        "INSERT INTO account "
        "(account_id, username, account_display_name, email, created_via, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)"
    )
    return batched_insert(conn, sql, account_rows(entries), batch_size)


def run_import(
    conn: duckdb.DuckDBPyConnection, archive_dir: Path, batch_size: int
) -> None:
    imports = [
        ("likes", lambda: import_likes(conn, archive_dir, batch_size)),
        ("followers", lambda: import_followers(conn, archive_dir, batch_size)),
        ("following", lambda: import_following(conn, archive_dir, batch_size)),
        ("account", lambda: import_account(conn, archive_dir, batch_size)),
    ]
    for label, loader in imports:
        conn.execute("BEGIN")
        try:
            count = loader()
        except Exception:
            conn.execute("ROLLBACK")
            raise
        else:
            conn.execute("COMMIT")
            print(f"Imported {count} {label} rows.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import likes, followers, following, and account metadata into DuckDB."
    )
    parser.add_argument(
        "--archive-dir",
        default=str(DEFAULT_ARCHIVE_DIR),
        help="Path to archive/data directory.",
    )
    parser.add_argument(
        "--db-path", default=DEFAULT_DB_PATH, help="DuckDB database file."
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Batch size for inserts.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    archive_dir = Path(args.archive_dir)
    if not archive_dir.exists():
        print(f"Archive directory not found: {archive_dir}", file=sys.stderr)
        return 1
    conn = duckdb.connect(args.db_path)
    try:
        run_import(conn, archive_dir, args.batch_size)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
