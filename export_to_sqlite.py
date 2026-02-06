#!/usr/bin/env python3
"""Export DuckDB database to SQLite3 format."""

import os
import sqlite3
import duckdb

# File paths
DUCKDB_PATH = "twitter.db"
SQLITE_PATH = "twitter.sqlite3"

# Tables in dependency order (parents before children for foreign keys)
TABLES = [
    "users",
    "tweets", 
    "hashtags",
    "mentions",
    "urls",
    "media",
    "likes",
    "followers",
    "following",
    "account",
]

# SQLite CREATE TABLE statements (adapted from DuckDB schema)
# Key differences: no sequences, use INTEGER PRIMARY KEY for auto-increment
SQLITE_SCHEMA = """
-- Users table
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    screen_name TEXT UNIQUE,
    name TEXT
);
CREATE INDEX IF NOT EXISTS idx_users_screen_name ON users(screen_name);

-- Tweets table
CREATE TABLE IF NOT EXISTS tweets (
    tweet_id TEXT PRIMARY KEY,
    created_at TIMESTAMP NOT NULL,
    full_text TEXT NOT NULL,
    lang TEXT,
    source TEXT,
    retweet_count INTEGER DEFAULT 0,
    favorite_count INTEGER DEFAULT 0,
    retweeted INTEGER DEFAULT 0,
    favorited INTEGER DEFAULT 0,
    truncated INTEGER DEFAULT 0,
    in_reply_to_status_id TEXT,
    in_reply_to_user_id TEXT,
    in_reply_to_screen_name TEXT,
    display_text_range_start INTEGER,
    display_text_range_end INTEGER,
    editable_until TIMESTAMP,
    edits_remaining INTEGER,
    is_edit_eligible INTEGER,
    FOREIGN KEY (in_reply_to_user_id) REFERENCES users(user_id)
);
CREATE INDEX IF NOT EXISTS idx_tweets_created_at ON tweets(created_at);
CREATE INDEX IF NOT EXISTS idx_tweets_in_reply_to ON tweets(in_reply_to_status_id);
CREATE INDEX IF NOT EXISTS idx_tweets_lang ON tweets(lang);

-- Hashtags table (INTEGER PRIMARY KEY auto-increments in SQLite)
CREATE TABLE IF NOT EXISTS hashtags (
    id INTEGER PRIMARY KEY,
    tweet_id TEXT NOT NULL,
    hashtag TEXT NOT NULL,
    start_index INTEGER,
    end_index INTEGER,
    FOREIGN KEY (tweet_id) REFERENCES tweets(tweet_id)
);
CREATE INDEX IF NOT EXISTS idx_hashtags_tweet ON hashtags(tweet_id);
CREATE INDEX IF NOT EXISTS idx_hashtags_tag ON hashtags(hashtag);

-- Mentions table
CREATE TABLE IF NOT EXISTS mentions (
    id INTEGER PRIMARY KEY,
    tweet_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    screen_name TEXT NOT NULL,
    name TEXT,
    start_index INTEGER,
    end_index INTEGER,
    FOREIGN KEY (tweet_id) REFERENCES tweets(tweet_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);
CREATE INDEX IF NOT EXISTS idx_mentions_tweet ON mentions(tweet_id);
CREATE INDEX IF NOT EXISTS idx_mentions_user ON mentions(user_id);

-- URLs table  
CREATE TABLE IF NOT EXISTS urls (
    id INTEGER PRIMARY KEY,
    tweet_id TEXT NOT NULL,
    url TEXT NOT NULL,
    expanded_url TEXT,
    display_url TEXT,
    start_index INTEGER,
    end_index INTEGER,
    FOREIGN KEY (tweet_id) REFERENCES tweets(tweet_id)
);
CREATE INDEX IF NOT EXISTS idx_urls_tweet ON urls(tweet_id);
CREATE INDEX IF NOT EXISTS idx_urls_expanded ON urls(expanded_url);

-- Media table
CREATE TABLE IF NOT EXISTS media (
    id INTEGER PRIMARY KEY,
    tweet_id TEXT NOT NULL,
    media_id TEXT,
    media_url TEXT,
    media_type TEXT,
    file_path TEXT,
    FOREIGN KEY (tweet_id) REFERENCES tweets(tweet_id)
);
CREATE INDEX IF NOT EXISTS idx_media_tweet ON media(tweet_id);
CREATE INDEX IF NOT EXISTS idx_media_type ON media(media_type);

-- Likes table
CREATE TABLE IF NOT EXISTS likes (
    id INTEGER PRIMARY KEY,
    tweet_id TEXT NOT NULL,
    full_text TEXT,
    expanded_url TEXT,
    liked_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_likes_tweet ON likes(tweet_id);

-- Followers table
CREATE TABLE IF NOT EXISTS followers (
    account_id TEXT PRIMARY KEY,
    user_link TEXT,
    followed_at TIMESTAMP
);

-- Following table
CREATE TABLE IF NOT EXISTS following (
    account_id TEXT PRIMARY KEY,
    user_link TEXT,
    followed_at TIMESTAMP
);

-- Account table
CREATE TABLE IF NOT EXISTS account (
    account_id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    account_display_name TEXT,
    email TEXT,
    created_via TEXT,
    created_at TIMESTAMP
);
"""


def export_to_sqlite(duckdb_path: str = DUCKDB_PATH, sqlite_path: str = SQLITE_PATH):
    """Export all tables from DuckDB to SQLite."""
    
    # Remove existing SQLite file if present
    if os.path.exists(sqlite_path):
        os.remove(sqlite_path)
        print(f"Removed existing {sqlite_path}")
    
    # Connect to both databases
    duck_conn = duckdb.connect(duckdb_path, read_only=True)
    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_cursor = sqlite_conn.cursor()
    
    # Create schema in SQLite
    print("Creating SQLite schema...")
    sqlite_cursor.executescript(SQLITE_SCHEMA)
    sqlite_conn.commit()

    # Export each table
    total_rows = 0
    row_counts = {}

    for table in TABLES:
        print(f"Exporting {table}...")

        # Get column names from DuckDB
        columns_result = duck_conn.execute(
            f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table}' ORDER BY ordinal_position"
        ).fetchall()
        columns = [col[0] for col in columns_result]

        if not columns:
            print(f"  Warning: No columns found for {table}, skipping")
            row_counts[table] = 0
            continue

        # Fetch all data from DuckDB
        col_list = ", ".join(columns)
        rows = duck_conn.execute(f"SELECT {col_list} FROM {table}").fetchall()

        if rows:
            # Insert into SQLite
            placeholders = ", ".join(["?" for _ in columns])
            insert_sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"

            # Convert boolean values to integers for SQLite
            converted_rows = []
            for row in rows:
                converted_row = tuple(
                    int(val) if isinstance(val, bool) else val
                    for val in row
                )
                converted_rows.append(converted_row)

            sqlite_cursor.executemany(insert_sql, converted_rows)
            sqlite_conn.commit()

        row_count = len(rows)
        row_counts[table] = row_count
        total_rows += row_count
        print(f"  Exported {row_count} rows")

    # Close connections
    duck_conn.close()
    sqlite_conn.close()

    # Print summary
    print("\n" + "=" * 50)
    print("Export complete!")
    print(f"Total rows exported: {total_rows}")
    print("\nRow counts by table:")
    for table, count in row_counts.items():
        print(f"  {table}: {count}")

    return row_counts


def verify_export(duckdb_path: str = DUCKDB_PATH, sqlite_path: str = SQLITE_PATH):
    """Verify that the SQLite export matches the DuckDB source."""

    print("\n" + "=" * 50)
    print("Verifying export...")

    duck_conn = duckdb.connect(duckdb_path, read_only=True)
    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_cursor = sqlite_conn.cursor()

    all_match = True

    for table in TABLES:
        # Get DuckDB count
        duck_count = duck_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

        # Get SQLite count
        sqlite_cursor.execute(f"SELECT COUNT(*) FROM {table}")
        sqlite_count = sqlite_cursor.fetchone()[0]

        status = "✓" if duck_count == sqlite_count else "✗"
        if duck_count != sqlite_count:
            all_match = False

        print(f"  {status} {table}: DuckDB={duck_count}, SQLite={sqlite_count}")

    duck_conn.close()
    sqlite_conn.close()

    if all_match:
        print("\n✓ All row counts match!")
    else:
        print("\n✗ Some tables have mismatched row counts!")

    return all_match


if __name__ == "__main__":
    row_counts = export_to_sqlite()
    verify_export()

