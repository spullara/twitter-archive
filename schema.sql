CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    screen_name TEXT,
    name TEXT,
    UNIQUE (screen_name)
);

CREATE INDEX IF NOT EXISTS idx_users_screen_name ON users(screen_name);

CREATE TABLE IF NOT EXISTS tweets (
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
    in_reply_to_status_id TEXT,
    in_reply_to_user_id TEXT,
    in_reply_to_screen_name TEXT,
    display_text_range_start INTEGER,
    display_text_range_end INTEGER,
    editable_until TIMESTAMP,
    edits_remaining INTEGER,
    is_edit_eligible BOOLEAN,
    FOREIGN KEY (in_reply_to_user_id) REFERENCES users(user_id)
);

CREATE INDEX IF NOT EXISTS idx_tweets_created_at ON tweets(created_at);
CREATE INDEX IF NOT EXISTS idx_tweets_in_reply_to ON tweets(in_reply_to_status_id);
CREATE INDEX IF NOT EXISTS idx_tweets_lang ON tweets(lang);

CREATE SEQUENCE IF NOT EXISTS hashtags_id_seq;
CREATE SEQUENCE IF NOT EXISTS mentions_id_seq;
CREATE SEQUENCE IF NOT EXISTS urls_id_seq;
CREATE SEQUENCE IF NOT EXISTS media_id_seq;
CREATE SEQUENCE IF NOT EXISTS likes_id_seq;

CREATE TABLE IF NOT EXISTS hashtags (
    id BIGINT PRIMARY KEY DEFAULT nextval('hashtags_id_seq'),
    tweet_id TEXT NOT NULL,
    hashtag TEXT NOT NULL,
    start_index INTEGER,
    end_index INTEGER,
    FOREIGN KEY (tweet_id) REFERENCES tweets(tweet_id)
);

CREATE INDEX IF NOT EXISTS idx_hashtags_tweet ON hashtags(tweet_id);
CREATE INDEX IF NOT EXISTS idx_hashtags_tag ON hashtags(hashtag);

CREATE TABLE IF NOT EXISTS mentions (
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

CREATE INDEX IF NOT EXISTS idx_mentions_tweet ON mentions(tweet_id);
CREATE INDEX IF NOT EXISTS idx_mentions_user ON mentions(user_id);

CREATE TABLE IF NOT EXISTS urls (
    id BIGINT PRIMARY KEY DEFAULT nextval('urls_id_seq'),
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

CREATE TABLE IF NOT EXISTS media (
    id BIGINT PRIMARY KEY DEFAULT nextval('media_id_seq'),
    tweet_id TEXT NOT NULL,
    media_id TEXT,
    media_url TEXT,
    media_type TEXT,
    file_path TEXT,
    FOREIGN KEY (tweet_id) REFERENCES tweets(tweet_id)
);

CREATE INDEX IF NOT EXISTS idx_media_tweet ON media(tweet_id);
CREATE INDEX IF NOT EXISTS idx_media_type ON media(media_type);

CREATE TABLE IF NOT EXISTS likes (
    id BIGINT PRIMARY KEY DEFAULT nextval('likes_id_seq'),
    tweet_id TEXT NOT NULL,
    full_text TEXT,
    expanded_url TEXT,
    liked_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_likes_tweet ON likes(tweet_id);

CREATE TABLE IF NOT EXISTS followers (
    account_id TEXT PRIMARY KEY,
    user_link TEXT,
    followed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS following (
    account_id TEXT PRIMARY KEY,
    user_link TEXT,
    followed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS account (
    account_id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    account_display_name TEXT,
    email TEXT,
    created_via TEXT,
    created_at TIMESTAMP
);
