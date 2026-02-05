#!/usr/bin/env python3
import argparse
import html
import json
import os
import re
import sys
from datetime import datetime
from typing import List, Optional, Set, Tuple
from urllib.parse import urlparse

import duckdb


ARCHIVE_DEFAULT = os.path.join("archive", "data")
DB_DEFAULT = "twitter.db"
BATCH_SIZE = 1000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import tweets and related entities from a Twitter archive into DuckDB."
    )
    parser.add_argument(
        "--archive-dir",
        default=ARCHIVE_DEFAULT,
        help="Path to archive data directory (default: archive/data).",
    )
    parser.add_argument(
        "--db",
        default=DB_DEFAULT,
        help="DuckDB database file (default: twitter.db).",
    )
    return parser.parse_args()


def clean_source(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    stripped = re.sub(r"<[^>]+>", "", value)
    unescaped = html.unescape(stripped).strip()
    return unescaped or None


def parse_int(value) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        candidate = value.strip()
        if candidate == "":
            return None
        try:
            return int(candidate)
        except ValueError:
            return None
    return None


def parse_bool(value) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return None


def parse_twitter_datetime(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    if "T" in value and value.endswith("Z"):
        return value
    try:
        parsed = datetime.strptime(value, "%a %b %d %H:%M:%S %z %Y")
        return parsed.isoformat()
    except ValueError:
        return value


def load_js_array(path: str) -> List:
    with open(path, "r", encoding="utf-8") as handle:
        raw = handle.read()
    start = raw.find("[")
    end = raw.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"Unable to locate JSON array in {path}")
    return json.loads(raw[start : end + 1])


def find_tweet_files(archive_dir: str) -> List[str]:
    if not os.path.isdir(archive_dir):
        return []
    candidates: Set[str] = set()
    for filename in ("tweets.js", "tweet.js"):
        path = os.path.join(archive_dir, filename)
        if os.path.exists(path):
            candidates.add(path)
    for name in os.listdir(archive_dir):
        if name.startswith("tweets") and name.endswith(".js"):
            candidates.add(os.path.join(archive_dir, name))
    files = sorted(candidates)
    tweet_files = []
    for path in files:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                head = handle.read(512)
            if "window.YTD.tweets" in head:
                tweet_files.append(path)
        except OSError:
            continue
    return tweet_files


def media_file_path(
    archive_dir: str, tweet_id: str, media_url: Optional[str]
) -> Optional[str]:
    if not media_url:
        return None
    parsed = urlparse(media_url)
    basename = os.path.basename(parsed.path)
    if not basename:
        return None
    candidate = os.path.join(archive_dir, "tweets_media", f"{tweet_id}-{basename}")
    return candidate if os.path.exists(candidate) else None


def flush_batches(
    conn: duckdb.DuckDBPyConnection,
    tweet_rows: List[Tuple],
    user_rows: List[Tuple],
    mention_rows: List[Tuple],
    hashtag_rows: List[Tuple],
    url_rows: List[Tuple],
    media_rows: List[Tuple],
) -> None:
    if user_rows:
        conn.executemany(
            "INSERT OR IGNORE INTO users (user_id, screen_name, name) VALUES (?, ?, ?)",
            user_rows,
        )
        user_rows.clear()
    if tweet_rows:
        conn.executemany(
            """
            INSERT OR IGNORE INTO tweets (
                tweet_id,
                created_at,
                full_text,
                lang,
                source,
                retweet_count,
                favorite_count,
                retweeted,
                favorited,
                truncated,
                in_reply_to_status_id,
                in_reply_to_user_id,
                in_reply_to_screen_name,
                display_text_range_start,
                display_text_range_end,
                editable_until,
                edits_remaining,
                is_edit_eligible
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tweet_rows,
        )
        tweet_rows.clear()
    if mention_rows:
        conn.executemany(
            """
            INSERT INTO mentions (
                tweet_id,
                user_id,
                screen_name,
                name,
                start_index,
                end_index
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            mention_rows,
        )
        mention_rows.clear()
    if hashtag_rows:
        conn.executemany(
            """
            INSERT INTO hashtags (
                tweet_id,
                hashtag,
                start_index,
                end_index
            ) VALUES (?, ?, ?, ?)
            """,
            hashtag_rows,
        )
        hashtag_rows.clear()
    if url_rows:
        conn.executemany(
            """
            INSERT INTO urls (
                tweet_id,
                url,
                expanded_url,
                display_url,
                start_index,
                end_index
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            url_rows,
        )
        url_rows.clear()
    if media_rows:
        conn.executemany(
            """
            INSERT INTO media (
                tweet_id,
                media_id,
                media_url,
                media_type,
                file_path
            ) VALUES (?, ?, ?, ?, ?)
            """,
            media_rows,
        )
        media_rows.clear()


def main() -> int:
    args = parse_args()
    archive_dir = args.archive_dir
    if not os.path.isdir(archive_dir):
        print(f"Archive directory not found: {archive_dir}", file=sys.stderr)
        return 1
    tweet_files = find_tweet_files(archive_dir)
    if not tweet_files:
        print(f"No tweet archive files found in {archive_dir}.", file=sys.stderr)
        return 1

    conn = duckdb.connect(args.db)
    tweet_rows: List[Tuple] = []
    user_rows: List[Tuple] = []
    mention_rows: List[Tuple] = []
    hashtag_rows: List[Tuple] = []
    url_rows: List[Tuple] = []
    media_rows: List[Tuple] = []

    total_tweets = 0
    for path in tweet_files:
        items = load_js_array(path)
        for item in items:
            tweet = item.get("tweet") if isinstance(item, dict) else None
            if not tweet:
                continue
            tweet_id = tweet.get("id_str") or tweet.get("id")
            if not tweet_id:
                continue
            tweet_id = str(tweet_id)

            created_at = parse_twitter_datetime(tweet.get("created_at"))
            if created_at is None:
                continue
            full_text = tweet.get("full_text") or tweet.get("text") or ""
            lang = tweet.get("lang")
            source = clean_source(tweet.get("source"))
            retweet_count = parse_int(tweet.get("retweet_count"))
            if retweet_count is None:
                retweet_count = 0
            favorite_count = parse_int(tweet.get("favorite_count"))
            if favorite_count is None:
                favorite_count = 0
            retweeted = parse_bool(tweet.get("retweeted"))
            if retweeted is None:
                retweeted = False
            favorited = parse_bool(tweet.get("favorited"))
            if favorited is None:
                favorited = False
            truncated = parse_bool(tweet.get("truncated"))
            if truncated is None:
                truncated = False

            in_reply_to_status_id = (
                tweet.get("in_reply_to_status_id_str")
                or tweet.get("in_reply_to_status_id")
            )
            in_reply_to_user_id = (
                tweet.get("in_reply_to_user_id_str") or tweet.get("in_reply_to_user_id")
            )
            in_reply_to_screen_name = tweet.get("in_reply_to_screen_name")

            display_range = tweet.get("display_text_range") or []
            display_start = parse_int(display_range[0]) if len(display_range) > 0 else None
            display_end = parse_int(display_range[1]) if len(display_range) > 1 else None

            edit_initial = (tweet.get("edit_info") or {}).get("initial") or {}
            editable_until = edit_initial.get("editableUntil")
            edits_remaining = parse_int(edit_initial.get("editsRemaining"))
            is_edit_eligible = parse_bool(edit_initial.get("isEditEligible"))

            tweet_rows.append(
                (
                    tweet_id,
                    created_at,
                    full_text,
                    lang,
                    source,
                    retweet_count,
                    favorite_count,
                    retweeted,
                    favorited,
                    truncated,
                    str(in_reply_to_status_id)
                    if in_reply_to_status_id is not None
                    else None,
                    str(in_reply_to_user_id) if in_reply_to_user_id is not None else None,
                    in_reply_to_screen_name,
                    display_start,
                    display_end,
                    editable_until,
                    edits_remaining,
                    is_edit_eligible,
                )
            )

            if in_reply_to_user_id is not None:
                user_rows.append(
                    (
                        str(in_reply_to_user_id),
                        in_reply_to_screen_name,
                        None,
                    )
                )

            entities = tweet.get("entities") or {}
            for mention in entities.get("user_mentions", []) or []:
                user_id = mention.get("id_str") or mention.get("id")
                if not user_id:
                    continue
                screen_name = mention.get("screen_name")
                name = mention.get("name")
                indices = mention.get("indices") or []
                start_index = parse_int(indices[0]) if len(indices) > 0 else None
                end_index = parse_int(indices[1]) if len(indices) > 1 else None

                user_rows.append((str(user_id), screen_name, name))
                mention_rows.append(
                    (
                        tweet_id,
                        str(user_id),
                        screen_name or "",
                        name,
                        start_index,
                        end_index,
                    )
                )

            for hashtag in entities.get("hashtags", []) or []:
                tag = hashtag.get("text")
                if not tag:
                    continue
                indices = hashtag.get("indices") or []
                start_index = parse_int(indices[0]) if len(indices) > 0 else None
                end_index = parse_int(indices[1]) if len(indices) > 1 else None
                hashtag_rows.append((tweet_id, tag, start_index, end_index))

            for url in entities.get("urls", []) or []:
                url_value = url.get("url")
                if not url_value:
                    continue
                indices = url.get("indices") or []
                start_index = parse_int(indices[0]) if len(indices) > 0 else None
                end_index = parse_int(indices[1]) if len(indices) > 1 else None
                url_rows.append(
                    (
                        tweet_id,
                        url_value,
                        url.get("expanded_url"),
                        url.get("display_url"),
                        start_index,
                        end_index,
                    )
                )

            media_entities = []
            if (tweet.get("extended_entities") or {}).get("media"):
                media_entities = tweet["extended_entities"]["media"]
            elif entities.get("media"):
                media_entities = entities.get("media")

            media_seen: Set[Tuple[Optional[str], Optional[str]]] = set()
            for media in media_entities or []:
                media_id = media.get("id_str") or media.get("id")
                media_url = media.get("media_url_https") or media.get("media_url")
                if not media_url:
                    continue
                media_type = media.get("type")
                dedupe_key = (str(media_id) if media_id is not None else None, media_url)
                if dedupe_key in media_seen:
                    continue
                media_seen.add(dedupe_key)

                media_rows.append(
                    (
                        tweet_id,
                        str(media_id) if media_id is not None else None,
                        media_url,
                        media_type,
                        media_file_path(archive_dir, tweet_id, media_url),
                    )
                )

            total_tweets += 1
            if total_tweets % BATCH_SIZE == 0:
                flush_batches(
                    conn,
                    tweet_rows,
                    user_rows,
                    mention_rows,
                    hashtag_rows,
                    url_rows,
                    media_rows,
                )

    flush_batches(
        conn, tweet_rows, user_rows, mention_rows, hashtag_rows, url_rows, media_rows
    )

    print(f"Imported {total_tweets} tweets from {len(tweet_files)} file(s).")
    print("Files used:")
    for path in tweet_files:
        print(f"- {path}")
    print("Assumptions:")
    print("- Tweets are stored in window.YTD.tweets.* files inside archive/data.")
    print("- Media files (if present) are stored under archive/data/tweets_media.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
