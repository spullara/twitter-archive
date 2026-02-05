# Twitter Archive Analyzer

A DuckDB-based tool for analyzing your Twitter archive data.

## Prerequisites

- Python 3.7 or higher
- `pip` and `venv` modules available
- A Twitter archive exported in the standard format (JavaScript files with `window.YTD.*` prefix)

## Setup

### 1. Create and activate a virtual environment

```bash
python -m venv venv
source venv/bin/activate  # On macOS/Linux
# or: venv\Scripts\activate  # On Windows
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Load the database schema

```bash
python -c "import duckdb; conn = duckdb.connect('twitter.db'); conn.execute(open('schema.sql').read())"
```

### 4. Place your Twitter archive

Ensure your archive is extracted to `archive/data/`. The directory should contain files like:
- `tweets.js`
- `like.js`
- `follower.js`
- `following.js`
- `account.js`

### 5. Import tweets and entities

```bash
python import_tweets.py
```

This imports tweets, users, hashtags, mentions, URLs, and media metadata.

### 6. Import metadata (likes, followers, following, account)

```bash
python import_metadata.py
```

## Verification

After importing, verify the data was loaded correctly:

```bash
python -c "
import duckdb
conn = duckdb.connect('twitter.db')
result = conn.execute('''
    SELECT 'tweets' as table_name, COUNT(*) as count FROM tweets
    UNION ALL SELECT 'users', COUNT(*) FROM users
    UNION ALL SELECT 'mentions', COUNT(*) FROM mentions
    UNION ALL SELECT 'hashtags', COUNT(*) FROM hashtags
    UNION ALL SELECT 'likes', COUNT(*) FROM likes
''').fetchall()
for row in result:
    print(f'{row[0]}: {row[1]}')"
```

## Example Analysis Queries

### Most Mentioned Users

```sql
SELECT user_id, screen_name, COUNT(*) as mention_count
FROM mentions
GROUP BY user_id, screen_name
ORDER BY mention_count DESC
LIMIT 10;
```

### Most Popular Hashtags

```sql
SELECT hashtag, COUNT(*) as usage_count
FROM hashtags
GROUP BY hashtag
ORDER BY usage_count DESC
LIMIT 10;
```

### Engagement Over Time (by month)

```sql
SELECT strftime(created_at, '%Y-%m') as month,
       SUM(favorite_count) as total_favorites,
       SUM(retweet_count) as total_retweets
FROM tweets
GROUP BY month
ORDER BY month;
```

### Most Active Hours

```sql
SELECT EXTRACT(HOUR FROM created_at) as hour,
       COUNT(*) as tweet_count
FROM tweets
GROUP BY hour
ORDER BY tweet_count DESC;
```

### Language Distribution

```sql
SELECT lang, COUNT(*) as count
FROM tweets
GROUP BY lang
ORDER BY count DESC;
```

### Reply Chains (find replies to your tweets)

```sql
SELECT t.tweet_id, t.full_text, t.in_reply_to_status_id
FROM tweets t
WHERE t.in_reply_to_status_id IS NOT NULL
LIMIT 20;
```

### Media Usage by Type

```sql
SELECT media_type, COUNT(*) as count
FROM media
GROUP BY media_type
ORDER BY count DESC;
```

## Running Queries

Use the DuckDB CLI or Python:

```bash
# DuckDB CLI
duckdb twitter.db

# Python
python -c "
import duckdb
conn = duckdb.connect('twitter.db')
result = conn.execute('SELECT COUNT(*) FROM tweets').fetchone()
print(f'Total tweets: {result[0]}')"
```

## Files

- `schema.sql` - Database schema with all 10 tables
- `import_tweets.py` - Imports tweets and related entities
- `import_metadata.py` - Imports likes, followers, following, account
- `requirements.txt` - Python dependencies (duckdb)
- `twitter.db` - Generated database (after running import scripts)

