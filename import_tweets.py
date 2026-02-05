#!/usr/bin/env python3
"""Import tweets and related entities from Twitter archive into DuckDB."""

import json
import os
import re
from datetime import datetime
import duckdb

# Default paths
DEFAULT_ARCHIVE_PATH = "archive/data"
DEFAULT_DB_PATH = "twitter.db"
BATCH_SIZE = 1000


def load_js_file(filepath: str) -> list:
    """Load a Twitter archive .js file, stripping the window.YTD.* prefix."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Strip the window.YTD.*.part0 = prefix
    match = re.match(r'^window\.YTD\.\w+\.part\d+\s*=\s*', content)
    if match:
        content = content[match.end():]
    
    return json.loads(content)


def parse_twitter_date(date_str: str) -> datetime:
    """Parse Twitter's date format: 'Thu Feb 05 17:09:09 +0000 2026'"""
    return datetime.strptime(date_str, '%a %b %d %H:%M:%S %z %Y')


def import_tweets(archive_path: str = DEFAULT_ARCHIVE_PATH, db_path: str = DEFAULT_DB_PATH):
    """Import tweets and related entities from the archive."""
    tweets_file = os.path.join(archive_path, "tweets.js")
    
    if not os.path.exists(tweets_file):
        print(f"Error: {tweets_file} not found")
        return
    
    print(f"Loading tweets from {tweets_file}...")
    tweets_data = load_js_file(tweets_file)
    print(f"Loaded {len(tweets_data)} tweets")
    
    # Connect to database
    conn = duckdb.connect(db_path)
    
    # Prepare batch lists
    users_batch = []
    tweets_batch = []
    hashtags_batch = []
    mentions_batch = []
    urls_batch = []
    media_batch = []
    
    seen_users = set()  # Track users to avoid duplicates within batch
    
    for item in tweets_data:
        tweet = item.get('tweet', {})
        tweet_id = tweet.get('id_str')
        
        if not tweet_id:
            continue
        
        # Parse tweet data
        created_at = parse_twitter_date(tweet.get('created_at'))
        edit_info = tweet.get('edit_info', {}).get('initial', {})
        editable_until_str = edit_info.get('editableUntil')
        editable_until = datetime.fromisoformat(editable_until_str.replace('Z', '+00:00')) if editable_until_str else None
        display_range = tweet.get('display_text_range', [None, None])
        
        # Add tweet
        tweets_batch.append((
            tweet_id,
            created_at,
            tweet.get('full_text', ''),
            tweet.get('lang'),
            tweet.get('source'),
            int(tweet.get('retweet_count', 0)),
            int(tweet.get('favorite_count', 0)),
            tweet.get('retweeted', False),
            tweet.get('favorited', False),
            tweet.get('truncated', False),
            tweet.get('in_reply_to_status_id_str'),
            tweet.get('in_reply_to_user_id_str'),
            tweet.get('in_reply_to_screen_name'),
            int(display_range[0]) if display_range[0] else None,
            int(display_range[1]) if display_range[1] else None,
            editable_until,
            int(edit_info.get('editsRemaining', 0)) if edit_info.get('editsRemaining') else None,
            edit_info.get('isEditEligible', False),
        ))
        
        # Extract entities
        entities = tweet.get('entities', {})
        
        # Process user mentions (also adds to users table)
        for mention in entities.get('user_mentions', []):
            user_id = mention.get('id_str')
            if user_id and user_id not in seen_users:
                users_batch.append((user_id, mention.get('screen_name'), mention.get('name')))
                seen_users.add(user_id)
            
            indices = mention.get('indices', [None, None])
            mentions_batch.append((
                tweet_id,
                user_id,
                mention.get('screen_name'),
                mention.get('name'),
                int(indices[0]) if indices[0] else None,
                int(indices[1]) if indices[1] else None,
            ))
        
        # Process in_reply_to user (add to users table if not seen)
        reply_user_id = tweet.get('in_reply_to_user_id_str')
        if reply_user_id and reply_user_id not in seen_users:
            users_batch.append((reply_user_id, tweet.get('in_reply_to_screen_name'), None))
            seen_users.add(reply_user_id)
        
        # Process hashtags
        for hashtag in entities.get('hashtags', []):
            indices = hashtag.get('indices', [None, None])
            hashtags_batch.append((
                tweet_id,
                hashtag.get('text'),
                int(indices[0]) if indices[0] else None,
                int(indices[1]) if indices[1] else None,
            ))
        
        # Process URLs
        for url in entities.get('urls', []):
            indices = url.get('indices', [None, None])
            urls_batch.append((
                tweet_id,
                url.get('url'),
                url.get('expanded_url'),
                url.get('display_url'),
                int(indices[0]) if indices[0] else None,
                int(indices[1]) if indices[1] else None,
            ))
        
        # Process media (from entities and extended_entities)
        media_entities = entities.get('media', [])
        extended_media = tweet.get('extended_entities', {}).get('media', [])
        # Combine and dedupe by media_id
        seen_media = set()
        for m in media_entities + extended_media:
            media_id = m.get('id_str')
            if media_id and media_id not in seen_media:
                seen_media.add(media_id)
                media_batch.append((
                    tweet_id,
                    media_id,
                    m.get('media_url_https') or m.get('media_url'),
                    m.get('type'),
                    None,  # file_path - could be populated later
                ))
    
    # Batch insert all data
    print("Inserting users...")
    if users_batch:
        conn.executemany(
            "INSERT OR IGNORE INTO users (user_id, screen_name, name) VALUES (?, ?, ?)",
            users_batch
        )
    print(f"  Processed {len(users_batch)} users")

    print("Inserting tweets...")
    if tweets_batch:
        conn.executemany(
            """INSERT OR IGNORE INTO tweets (
                tweet_id, created_at, full_text, lang, source,
                retweet_count, favorite_count, retweeted, favorited, truncated,
                in_reply_to_status_id, in_reply_to_user_id, in_reply_to_screen_name,
                display_text_range_start, display_text_range_end,
                editable_until, edits_remaining, is_edit_eligible
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            tweets_batch
        )
    print(f"  Processed {len(tweets_batch)} tweets")

    print("Inserting hashtags...")
    if hashtags_batch:
        conn.executemany(
            "INSERT INTO hashtags (tweet_id, hashtag, start_index, end_index) VALUES (?, ?, ?, ?)",
            hashtags_batch
        )
    print(f"  Processed {len(hashtags_batch)} hashtags")

    print("Inserting mentions...")
    if mentions_batch:
        conn.executemany(
            "INSERT INTO mentions (tweet_id, user_id, screen_name, name, start_index, end_index) VALUES (?, ?, ?, ?, ?, ?)",
            mentions_batch
        )
    print(f"  Processed {len(mentions_batch)} mentions")

    print("Inserting urls...")
    if urls_batch:
        conn.executemany(
            "INSERT INTO urls (tweet_id, url, expanded_url, display_url, start_index, end_index) VALUES (?, ?, ?, ?, ?, ?)",
            urls_batch
        )
    print(f"  Processed {len(urls_batch)} urls")

    print("Inserting media...")
    if media_batch:
        conn.executemany(
            "INSERT INTO media (tweet_id, media_id, media_url, media_type, file_path) VALUES (?, ?, ?, ?, ?)",
            media_batch
        )
    print(f"  Processed {len(media_batch)} media items")

    conn.close()
    print("Import complete!")


if __name__ == "__main__":
    import sys
    archive_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ARCHIVE_PATH
    db_path = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_DB_PATH
    import_tweets(archive_path, db_path)

