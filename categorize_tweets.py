#!/usr/bin/env python3
"""Categorize tweets using Google Gemini 2.5 Flash Lite API."""

import argparse
import json
import os
import signal
import sys
import time
from datetime import datetime

import duckdb
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Configuration
DEFAULT_DB_PATH = "twitter.db"
BATCH_SIZE = 10  # Number of tweets per API call
SAVE_INTERVAL = 50  # Save progress every N tweets
RATE_LIMIT_DELAY = 0.5  # Seconds between API calls

# Global flag for graceful shutdown
shutdown_requested = False


def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully."""
    global shutdown_requested
    print("\n⚠️  Shutdown requested. Finishing current batch and saving progress...")
    shutdown_requested = True


def setup_database(conn: duckdb.DuckDBPyConnection):
    """Create tweet_categories table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tweet_categories (
            id BIGINT PRIMARY KEY DEFAULT nextval('tweet_categories_id_seq'),
            tweet_id TEXT NOT NULL,
            category TEXT NOT NULL,
            confidence FLOAT,
            categorized_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            raw_response TEXT,
            FOREIGN KEY (tweet_id) REFERENCES tweets(tweet_id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tweet_categories_tweet ON tweet_categories(tweet_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tweet_categories_category ON tweet_categories(category)")


def setup_sequence(conn: duckdb.DuckDBPyConnection):
    """Create sequence for tweet_categories if it doesn't exist."""
    try:
        conn.execute("CREATE SEQUENCE IF NOT EXISTS tweet_categories_id_seq START 1")
    except Exception:
        pass  # Sequence might already exist


def reset_categories(conn: duckdb.DuckDBPyConnection):
    """Delete all categories and reset."""
    print("🗑️  Resetting all categories...")
    conn.execute("DELETE FROM tweet_categories")
    conn.execute("DROP SEQUENCE IF EXISTS tweet_categories_id_seq")
    conn.execute("CREATE SEQUENCE tweet_categories_id_seq START 1")
    print("✅ All categories cleared.")


def get_uncategorized_tweets(conn: duckdb.DuckDBPyConnection, limit: int = None) -> list:
    """Get tweets that haven't been categorized yet."""
    query = """
        SELECT t.tweet_id, t.full_text, t.created_at, t.lang
        FROM tweets t
        LEFT JOIN (
            SELECT DISTINCT tweet_id FROM tweet_categories
        ) tc ON t.tweet_id = tc.tweet_id
        WHERE tc.tweet_id IS NULL
        ORDER BY t.created_at DESC
    """
    if limit:
        query += f" LIMIT {limit}"

    return conn.execute(query).fetchall()


CATEGORY_PROMPT = """Analyze this tweet and categorize it into one or more of these categories:
- technical: Programming, software development, tech discussions
- personal: Personal updates, thoughts, life events
- professional: Work-related, career, industry news
- social: Conversations, replies, social interactions
- commentary: News sharing, political/social commentary
- humor: Jokes, memes, funny observations
- question: Asking for help or information
- announcement: Product launches, event announcements
- retweet: Shared/retweeted content
- other: Doesn't fit other categories

Tweet: "{tweet_text}"

Respond with ONLY a JSON object in this exact format (no markdown, no explanation):
{{"categories": ["category1", "category2"], "primary": "category1", "confidence": 0.85}}

Rules:
- "categories" should be 1-3 most relevant categories
- "primary" should be the single best category
- "confidence" should be 0.0-1.0 indicating certainty"""


def categorize_batch(client, tweets: list) -> list:
    """Categorize a batch of tweets using Gemini API."""
    results = []

    for tweet_id, full_text, created_at, lang in tweets:
        if shutdown_requested:
            break

        try:
            prompt = CATEGORY_PROMPT.format(tweet_text=full_text[:1000])  # Limit text length
            response = client.models.generate_content(
                model="gemini-2.0-flash-lite",
                contents=prompt
            )

            # Parse JSON response
            response_text = response.text.strip()
            # Remove markdown code blocks if present
            if response_text.startswith("```"):
                response_text = response_text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            data = json.loads(response_text)
            categories = data.get("categories", [data.get("primary", "other")])
            confidence = data.get("confidence", 0.5)

            for cat in categories:
                results.append({
                    "tweet_id": tweet_id,
                    "category": cat.lower(),
                    "confidence": confidence if cat == data.get("primary") else confidence * 0.8,
                    "raw_response": response_text
                })

            time.sleep(RATE_LIMIT_DELAY)  # Rate limiting

        except json.JSONDecodeError as e:
            print(f"  ⚠️  JSON parse error for tweet {tweet_id}: {e}")
            results.append({
                "tweet_id": tweet_id,
                "category": "other",
                "confidence": 0.0,
                "raw_response": response.text if 'response' in dir() else str(e)
            })
        except Exception as e:
            print(f"  ❌ Error categorizing tweet {tweet_id}: {e}")
            if "429" in str(e) or "rate" in str(e).lower():
                print("  ⏳ Rate limited. Waiting 60 seconds...")
                time.sleep(60)
            time.sleep(1)  # Brief pause on error

    return results


def save_results(conn: duckdb.DuckDBPyConnection, results: list):
    """Save categorization results to database."""
    if not results:
        return

    for r in results:
        conn.execute("""
            INSERT INTO tweet_categories (tweet_id, category, confidence, raw_response)
            VALUES (?, ?, ?, ?)
        """, (r["tweet_id"], r["category"], r["confidence"], r["raw_response"]))


def show_stats(conn: duckdb.DuckDBPyConnection):
    """Display category distribution statistics."""
    print("\n📊 Category Distribution:")
    print("-" * 40)

    results = conn.execute("""
        SELECT category, COUNT(*) as count
        FROM tweet_categories
        GROUP BY category
        ORDER BY count DESC
    """).fetchall()

    total = sum(r[1] for r in results)
    for category, count in results:
        pct = (count / total * 100) if total > 0 else 0
        bar = "█" * int(pct / 2)
        print(f"  {category:15} {count:6} ({pct:5.1f}%) {bar}")

    print("-" * 40)
    print(f"  {'TOTAL':15} {total:6}")

    # Show unique tweets categorized
    unique_tweets = conn.execute(
        "SELECT COUNT(DISTINCT tweet_id) FROM tweet_categories"
    ).fetchone()[0]
    total_tweets = conn.execute("SELECT COUNT(*) FROM tweets").fetchone()[0]
    print(f"\n📈 Progress: {unique_tweets:,} / {total_tweets:,} tweets categorized ({unique_tweets/total_tweets*100:.1f}%)")


def main():
    global shutdown_requested

    parser = argparse.ArgumentParser(
        description="Categorize tweets using Google Gemini 2.5 Flash Lite API"
    )
    parser.add_argument(
        "--db", type=str, default=DEFAULT_DB_PATH,
        help=f"Path to DuckDB database (default: {DEFAULT_DB_PATH})"
    )
    parser.add_argument(
        "--sample", type=int, metavar="N",
        help="Only categorize N tweets (for testing)"
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Clear all existing categories and start fresh"
    )
    parser.add_argument(
        "--stats", action="store_true",
        help="Show category statistics and exit"
    )
    parser.add_argument(
        "--batch-size", type=int, default=BATCH_SIZE,
        help=f"Tweets per batch (default: {BATCH_SIZE})"
    )
    args = parser.parse_args()

    # Load environment variables
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ Error: GEMINI_API_KEY not found in .env file")
        sys.exit(1)

    # Set up signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Connect to database
    if not os.path.exists(args.db):
        print(f"❌ Error: Database not found: {args.db}")
        sys.exit(1)

    conn = duckdb.connect(args.db)

    # Set up database schema
    setup_sequence(conn)
    setup_database(conn)

    # Handle --stats flag
    if args.stats:
        show_stats(conn)
        conn.close()
        return

    # Handle --reset flag
    if args.reset:
        reset_categories(conn)

    # Get uncategorized tweets
    tweets = get_uncategorized_tweets(conn, limit=args.sample)

    if not tweets:
        print("✅ All tweets have been categorized!")
        show_stats(conn)
        conn.close()
        return

    print(f"📝 Found {len(tweets):,} uncategorized tweets")
    if args.sample:
        print(f"   (Sample mode: processing {args.sample} tweets)")

    # Configure Gemini API client
    client = genai.Client(api_key=api_key)

    # Process tweets in batches
    total_processed = 0
    all_results = []
    start_time = time.time()

    print("\n🚀 Starting categorization...")

    try:
        for i in range(0, len(tweets), args.batch_size):
            if shutdown_requested:
                break

            batch = tweets[i:i + args.batch_size]
            batch_num = i // args.batch_size + 1
            total_batches = (len(tweets) + args.batch_size - 1) // args.batch_size

            print(f"  📦 Batch {batch_num}/{total_batches} ({len(batch)} tweets)...", end=" ", flush=True)

            results = categorize_batch(client, batch)
            all_results.extend(results)
            total_processed += len(batch)

            print(f"✅ ({len(results)} categories)")

            # Save periodically
            if total_processed % SAVE_INTERVAL == 0 or shutdown_requested:
                save_results(conn, all_results)
                all_results = []

    except KeyboardInterrupt:
        shutdown_requested = True
        print("\n⚠️  Interrupted!")

    # Save any remaining results
    if all_results:
        print("💾 Saving final results...")
        save_results(conn, all_results)

    elapsed = time.time() - start_time
    print(f"\n⏱️  Completed in {elapsed:.1f} seconds ({total_processed / elapsed:.1f} tweets/sec)")

    show_stats(conn)
    conn.close()

    if shutdown_requested:
        print("\n💡 Tip: Run the script again to continue from where you left off.")


if __name__ == "__main__":
    main()
