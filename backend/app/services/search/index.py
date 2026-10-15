"""
Volltext über Kapitel und Feed-Einträge.

  chapters_fts   Kapiteltitel (Inhalt liegt in chapters), Trigger halten ihn aktuell
  feed_fts       Titel, Kanal, Beschreibung und Schlagwörter der Feed-Einträge;
                 ohne eigenen Inhalt (rowid = rss_entries.id), weil der Kanalname
                 aus subscriptions kommt
  music_fts      Titel, Künstler, Album, Genre und Liedtext der eigenen
                 Musiksammlung (Inhalt liegt in music_files). music_files hat
                 keine feste Zeilennummer (Schlüssel ist Text): VACUUM kann sie
                 neu vergeben, danach baut after_vacuum diesen Index neu.

Gleicher Tokenizer wie der Videoindex (search_index), damit ein Wort überall
gleich trifft. Die Videos selbst pflegt search_index, das Gesagte transcripts.
"""
SCHEMA_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS chapters_fts USING fts5(
    title, content='chapters', content_rowid='id',
    tokenize='unicode61 remove_diacritics 2', prefix='2 3 4'
);
CREATE TRIGGER IF NOT EXISTS trg_chapters_fts_insert AFTER INSERT ON chapters
BEGIN
    INSERT INTO chapters_fts (rowid, title) VALUES (new.id, new.title);
END;
CREATE TRIGGER IF NOT EXISTS trg_chapters_fts_delete AFTER DELETE ON chapters
BEGIN
    INSERT INTO chapters_fts (chapters_fts, rowid, title) VALUES ('delete', old.id, old.title);
END;
CREATE TRIGGER IF NOT EXISTS trg_chapters_fts_update AFTER UPDATE OF title ON chapters
BEGIN
    INSERT INTO chapters_fts (chapters_fts, rowid, title) VALUES ('delete', old.id, old.title);
    INSERT INTO chapters_fts (rowid, title) VALUES (new.id, new.title);
END;

CREATE VIRTUAL TABLE IF NOT EXISTS feed_fts USING fts5(
    title, channel_name, description, keywords,
    content='', contentless_delete=1,
    tokenize='unicode61 remove_diacritics 2', prefix='2 3 4'
);
CREATE TRIGGER IF NOT EXISTS trg_feed_fts_insert AFTER INSERT ON rss_entries
BEGIN
    INSERT INTO feed_fts (rowid, title, channel_name, description, keywords)
    VALUES (new.id, COALESCE(new.title, ''),
            COALESCE((SELECT channel_name FROM subscriptions WHERE channel_id = new.channel_id), ''),
            COALESCE(new.description, ''), COALESCE(new.keywords, ''));
END;
CREATE TRIGGER IF NOT EXISTS trg_feed_fts_update
AFTER UPDATE OF title, description, keywords, channel_id ON rss_entries
BEGIN
    DELETE FROM feed_fts WHERE rowid = old.id;
    INSERT INTO feed_fts (rowid, title, channel_name, description, keywords)
    VALUES (new.id, COALESCE(new.title, ''),
            COALESCE((SELECT channel_name FROM subscriptions WHERE channel_id = new.channel_id), ''),
            COALESCE(new.description, ''), COALESCE(new.keywords, ''));
END;
CREATE TRIGGER IF NOT EXISTS trg_feed_fts_delete AFTER DELETE ON rss_entries
BEGIN
    DELETE FROM feed_fts WHERE rowid = old.id;
END;
CREATE VIRTUAL TABLE IF NOT EXISTS music_fts USING fts5(
    title, artist, album_artist, album, genre, lyrics_text,
    content='music_files', content_rowid='rowid',
    tokenize='unicode61 remove_diacritics 2', prefix='2 3 4'
);
CREATE TRIGGER IF NOT EXISTS trg_music_fts_insert AFTER INSERT ON music_files
BEGIN
    INSERT INTO music_fts (rowid, title, artist, album_artist, album, genre, lyrics_text)
    VALUES (new.rowid, new.title, new.artist, new.album_artist, new.album, new.genre, new.lyrics_text);
END;
CREATE TRIGGER IF NOT EXISTS trg_music_fts_delete AFTER DELETE ON music_files
BEGIN
    INSERT INTO music_fts (music_fts, rowid, title, artist, album_artist, album, genre, lyrics_text)
    VALUES ('delete', old.rowid, old.title, old.artist, old.album_artist, old.album, old.genre, old.lyrics_text);
END;
CREATE TRIGGER IF NOT EXISTS trg_music_fts_update
AFTER UPDATE OF title, artist, album_artist, album, genre, lyrics_text ON music_files
BEGIN
    INSERT INTO music_fts (music_fts, rowid, title, artist, album_artist, album, genre, lyrics_text)
    VALUES ('delete', old.rowid, old.title, old.artist, old.album_artist, old.album, old.genre, old.lyrics_text);
    INSERT INTO music_fts (rowid, title, artist, album_artist, album, genre, lyrics_text)
    VALUES (new.rowid, new.title, new.artist, new.album_artist, new.album, new.genre, new.lyrics_text);
END;
CREATE TRIGGER IF NOT EXISTS trg_feed_fts_channel AFTER UPDATE OF channel_name ON subscriptions
BEGIN
    DELETE FROM feed_fts WHERE rowid IN (SELECT id FROM rss_entries WHERE channel_id = new.channel_id);
    INSERT INTO feed_fts (rowid, title, channel_name, description, keywords)
    SELECT id, COALESCE(title, ''), COALESCE(new.channel_name, ''), COALESCE(description, ''), COALESCE(keywords, '')
    FROM rss_entries WHERE channel_id = new.channel_id;
END;
"""

_FILL_FEED = """
INSERT INTO feed_fts (rowid, title, channel_name, description, keywords)
SELECT r.id, COALESCE(r.title, ''), COALESCE(s.channel_name, ''), COALESCE(r.description, ''), COALESCE(r.keywords, '')
FROM rss_entries r LEFT JOIN subscriptions s ON s.channel_id = r.channel_id
"""


async def install_schema(connection, *, build: bool) -> None:
    """Tabellen und Trigger anlegen; build=True füllt die Indexe aus dem Bestand."""
    if build:
        for table in ("chapters_fts", "feed_fts", "music_fts"):
            await connection.execute(f"DROP TABLE IF EXISTS {table}")
    await connection.executescript(SCHEMA_SQL)
    if build:
        await connection.execute("INSERT INTO chapters_fts (chapters_fts) VALUES ('rebuild')")
        await connection.execute("INSERT INTO music_fts (music_fts) VALUES ('rebuild')")
        await connection.execute(_FILL_FEED)
    await connection.commit()


async def after_vacuum(connection) -> None:
    """Nach VACUUM: Indexe über Tabellen ohne feste Zeilennummer neu aufbauen."""
    await connection.execute("INSERT INTO music_fts (music_fts) VALUES ('rebuild')")
    await connection.commit()
