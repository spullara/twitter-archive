# Twitter Archive DuckDB

Load a Twitter/X account archive into DuckDB for analysis.

## Requirements
- Python 3.7+
- `pip` and the `venv` module
- A Twitter archive in standard export format

## Assumptions
- Archive is in standard Twitter export format (JavaScript files with `window.YTD.*` prefix).
- Archive is located at `archive/data/`.
- Database filename for examples is `twitter.db`.
- Archive files are complete and not corrupted.

## Setup
Run these commands from the repository root:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Create the schema

```bash
python -c "import duckdb; conn = duckdb.connect('twitter.db'); conn.execute(open('schema.sql').read())"
```

## Import data

```bash
python import_tweets.py
python import_metadata.py
```

## Verification commands
These mirror the verification plan for this project:

```bash
python -m venv venv && source venv/bin/activate && pip install -r requirements.txt
python -c "import duckdb; conn = duckdb.connect('twitter.db'); conn.execute(open('schema.sql').read())"
python import_tweets.py
python import_metadata.py
```

Run this SQL against `twitter.db` (for example, in the DuckDB CLI or any SQL client):

```sql
SELECT 'tweets' as table_name, COUNT(*) as count FROM tweets
UNION ALL SELECT 'users', COUNT(*) FROM users
UNION ALL SELECT 'mentions', COUNT(*) FROM mentions
UNION ALL SELECT 'hashtags', COUNT(*) FROM hashtags
UNION ALL SELECT 'likes', COUNT(*) FROM likes;
```

## Example analysis queries
These queries match the schema and should run in DuckDB:

```sql
-- Most mentioned users
SELECT user_id, screen_name, COUNT(*) AS mentions
FROM mentions
GROUP BY user_id, screen_name
ORDER BY mentions DESC;

-- Reply chains (direct replies)
SELECT t.tweet_id,
       t.in_reply_to_status_id,
       parent.full_text AS replied_to_text
FROM tweets t
LEFT JOIN tweets parent
  ON t.in_reply_to_status_id = parent.tweet_id
WHERE t.in_reply_to_status_id IS NOT NULL
LIMIT 50;

-- Engagement over time
SELECT date_trunc('day', created_at) AS day,
       SUM(favorite_count) AS favorites,
       SUM(retweet_count) AS retweets
FROM tweets
GROUP BY day
ORDER BY day;

-- Popular hashtags
SELECT hashtag, COUNT(*) AS uses
FROM hashtags
GROUP BY hashtag
ORDER BY uses DESC;
```

## Notes
- No example data inserts are included; data comes only from your archive.
