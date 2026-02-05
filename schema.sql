-- Twitter Archive Database Schema for DuckDB
-- Creates all tables, sequences, indexes, and foreign key constraints

-- ============================================================================
-- SEQUENCES (for auto-incrementing surrogate keys)
-- ============================================================================

CREATE SEQUENCE hashtags_id_seq START 1;
CREATE SEQUENCE mentions_id_seq START 1;
CREATE SEQUENCE urls_id_seq START 1;
CREATE SEQUENCE media_id_seq START 1;
CREATE SEQUENCE likes_id_seq START 1;

-- ============================================================================
-- TABLES
-- ============================================================================

-- 1. users: Referenced users from mentions, replies, and account data
CREATE TABLE users (
    user_id TEXT PRIMARY KEY,
    screen_name TEXT,
    name TEXT,
    UNIQUE(screen_name)
);

CREATE INDEX idx_users_screen_name ON users(screen_name);

-- 2. tweets: Primary table for all tweet content and metadata
CREATE TABLE tweets (
    tweet_id TEXT PRIMARY KEY,
    created_at TIMESTAMP NOT NULL,
    full_text TEXT NOT NULL,
    lang TEXT,
    source TEXT,
    retweet_count INTEGER DEFAULT 0,
    favorite_count INTEGER DEFAULT 0,
    retweeted BOOLEAN DEFAULT FALSE,
    favorited BOOLEAN DEFAULT FALSE,
    truncated BOOLEAN DEFAULT FALSE,
    
    -- Reply information
    in_reply_to_status_id TEXT,
    in_reply_to_user_id TEXT,
    in_reply_to_screen_name TEXT,
    
    -- Display metadata
    display_text_range_start INTEGER,
    display_text_range_end INTEGER,
    
    -- Edit information
    editable_until TIMESTAMP,
    edits_remaining INTEGER,
    is_edit_eligible BOOLEAN,
    
    FOREIGN KEY (in_reply_to_user_id) REFERENCES users(user_id)
);

CREATE INDEX idx_tweets_created_at ON tweets(created_at);
CREATE INDEX idx_tweets_in_reply_to ON tweets(in_reply_to_status_id);
CREATE INDEX idx_tweets_lang ON tweets(lang);

-- 3. hashtags: Hashtags extracted from tweets
CREATE TABLE hashtags (
    id BIGINT PRIMARY KEY DEFAULT nextval('hashtags_id_seq'),
    tweet_id TEXT NOT NULL,
    hashtag TEXT NOT NULL,
    start_index INTEGER,
    end_index INTEGER,
    FOREIGN KEY (tweet_id) REFERENCES tweets(tweet_id)
);

CREATE INDEX idx_hashtags_tweet ON hashtags(tweet_id);
CREATE INDEX idx_hashtags_tag ON hashtags(hashtag);

-- 4. mentions: User mentions within tweets
CREATE TABLE mentions (
    id BIGINT PRIMARY KEY DEFAULT nextval('mentions_id_seq'),
    tweet_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    screen_name TEXT NOT NULL,
    name TEXT,
    start_index INTEGER,
    end_index INTEGER,
    FOREIGN KEY (tweet_id) REFERENCES tweets(tweet_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE INDEX idx_mentions_tweet ON mentions(tweet_id);
CREATE INDEX idx_mentions_user ON mentions(user_id);

-- 5. urls: URLs shared in tweets
CREATE TABLE urls (
    id BIGINT PRIMARY KEY DEFAULT nextval('urls_id_seq'),
    tweet_id TEXT NOT NULL,
    url TEXT NOT NULL,
    expanded_url TEXT,
    display_url TEXT,
    start_index INTEGER,
    end_index INTEGER,
    FOREIGN KEY (tweet_id) REFERENCES tweets(tweet_id)
);

CREATE INDEX idx_urls_tweet ON urls(tweet_id);
CREATE INDEX idx_urls_expanded ON urls(expanded_url);

-- 6. media: Media attachments (photos, videos, GIFs)
CREATE TABLE media (
    id BIGINT PRIMARY KEY DEFAULT nextval('media_id_seq'),
    tweet_id TEXT NOT NULL,
    media_id TEXT,
    media_url TEXT,
    media_type TEXT,
    file_path TEXT,
    FOREIGN KEY (tweet_id) REFERENCES tweets(tweet_id)
);

CREATE INDEX idx_media_tweet ON media(tweet_id);
CREATE INDEX idx_media_type ON media(media_type);

-- 7. likes: Tweets liked by the account owner
CREATE TABLE likes (
    id BIGINT PRIMARY KEY DEFAULT nextval('likes_id_seq'),
    tweet_id TEXT NOT NULL,
    full_text TEXT,
    expanded_url TEXT,
    liked_at TIMESTAMP
);

CREATE INDEX idx_likes_tweet ON likes(tweet_id);

-- 8. followers: Accounts following the user
CREATE TABLE followers (
    account_id TEXT PRIMARY KEY,
    user_link TEXT,
    followed_at TIMESTAMP
);

-- 9. following: Accounts the user follows
CREATE TABLE following (
    account_id TEXT PRIMARY KEY,
    user_link TEXT,
    followed_at TIMESTAMP
);

-- 10. account: The account owner's information
CREATE TABLE account (
    account_id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    account_display_name TEXT,
    email TEXT,
    created_via TEXT,
    created_at TIMESTAMP
);

