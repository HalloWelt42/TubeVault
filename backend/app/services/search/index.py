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

Schlagwörter des Feeds stehen als JSON-Liste mit \\u-Umschreibung in
rss_entries.keywords; in den Volltext kommen sie entschlüsselt als Klartext
(keywords_text). Bis v60 stand dort das rohe JSON: keywords:Militär fand am
Bestand 93 Einträge, 742 tragen ein Schlagwort mit "militär". v61 schreibt
die betroffenen Einträge neu (reindex_feed_keywords).
"""


def keywords_text(ref: str) -> str:
    """SQL-Ausdruck: Schlagwörter (JSON-Liste in ref) als Klartext, durch
    Leerzeichen getrennt; kein JSON-Feld: der Text, wie er ist."""
    return (f"CASE WHEN json_valid({ref}) AND json_type({ref}) = 'array' "
            f"THEN COALESCE((SELECT group_concat(value, ' ') FROM json_each({ref})), '') "
            f"ELSE COALESCE({ref}, '') END")


SCHEMA_SQL = f"""
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
            COALESCE(new.description, ''), {keywords_text('new.keywords')});
END;
CREATE TRIGGER IF NOT EXISTS trg_feed_fts_update
AFTER UPDATE OF title, description, keywords, channel_id ON rss_entries
BEGIN
    DELETE FROM feed_fts WHERE rowid = old.id;
    INSERT INTO feed_fts (rowid, title, channel_name, description, keywords)
    VALUES (new.id, COALESCE(new.title, ''),
            COALESCE((SELECT channel_name FROM subscriptions WHERE channel_id = new.channel_id), ''),
            COALESCE(new.description, ''), {keywords_text('new.keywords')});
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
    SELECT id, COALESCE(title, ''), COALESCE(new.channel_name, ''), COALESCE(description, ''), {keywords_text('keywords')}
    FROM rss_entries WHERE channel_id = new.channel_id;
END;
"""

_FILL_FEED = f"""
INSERT INTO feed_fts (rowid, title, channel_name, description, keywords)
SELECT r.id, COALESCE(r.title, ''), COALESCE(s.channel_name, ''), COALESCE(r.description, ''), {keywords_text('r.keywords')}
FROM rss_entries r LEFT JOIN subscriptions s ON s.channel_id = r.channel_id
"""
_FEED_TRIGGERS = ("trg_feed_fts_insert", "trg_feed_fts_update", "trg_feed_fts_delete", "trg_feed_fts_channel")


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


async def reindex_feed_keywords(connection) -> int:
    """v61: Trigger dieser Fassung anlegen und die Feed-Einträge neu schreiben,
    deren Schlagwörter mit Umschreibung (Rückstrich) im JSON stehen - nur bei
    ihnen zerlegt der Tokenizer das rohe JSON anders als den Klartext (am
    Bestand 4.075 von 157.137; alles neu zu bauen dauerte am Mac 8 s, auf dem
    Pi rund dreimal so lang). Gibt die Zahl der neu geschriebenen zurück."""
    for trigger in _FEED_TRIGGERS:
        await connection.execute(f"DROP TRIGGER IF EXISTS {trigger}")
    await connection.executescript(SCHEMA_SQL)
    escaped = "instr(r.keywords, char(92)) > 0"
    await connection.execute(f"DELETE FROM feed_fts WHERE rowid IN (SELECT r.id FROM rss_entries r WHERE {escaped})")
    cursor = await connection.execute(f"{_FILL_FEED} WHERE {escaped}")
    await connection.commit()
    return cursor.rowcount


async def after_vacuum(connection) -> None:
    """Nach VACUUM: Indexe über Tabellen ohne feste Zeilennummer neu aufbauen."""
    await connection.execute("INSERT INTO music_fts (music_fts) VALUES ('rebuild')")
    await connection.commit()
