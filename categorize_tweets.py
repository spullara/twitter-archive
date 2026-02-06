#!/usr/bin/env python3
"""Categorize tweets using Google Gemini 2.5 Flash Lite API."""

import argparse
import json
import logging
import os
import re
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
LOG_FILE = "categorization.log"

# Set up file logger for detailed categorization logging
cat_logger = logging.getLogger("categorization")
cat_logger.setLevel(logging.INFO)

# Create file handler with append mode
_file_handler = logging.FileHandler(LOG_FILE, mode='a', encoding='utf-8')
_file_handler.setLevel(logging.INFO)

# Create a clean, human-readable format
_formatter = logging.Formatter('[%(asctime)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
_file_handler.setFormatter(_formatter)

# Add handler to logger (avoid duplicates on reimport)
if not cat_logger.handlers:
    cat_logger.addHandler(_file_handler)


def log_tweet_processing(tweet_id: str, full_text: str, categories: list,
                         primary_category: str, confidence: float):
    """Log a tweet being processed with its categorization results."""
    # Truncate text to first 100 chars for readability
    text_preview = full_text[:100].replace('\n', ' ')
    if len(full_text) > 100:
        text_preview += "..."

    cat_logger.info(f"Processing tweet {tweet_id}")
    cat_logger.info(f"  Text: \"{text_preview}\"")
    cat_logger.info(f"  Categories: {', '.join(categories)}")
    cat_logger.info(f"  Primary: {primary_category} (confidence: {confidence:.2f})")


def log_new_category_created(category_name: str, description: str, tweet_id: str):
    """Log when a new custom category is created."""
    cat_logger.info(f"NEW CATEGORY CREATED: {category_name}")
    cat_logger.info(f"  Description: {description}")
    cat_logger.info(f"  First tweet: {tweet_id}")


def log_session_start(tweet_count: int, custom_category_count: int):
    """Log the start of a categorization session."""
    cat_logger.info("=" * 60)
    cat_logger.info(f"CATEGORIZATION SESSION STARTED")
    cat_logger.info(f"  Tweets to process: {tweet_count}")
    cat_logger.info(f"  Existing custom categories: {custom_category_count}")
    cat_logger.info("=" * 60)


def log_session_end(total_processed: int, elapsed_seconds: float, new_categories: int):
    """Log the end of a categorization session."""
    cat_logger.info("-" * 60)
    cat_logger.info(f"CATEGORIZATION SESSION ENDED")
    cat_logger.info(f"  Tweets processed: {total_processed}")
    cat_logger.info(f"  Time elapsed: {elapsed_seconds:.1f} seconds")
    cat_logger.info(f"  Rate: {total_processed / elapsed_seconds:.1f} tweets/sec" if elapsed_seconds > 0 else "  Rate: N/A")
    cat_logger.info(f"  New categories created: {new_categories}")
    cat_logger.info("-" * 60)


# Standard categories that are always available
STANDARD_CATEGORIES = [
    "technical", "personal", "professional", "social", "commentary",
    "humor", "question", "announcement", "retweet", "other"
]

# Global flag for graceful shutdown
shutdown_requested = False


def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully."""
    global shutdown_requested
    print("\n⚠️  Shutdown requested. Finishing current batch and saving progress...")
    shutdown_requested = True


def setup_database(conn: duckdb.DuckDBPyConnection):
    """Create tweet_categories and custom_categories tables if they don't exist."""
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

    # Create custom_categories table for dynamically created categories
    conn.execute("""
        CREATE TABLE IF NOT EXISTS custom_categories (
            category_name VARCHAR PRIMARY KEY,
            description VARCHAR NOT NULL,
            example_tweet_id VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            usage_count INTEGER DEFAULT 1
        )
    """)


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
    conn.execute("DELETE FROM custom_categories")
    conn.execute("DROP SEQUENCE IF EXISTS tweet_categories_id_seq")
    conn.execute("CREATE SEQUENCE tweet_categories_id_seq START 1")
    print("✅ All categories cleared (including custom categories).")


def get_custom_categories(conn: duckdb.DuckDBPyConnection) -> list:
    """Get all custom categories from the database."""
    try:
        results = conn.execute("""
            SELECT category_name, description FROM custom_categories
            ORDER BY usage_count DESC
        """).fetchall()
        return [(r[0], r[1]) for r in results]
    except Exception:
        return []


def get_custom_category_count(conn: duckdb.DuckDBPyConnection) -> int:
    """Get the number of custom categories."""
    try:
        return conn.execute("SELECT COUNT(*) FROM custom_categories").fetchone()[0]
    except Exception:
        return 0


def add_custom_category(conn: duckdb.DuckDBPyConnection, category_name: str,
                        description: str, example_tweet_id: str) -> bool:
    """Add a new custom category. No limit on number of categories."""
    # Validate category name format (lowercase, single word or hyphenated)
    if not re.match(r'^[a-z][a-z0-9-]*$', category_name):
        print(f"  ⚠️  Invalid category name format: '{category_name}'")
        return False

    # Check if it's too similar to existing categories
    all_categories = STANDARD_CATEGORIES + [c[0] for c in get_custom_categories(conn)]
    if category_name in all_categories:
        return True  # Already exists, that's fine

    try:
        conn.execute("""
            INSERT INTO custom_categories (category_name, description, example_tweet_id)
            VALUES (?, ?, ?)
        """, (category_name, description, example_tweet_id))
        print(f"  ✨ New category created: '{category_name}' - {description}")
        log_new_category_created(category_name, description, example_tweet_id)
        return True
    except Exception as e:
        # Might be a duplicate key, which is fine
        if "Duplicate" in str(e) or "unique" in str(e).lower():
            return True
        print(f"  ⚠️  Error creating category '{category_name}': {e}")
        return False


def increment_category_usage(conn: duckdb.DuckDBPyConnection, category_name: str):
    """Increment the usage count for a custom category."""
    try:
        conn.execute("""
            UPDATE custom_categories
            SET usage_count = usage_count + 1
            WHERE category_name = ?
        """, (category_name,))
    except Exception:
        pass  # Ignore errors (might not be a custom category)


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


STANDARD_CATEGORY_DESCRIPTIONS = {
    "technical": "Programming, software development, tech discussions",
    "personal": "Personal updates, thoughts, life events",
    "professional": "Work-related, career, industry news",
    "social": "Conversations, replies, social interactions",
    "commentary": "News sharing, political/social commentary",
    "humor": "Jokes, memes, funny observations",
    "question": "Asking for help or information",
    "announcement": "Product launches, event announcements",
    "retweet": "Shared/retweeted content",
    "other": "Doesn't fit other categories"
}


def build_category_prompt(custom_categories: list, can_create_new: bool = True) -> str:
    """Build the category prompt dynamically with custom categories."""
    # Start with standard categories
    category_lines = []
    for cat, desc in STANDARD_CATEGORY_DESCRIPTIONS.items():
        category_lines.append(f"- {cat}: {desc}")

    # Add custom categories if any
    if custom_categories:
        category_lines.append("")
        category_lines.append("Custom categories (previously created):")
        for cat_name, cat_desc in custom_categories:
            category_lines.append(f"- {cat_name}: {cat_desc}")

    categories_text = "\n".join(category_lines)

    # Build the new category instruction if creation is allowed
    new_category_instruction = ""
    if can_create_new:
        new_category_instruction = """

NEW CATEGORY CREATION:
Before using "other", consider if this tweet represents a recurring pattern that deserves its own category.
If the tweet doesn't fit well into existing categories, CREATE A NEW category using "new_category":
{{"name": "category-name", "description": "Brief description of what this category covers"}}

Examples of good new categories:
- "link-share": Sharing URLs/links without much commentary
- "recommendation": Suggesting products, services, or content
- "rant": Expressing frustration or strong negative opinions
- "appreciation": Expressing gratitude or praise
- "meta": Tweets about Twitter/tweeting itself

Category name rules:
- Lowercase, single word or hyphenated (e.g., "media-sharing", "hot-take")
- Keep descriptions under 50 characters
- Only use "other" as last resort""".replace("{", "{{").replace("}", "}}")

    prompt = f"""Analyze this tweet and categorize it into one or more of these categories:
{categories_text}

Tweet: "{{tweet_text}}"

Respond with ONLY a JSON object in this exact format (no markdown, no explanation):
{{{{"categories": ["category1", "category2"], "primary": "category1", "confidence": 0.85}}}}

Or if creating a new category:
{{{{"categories": ["new-category-name"], "primary": "new-category-name", "confidence": 0.85, "new_category": {{{{"name": "new-category-name", "description": "Brief description"}}}}}}}}
{new_category_instruction}
Rules:
- "categories" should be 1-3 most relevant categories
- "primary" should be the single best category
- "confidence" should be 0.0-1.0 indicating certainty
- Prefer existing categories when they fit reasonably well"""

    return prompt


def categorize_batch(client, conn: duckdb.DuckDBPyConnection, tweets: list) -> list:
    """Categorize a batch of tweets using Gemini API with dynamic category support."""
    results = []

    # Get custom categories at batch start
    custom_categories = get_custom_categories(conn)

    for tweet_id, full_text, created_at, lang in tweets:
        if shutdown_requested:
            break

        try:
            # Build dynamic prompt with current custom categories (always allow new categories)
            prompt_template = build_category_prompt(custom_categories, can_create_new=True)
            prompt = prompt_template.format(tweet_text=full_text[:1000])  # Limit text length

            response = client.models.generate_content(
                model="gemini-2.0-flash-lite",
                contents=prompt
            )

            # Parse JSON response
            response_text = response.text.strip()
            # Remove markdown code blocks if present
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                # Skip the first line (```json or ```) and remove the last line (```)
                response_text = "\n".join(lines[1:-1]).strip() if len(lines) > 2 else response_text

            data = json.loads(response_text)

            # Handle various response formats
            if isinstance(data, dict):
                categories = data.get("categories", [])
                if not categories:
                    primary = data.get("primary", "other")
                    categories = [primary] if primary else ["other"]
                confidence = data.get("confidence", 0.5)
            else:
                # Unexpected format
                categories = ["other"]
                confidence = 0.0

            # Handle new category creation
            new_category = data.get("new_category") if isinstance(data, dict) else None
            if new_category and isinstance(new_category, dict):
                cat_name = new_category.get("name", "").lower().strip()
                cat_desc = new_category.get("description", "")

                if cat_name and cat_desc:
                    if add_custom_category(conn, cat_name, cat_desc, tweet_id):
                        # Refresh custom categories for subsequent tweets in this batch
                        custom_categories = get_custom_categories(conn)

            # Log the tweet processing and categorization decision
            primary_category = data.get("primary", categories[0] if categories else "other")
            log_tweet_processing(
                tweet_id=tweet_id,
                full_text=full_text,
                categories=categories,
                primary_category=primary_category,
                confidence=confidence
            )

            # Track custom category usage
            existing_custom_cats = {c[0] for c in custom_categories}
            all_known_cats = set(STANDARD_CATEGORIES) | existing_custom_cats

            for cat in categories:
                cat_lower = cat.lower() if isinstance(cat, str) else str(cat).lower()

                # If category is not known, try to auto-create it
                if cat_lower not in all_known_cats:
                    # Check if it's a valid category name format
                    if re.match(r'^[a-z][a-z0-9-]*$', cat_lower):
                        # Auto-create the category
                        desc = f"Auto-created category: {cat_lower}"
                        if add_custom_category(conn, cat_lower, desc, tweet_id):
                            custom_categories = get_custom_categories(conn)
                            existing_custom_cats = {c[0] for c in custom_categories}
                            all_known_cats = set(STANDARD_CATEGORIES) | existing_custom_cats

                # Increment usage count for custom categories
                if cat_lower in existing_custom_cats:
                    increment_category_usage(conn, cat_lower)

                results.append({
                    "tweet_id": tweet_id,
                    "category": cat_lower,
                    "confidence": confidence if cat == data.get("primary") else confidence * 0.8,
                    "raw_response": response_text
                })

            time.sleep(RATE_LIMIT_DELAY)  # Rate limiting

        except json.JSONDecodeError as e:
            print(f"  ⚠️  JSON parse error for tweet {tweet_id}: {e}")
            # Show raw response for debugging
            raw = response.text if 'response' in locals() else str(e)
            if len(raw) < 200:
                print(f"      Raw response: {raw}")
            results.append({
                "tweet_id": tweet_id,
                "category": "other",
                "confidence": 0.0,
                "raw_response": raw
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
    """Display category distribution statistics including custom categories."""
    # Get all category counts
    results = conn.execute("""
        SELECT category, COUNT(*) as count
        FROM tweet_categories
        GROUP BY category
        ORDER BY count DESC
    """).fetchall()

    # Get custom categories
    custom_cats = {c[0]: c[1] for c in get_custom_categories(conn)}

    # Separate standard and custom categories
    standard_results = [(cat, count) for cat, count in results if cat in STANDARD_CATEGORIES]
    custom_results = [(cat, count) for cat, count in results if cat in custom_cats]
    unknown_results = [(cat, count) for cat, count in results
                       if cat not in STANDARD_CATEGORIES and cat not in custom_cats]

    total = sum(r[1] for r in results)

    # Show standard categories
    print("\n📊 Standard Categories:")
    print("-" * 50)
    for category, count in standard_results:
        pct = (count / total * 100) if total > 0 else 0
        bar = "█" * int(pct / 2)
        print(f"  {category:20} {count:6} ({pct:5.1f}%) {bar}")

    # Show custom categories if any
    if custom_results or custom_cats:
        print("\n✨ Custom Categories:")
        print("-" * 50)
        custom_count = len(custom_cats)
        print(f"  ({custom_count} custom categories)")
        print()
        for category, count in custom_results:
            pct = (count / total * 100) if total > 0 else 0
            bar = "█" * int(pct / 2)
            desc = custom_cats.get(category, "")
            desc_short = (desc[:25] + "...") if len(desc) > 28 else desc
            print(f"  {category:20} {count:6} ({pct:5.1f}%) {bar}")
            if desc_short:
                print(f"    └─ {desc_short}")

    # Show unknown categories (shouldn't happen normally)
    if unknown_results:
        print("\n⚠️  Unknown Categories:")
        print("-" * 50)
        for category, count in unknown_results:
            pct = (count / total * 100) if total > 0 else 0
            print(f"  {category:20} {count:6} ({pct:5.1f}%)")

    print("\n" + "-" * 50)
    print(f"  {'TOTAL':20} {total:6}")

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

    # Show custom category status
    custom_count = get_custom_category_count(conn)
    custom_count_before = custom_count  # Track for logging new categories at end
    if custom_count > 0:
        print(f"✨ Using {custom_count} custom categories (unlimited)")
    else:
        print(f"✨ Dynamic category creation enabled (unlimited)")

    # Configure Gemini API client
    client = genai.Client(api_key=api_key)

    # Process tweets in batches
    total_processed = 0
    all_results = []
    start_time = time.time()

    # Log session start
    log_session_start(len(tweets), custom_count)

    print("\n🚀 Starting categorization...")

    try:
        for i in range(0, len(tweets), args.batch_size):
            if shutdown_requested:
                break

            batch = tweets[i:i + args.batch_size]
            batch_num = i // args.batch_size + 1
            total_batches = (len(tweets) + args.batch_size - 1) // args.batch_size

            print(f"  📦 Batch {batch_num}/{total_batches} ({len(batch)} tweets)...", end=" ", flush=True)

            results = categorize_batch(client, conn, batch)
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

    # Log session end
    custom_count_after = get_custom_category_count(conn)
    new_categories_created = custom_count_after - custom_count_before
    log_session_end(total_processed, elapsed, new_categories_created)

    show_stats(conn)
    conn.close()

    if shutdown_requested:
        print("\n💡 Tip: Run the script again to continue from where you left off.")


if __name__ == "__main__":
    main()
