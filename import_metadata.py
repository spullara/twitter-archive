#!/usr/bin/env python3
"""
Import metadata from Twitter archive into DuckDB database.

Imports likes, followers, following, and account data from:
- archive/data/like.js
- archive/data/follower.js
- archive/data/following.js
- archive/data/account.js

Usage:
    python import_metadata.py [--data-dir PATH] [--db PATH]

Options:
    --data-dir PATH   Path to archive data directory (default: archive/data)
    --db PATH         Path to database file (default: twitter.db)
"""

import argparse
import json
import os
import sys
from pathlib import Path

try:
    import duckdb
except ImportError:
    print("Error: duckdb not installed. Run: pip install duckdb")
    sys.exit(1)


def parse_js_file(filepath: Path) -> list:
    """Parse Twitter archive JS file, stripping the window.YTD.* prefix."""
    if not filepath.exists():
        print(f"  Skipping {filepath.name}: file not found")
        return []

    content = filepath.read_text(encoding='utf-8')

    # Find the start of the JSON array (after 'window.YTD.*.part0 = ')
    eq_index = content.find('=')
    if eq_index == -1:
        print(f"  Warning: Invalid format in {filepath.name}")
        return []

    json_str = content[eq_index + 1:].strip()

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"  Warning: Failed to parse {filepath.name}: {e}")
        return []


def import_likes(conn: duckdb.DuckDBPyConnection, data_dir: Path, batch_size: int = 1000):
    """Import likes from like.js."""
    print("Importing likes...")
    filepath = data_dir / "like.js"
    data = parse_js_file(filepath)

    if not data:
        return 0

    batch = []
    count = 0

    for item in data:
        like = item.get('like', {})
        batch.append((
            like.get('tweetId'),
            like.get('fullText'),
            like.get('expandedUrl'),
            None  # liked_at not available in archive
        ))

        if len(batch) >= batch_size:
            conn.executemany(
                "INSERT INTO likes (tweet_id, full_text, expanded_url, liked_at) VALUES (?, ?, ?, ?)",
                batch
            )
            count += len(batch)
            batch = []

    # Insert remaining records
    if batch:
        conn.executemany(
            "INSERT INTO likes (tweet_id, full_text, expanded_url, liked_at) VALUES (?, ?, ?, ?)",
            batch
        )
        count += len(batch)

    print(f"  Imported {count} likes")
    return count


def import_followers(conn: duckdb.DuckDBPyConnection, data_dir: Path, batch_size: int = 1000):
    """Import followers from follower.js."""
    print("Importing followers...")
    filepath = data_dir / "follower.js"
    data = parse_js_file(filepath)

    if not data:
        return 0

    batch = []
    count = 0

    for item in data:
        follower = item.get('follower', {})
        batch.append((
            follower.get('accountId'),
            follower.get('userLink'),
            None  # followed_at not available
        ))

        if len(batch) >= batch_size:
            conn.executemany(
                "INSERT OR IGNORE INTO followers (account_id, user_link, followed_at) VALUES (?, ?, ?)",
                batch
            )
            count += len(batch)
            batch = []

    if batch:
        conn.executemany(
            "INSERT OR IGNORE INTO followers (account_id, user_link, followed_at) VALUES (?, ?, ?)",
            batch
        )
        count += len(batch)

    print(f"  Imported {count} followers")
    return count


def import_following(conn: duckdb.DuckDBPyConnection, data_dir: Path, batch_size: int = 1000):
    """Import following from following.js."""
    print("Importing following...")
    filepath = data_dir / "following.js"
    data = parse_js_file(filepath)

    if not data:
        return 0

    batch = []
    count = 0

    for item in data:
        following = item.get('following', {})
        batch.append((
            following.get('accountId'),
            following.get('userLink'),
            None  # followed_at not available
        ))

        if len(batch) >= batch_size:
            conn.executemany(
                "INSERT OR IGNORE INTO following (account_id, user_link, followed_at) VALUES (?, ?, ?)",
                batch
            )
            count += len(batch)
            batch = []

    if batch:
        conn.executemany(
            "INSERT OR IGNORE INTO following (account_id, user_link, followed_at) VALUES (?, ?, ?)",
            batch
        )
        count += len(batch)

    print(f"  Imported {count} following")
    return count


def import_account(conn: duckdb.DuckDBPyConnection, data_dir: Path):
    """Import account info from account.js."""
    print("Importing account...")
    filepath = data_dir / "account.js"
    data = parse_js_file(filepath)

    if not data:
        return 0

    count = 0
    for item in data:
        account = item.get('account', {})
        conn.execute(
            """INSERT OR IGNORE INTO account
               (account_id, username, account_display_name, email, created_via, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                account.get('accountId'),
                account.get('username'),
                account.get('accountDisplayName'),
                account.get('email'),
                account.get('createdVia'),
                account.get('createdAt')
            )
        )
        count += 1

    print(f"  Imported {count} account record(s)")
    return count


def main():
    parser = argparse.ArgumentParser(
        description="Import Twitter archive metadata into DuckDB database"
    )
    parser.add_argument(
        '--data-dir',
        type=Path,
        default=Path('archive/data'),
        help='Path to archive data directory (default: archive/data)'
    )
    parser.add_argument(
        '--db',
        type=Path,
        default=Path('twitter.db'),
        help='Path to database file (default: twitter.db)'
    )
    args = parser.parse_args()

    # Validate data directory
    if not args.data_dir.exists():
        print(f"Warning: Data directory not found: {args.data_dir}")
        print("Continuing anyway - will skip missing files...")

    # Connect to database
    if not args.db.exists():
        print(f"Error: Database file not found: {args.db}")
        print("Please run schema.sql first to create the database.")
        sys.exit(1)

    print(f"Connecting to database: {args.db}")
    conn = duckdb.connect(str(args.db))

    try:
        # Import all metadata
        total = 0
        total += import_likes(conn, args.data_dir)
        total += import_followers(conn, args.data_dir)
        total += import_following(conn, args.data_dir)
        total += import_account(conn, args.data_dir)

        print(f"\nImport complete! Total records: {total}")

    except Exception as e:
        print(f"Error during import: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == '__main__':
    main()
