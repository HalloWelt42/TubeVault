"""
TubeVault – Schlagwörter im Feed (eigener Index)

Der Schlagwort-Index (tag_index) für rss_entries.keywords: je Feed-Eintrag
und Schlagwort eine Zeile in feed_keywords mit Suchschlüssel tag_suche.
Derselbe Fehler wie bei den Videos (Wunsch 19.10.2026): der Feed filterte mit
keywords LIKE '%"<wort>"%' im JSON mit \\u-Umschreibung - "Militär",
"Streitkräfte" oder kyrillische Schlagwörter fanden nichts. Regel, Pflege und
Abfragen stehen in tag_index.

Pflege: Trigger auf rss_entries merken jeden neuen Eintrag mit Schlagwörtern
und jede Änderung an keywords vor (Kanal-Scan, RSS, Bereinigung); gelöschte
Einträge nehmen ihre Zeilen mit (Fremdschlüssel). Den Bestand nach der
Einführung (Migration v60) nimmt background_catch_up in Portionen auf.

Nutzer: Schlagwortfilter des Feeds (rss_service.get_new_videos) und die
Schlagwortliste des Feeds (feed_router /feed/tags).
"""
from app.services.tag_index import TagIndex

INDEX = TagIndex(table="feed_keywords", id_column="entry_id", id_type="INTEGER", owner="rss_entries",
                 column="keywords")
