"""
Kategorien mit Regeln (Entwurf mockups/kategorien.html, 15.10.2026).

Kontrakt:
- Regeln: "Kanal ist" (Kennung), "Schlagwort enthält" (ohne Groß/Klein, auch
  als Teil, auch Umlaute und \\u-umschriebene Schlagwörter), "Inhaltlich wie"
  (Bedeutung über den Vektorindex). Nur fertige Videos zählen.
- Neue Videos ordnen sich von selbst ein - auch "Inhaltlich wie", ohne die
  KI erneut zu fragen (Vektor und Schwelle der Regel sind gespeichert).
- Von Hand Hinzugefügtes und Herausgenommenes bleibt immer.
- Die Vorschau zählt passend, neu und herausfallend, ohne etwas zu ändern.
- Die Migration v52 erhält Kategorien und Zuordnungen (gelten als von Hand).
- "Themen erkennen" schlägt nur vor; Übernehmen legt Kategorie samt Regel an.
"""
import json

import pytest

from app.models.categories import CategoryCreate, RuleIn, TopicAccept
from app.routers import categories as categories_router
from app.services import (ai_chat, categories, category_rules, category_topics, collections, metadata_service,
                          semantic_index)

AXES = {
    "backen": ("brot", "teig", "sauerteig", "hefe", "backen", "kuchen", "pizza"),
    "elektronik": ("löten", "lötkolben", "platine", "schaltung", "widerstand"),
    "astronomie": ("mond", "stern", "teleskop", "galaxie", "planet"),
}


def _fake_vector(text: str) -> list[float]:
    """Themenachsen plus eine Achse "anderes": Fremdes liegt fern."""
    low = text.lower()
    return [float(sum(low.count(word) for word in words)) for words in AXES.values()] + [0.3]


@pytest.fixture
async def ai(test_db, set_setting, monkeypatch):
    calls = {"n": 0, "up": True}

    async def fake_embed(texts, url, model, timeout):
        if not calls["up"]:
            raise ConnectionError("aus")
        calls["n"] += 1
        return [_fake_vector(t) for t in texts]

    monkeypatch.setattr(semantic_index, "embed_texts", fake_embed)
    semantic_index.reset_availability()
    semantic_index._matrix = None
    semantic_index._query_cache.clear()
    await set_setting("ai.enabled", "true")
    await set_setting("ai.url", "http://ki.test/v1")
    yield calls
    semantic_index.reset_availability()
    semantic_index._matrix = None


async def _video(db, vid, title, channel="UCa", tags=None, status="ready", upload="20240101", raw_tags=None):
    await db.execute(
        """INSERT INTO videos (id, title, channel_id, channel_name, tags, status, upload_date, duration)
           VALUES (?, ?, ?, ?, ?, ?, ?, 600)""",
        (vid, title, channel, f"Kanal {channel}", raw_tags or json.dumps(tags or [], ensure_ascii=False), status, upload))


async def _category(db, name="Test") -> int:
    cursor = await db.execute("INSERT INTO categories (name, color) VALUES (?, '#2196F3')", (name,))
    return cursor.lastrowid


async def _members(db, category_id) -> dict[str, str]:
    rows = await db.fetch_all("SELECT video_id, origin FROM video_categories WHERE category_id = ?", (category_id,))
    return {row["video_id"]: row["origin"] for row in rows}


async def _index_all():
    cfg = await semantic_index.config()
    while await semantic_index.index_batch(*cfg):
        pass
    semantic_index._matrix = None


async def _settle():
    while await category_rules.process_dirty():
        pass


# ─── Regelarten ───────────────────────────────────────────────────────

async def test_kanal_ist_nur_fertige_videos_des_kanals(test_db):
    await _video(test_db, "a1", "Eins", channel="UCa")
    await _video(test_db, "a2", "Zwei", channel="UCa", status="pending")
    await _video(test_db, "b1", "Drei", channel="UCb")
    cid = await _category(test_db)
    result = await category_rules.save_rules(cid, [RuleIn(kind="channel", value="UCa")])
    assert result.added == 1 and await _members(test_db, cid) == {"a1": "rule"}


async def test_neue_videos_des_kanals_kommen_von_selbst(test_db):
    await _video(test_db, "a1", "Eins", channel="UCa")
    cid = await _category(test_db)
    await category_rules.save_rules(cid, [RuleIn(kind="channel", value="UCa")])
    await _video(test_db, "a2", "Neu geladen", channel="UCa", status="pending")
    await test_db.execute("UPDATE videos SET status = 'ready' WHERE id = 'a2'")   # Download fertig
    await _video(test_db, "b1", "Fremd", channel="UCb")
    await _settle()
    assert await _members(test_db, cid) == {"a1": "rule", "a2": "rule"}
    # das neueste Video steht oben in der eigenen Reihenfolge
    items = (await collections.load(f"category:{cid}")).items
    assert [i.id for i in items][0] == "a2"


async def test_schlagwort_ohne_gross_klein_auch_teilwort_und_umlaut(test_db):
    await _video(test_db, "k1", "Live", tags=["Livekonzert", "Rock"])
    await _video(test_db, "k2", "Probe", tags=["KONZERTE"])
    await _video(test_db, "k3", "Anders", tags=["Konzentration"])
    await _video(test_db, "u1", "Übung", raw_tags=json.dumps(["Übungsaufgaben"]))          # \\u-umschrieben
    await _video(test_db, "u2", "Leer", raw_tags="kaputt")
    cid = await _category(test_db, "Konzerte")
    await category_rules.save_rules(cid, [RuleIn(kind="tag", value="konzert")])
    assert set(await _members(test_db, cid)) == {"k1", "k2"}
    other = await _category(test_db, "Übungen")
    await category_rules.save_rules(other, [RuleIn(kind="tag", value="übung")])
    assert set(await _members(test_db, other)) == {"u1"}


async def test_inhaltlich_wie_findet_verwandtes_und_ordnet_neue_ohne_ki_ein(test_db, ai):
    await _video(test_db, "b1", "Sauerteig ansetzen")
    await _video(test_db, "b2", "Pizza aus dem Ofen")
    await _video(test_db, "e1", "Platine löten")
    await _index_all()
    cid = await _category(test_db, "Backen")
    await category_rules.save_rules(cid, [RuleIn(kind="semantic", value="Brot und Kuchen backen")])
    assert set(await _members(test_db, cid)) == {"b1", "b2"}
    rule = await test_db.fetch_one("SELECT precision FROM category_rules WHERE category_id = ?", (cid,))
    assert rule["precision"] == "ausgewogen"      # Standard aus den Einstellungen

    # neues Video bekommt seinen Vektor, die KI ist danach weg: es ordnet sich trotzdem ein
    await _video(test_db, "b3", "Hefeteig für Anfänger")
    await _index_all()
    ai["up"] = False
    semantic_index.reset_availability()
    calls = ai["n"]
    await _settle()
    assert set(await _members(test_db, cid)) == {"b1", "b2", "b3"} and ai["n"] == calls


async def test_inhaltlich_wie_ohne_ki_wird_nicht_gespeichert(test_db, ai, async_client_factory):
    await _video(test_db, "b1", "Sauerteig ansetzen")
    await _index_all()
    cid = await _category(test_db, "Backen")
    ai["up"] = False
    semantic_index.reset_availability()
    preview = await category_rules.preview(cid, [RuleIn(kind="semantic", value="Brot backen")])
    assert preview.semantic_missing and preview.matching == 0
    async with await async_client_factory(categories_router.router) as client:
        r = await client.put(f"/api/categories/{cid}/rules",
                             json={"rules": [{"kind": "semantic", "value": "Brot backen"}]})
    assert r.status_code == 503 and "KI-Dienst" in r.json()["detail"]
    assert not await test_db.fetch_val("SELECT COUNT(*) FROM category_rules")


async def test_gespeichertes_inhaltlich_wie_bleibt_ohne_ki(test_db, ai, set_setting):
    await _video(test_db, "b1", "Sauerteig ansetzen", tags=["brot"])
    await _video(test_db, "e1", "Platine löten", tags=["technik"])
    await _index_all()
    cid = await _category(test_db, "Backen")
    semantic = RuleIn(kind="semantic", value="Brot backen")
    await category_rules.save_rules(cid, [semantic])
    ai["up"] = False
    semantic_index.reset_availability()
    # andere Regel dazu: geht, die gespeicherte bleibt und trifft weiter
    result = await category_rules.save_rules(cid, [semantic, RuleIn(kind="tag", value="technik")])
    assert result.added == 1 and set(await _members(test_db, cid)) == {"b1", "e1"}
    # Bedeutungssuche ganz aus: die Regel bleibt gespeichert, trifft vorerst nichts
    await set_setting("ai.enabled", "false")
    preview = await category_rules.preview(cid, [semantic])
    assert preview.semantic_missing and preview.matching == 0 and preview.leaving == 1   # nur e1 (Schlagwort weg), b1 bleibt
    await category_rules.apply_category(cid)
    assert "b1" in await _members(test_db, cid)
    await category_rules.save_rules(cid, [semantic, RuleIn(kind="tag", value="brot")])
    assert await test_db.fetch_val("SELECT COUNT(*) FROM category_rule_vectors") == 1


async def test_regelvektor_wird_nach_wiederherstellen_nachgerechnet(test_db, ai):
    """Vektoren werden nicht gesichert: fehlt einer, rechnet der Hintergrund ihn nach."""
    await _video(test_db, "b1", "Sauerteig ansetzen")
    await _index_all()
    cid = await _category(test_db, "Backen")
    await category_rules.save_rules(cid, [RuleIn(kind="semantic", value="Brot backen")])
    await test_db.execute("DELETE FROM category_rule_vectors")
    await _video(test_db, "b2", "Hefeteig kneten")
    await _index_all()
    await _settle()
    assert set(await _members(test_db, cid)) == {"b1"}             # ohne Vektor trifft die Regel nichts Neues
    assert await category_rules.refresh_vectors() == 1
    assert set(await _members(test_db, cid)) == {"b1", "b2"}
    assert await category_rules.refresh_vectors() == 0


def test_schwelle_robust_gegen_grosses_thema():
    """Macht ein Thema viel der Sammlung aus, treibt es seine Schwelle nicht hoch."""
    import numpy as np
    rng = np.random.default_rng(1)
    scores = np.concatenate([rng.normal(0.30, 0.03, 700), rng.normal(0.70, 0.03, 300)])   # 30 % passend
    level = semantic_index.PRECISIONS["ausgewogen"]
    floor = semantic_index.rule_floor(scores, level, len(scores))
    assert (scores[700:] >= floor).mean() > 0.95 and (scores[:700] >= floor).mean() < 0.05
    # mit Durchschnitt und Streuung (wie die Suche) fiele das halbe Thema heraus
    assert semantic_index.score_floor(scores, level, len(scores)) > 0.70


# ─── Von Hand hat Vorrang ─────────────────────────────────────────────

async def test_von_hand_hinzugefuegtes_bleibt_ohne_regel(test_db):
    await _video(test_db, "a1", "Eins", channel="UCa")
    await _video(test_db, "h1", "Von Hand", channel="UCb")
    cid = await _category(test_db)
    await category_rules.save_rules(cid, [RuleIn(kind="channel", value="UCa")])
    assert await category_rules.add_by_hand(cid, ["h1", "a1"]) == 1         # a1 war schon drin
    assert await _members(test_db, cid) == {"a1": "hand", "h1": "hand"}       # a1 jetzt von Hand
    await category_rules.save_rules(cid, [])                                 # Regel weg
    assert await _members(test_db, cid) == {"a1": "hand", "h1": "hand"}


async def test_herausgenommenes_bringt_keine_regel_zurueck(test_db):
    await _video(test_db, "a1", "Eins", channel="UCa")
    await _video(test_db, "a2", "Zwei", channel="UCa")
    cid = await _category(test_db)
    await category_rules.save_rules(cid, [RuleIn(kind="channel", value="UCa")])
    removed = await category_rules.remove_by_hand(cid, ["a2"])
    assert [m.video_id for m in removed] == ["a2"] and removed[0].origin == "rule"
    await category_rules.apply_category(cid)
    await test_db.execute("UPDATE videos SET tags = '[\"neu\"]' WHERE id = 'a2'")    # merkt a2 neu vor
    await _settle()
    assert set(await _members(test_db, cid)) == {"a1"}
    # Rückgängig: wieder drin, wieder per Regel
    await category_rules.restore(cid, removed)
    assert await _members(test_db, cid) == {"a1": "rule", "a2": "rule"}
    # erneutes Hineinlegen von Hand hebt ein Herausnehmen auf
    await category_rules.remove_by_hand(cid, ["a1"])
    await category_rules.add_by_hand(cid, ["a1"])
    assert (await _members(test_db, cid))["a1"] == "hand"
    assert not await test_db.fetch_val("SELECT COUNT(*) FROM category_exclusions")


async def test_bearbeiten_in_der_wiedergabe_gilt_als_von_hand(test_db):
    await _video(test_db, "a1", "Eins", channel="UCa")
    rule_cat = await _category(test_db, "Per Regel")
    hand_cat = await _category(test_db, "Von Hand")
    await category_rules.save_rules(rule_cat, [RuleIn(kind="channel", value="UCa")])
    await metadata_service.metadata_service.update_video("a1", {"category_ids": [hand_cat]})
    assert await _members(test_db, hand_cat) == {"a1": "hand"}
    assert await _members(test_db, rule_cat) == {}
    await category_rules.apply_category(rule_cat)              # abgewählt bleibt draußen
    assert await _members(test_db, rule_cat) == {}


# ─── Vorschau ─────────────────────────────────────────────────────────

async def test_vorschau_zaehlt_ohne_zu_aendern(test_db):
    for vid, channel, tags in [("a1", "UCa", []), ("a2", "UCa", ["konzert"]), ("a3", "UCa", []),
                               ("b1", "UCb", ["Konzert"]), ("b2", "UCb", [])]:
        await _video(test_db, vid, vid, channel=channel, tags=tags)
    cid = await _category(test_db)
    await category_rules.save_rules(cid, [RuleIn(kind="channel", value="UCa")])
    await category_rules.remove_by_hand(cid, ["a3"])            # a3 bleibt draußen
    preview = await category_rules.preview(cid, [RuleIn(kind="tag", value="konzert")])
    # passend: a2, b1 - neu davon: b1 - heraus fiele: a1 (a2 bleibt, a3 ist ausgeschlossen)
    assert (preview.matching, preview.new, preview.leaving, preview.per_rule) == (2, 1, 1, [2])
    assert [s.id for s in preview.samples] == ["b1"]
    assert set(await _members(test_db, cid)) == {"a1", "a2"}    # nichts geändert
    both = await category_rules.preview(cid, [RuleIn(kind="channel", value="UCa"), RuleIn(kind="tag", value="konzert")])
    assert (both.matching, both.new, both.leaving, both.per_rule) == (3, 1, 0, [2, 2])


async def test_vorschau_neuer_kategorie_und_ungueltige_regeln(test_db, async_client_factory):
    await _video(test_db, "a1", "Eins", channel="UCa")
    async with await async_client_factory(categories_router.router) as client:
        r = await client.post("/api/categories/preview", json={"rules": [{"kind": "channel", "value": "UCa"}]})
        assert r.json()["matching"] == 1 and r.json()["new"] == 1
        r = await client.post("/api/categories/preview", json={"rules": [{"kind": "channel", "value": "UCgibtsnicht"}]})
        assert r.status_code == 400 and "Kanal" in r.json()["detail"]
        r = await client.post("/api/categories/preview", json={"rules": [{"kind": "tag", "value": "   "}]})
        assert r.status_code == 422


# ─── Übersicht, Anlegen, Löschen, Sammlung ────────────────────────────

async def test_uebersicht_anlegen_und_loeschen(test_db, async_client_factory):
    await _video(test_db, "a1", "Eins", channel="UCa")
    await _video(test_db, "a2", "Zwei", channel="UCa")
    await _video(test_db, "b1", "Drei", channel="UCb")
    async with await async_client_factory(categories_router.router) as client:
        r = await client.post("/api/categories", json={"name": " Kanal A ", "rules": [{"kind": "channel", "value": "UCa"}]})
        cid = r.json()["id"]
        assert (await client.post("/api/categories", json={"name": "kanal a"})).status_code == 409
        data = (await client.get("/api/categories/overview")).json()
        card = data["categories"][0]
        assert (data["total"], data["assigned"], data["unassigned"]) == (3, 2, 1)
        assert card["name"] == "Kanal A" and card["video_count"] == 2 and card["color"] == data["colors"][0]
        assert card["rules"][0]["label"] == "Kanal UCa" and len(card["cover_ids"]) == 2
        assert data["unsorted_channels"] == [{"channel_id": "UCb", "name": "Kanal UCb", "count": 1}]
        assert data["ai"]["semantic"] is False and data["ai"]["topics"] is False
        assert (await client.put(f"/api/categories/{cid}", json={"color": "#123456"})).status_code == 400
        assert (await client.delete(f"/api/categories/{cid}")).json() == {"deleted": True}
    assert not await test_db.fetch_val("SELECT COUNT(*) FROM category_rules")
    assert not await test_db.fetch_val("SELECT COUNT(*) FROM video_categories")
    assert await test_db.fetch_val("SELECT COUNT(*) FROM videos") == 3


async def test_kategorie_als_sammlung_mit_grund(test_db):
    await _video(test_db, "a1", "Kanal", channel="UCa", upload="20240101")
    await _video(test_db, "t1", "Schlagwort", channel="UCb", tags=["konzert"], upload="20240301")
    await _video(test_db, "h1", "Hand", channel="UCc", upload="20240201")
    cid = await categories.create(CategoryCreate(name="Mix", rules=[RuleIn(kind="channel", value="UCa"),
                                                                     RuleIn(kind="tag", value="konzert")]))
    await category_rules.add_by_hand(cid, ["h1"])
    collection = await collections.load(f"category:{cid}")
    assert collection.kind == "category" and collection.title == "Mix"
    assert [(i.id, i.reason) for i in collection.items] == [("h1", "hand"), ("t1", "tag"), ("a1", "channel")]
    await category_rules.reorder(cid, ["a1", "h1", "t1"])
    assert [i.id for i in (await collections.load(f"category:{cid}")).items] == ["a1", "h1", "t1"]
    with pytest.raises(LookupError):
        await collections.load("category:999")


# ─── Migration ────────────────────────────────────────────────────────

async def test_migration_erhaelt_kategorien_und_zuordnungen(tmp_path):
    """Eine Datenbank mit Stand v51 (Zuordnung nur Video und Kategorie)."""
    from app.database import Database
    path = tmp_path / "alt.db"
    old = Database(db_path=path)
    await old.connect()
    await old.conn.executescript("""
        DROP TRIGGER IF EXISTS trg_category_dirty_insert; DROP TRIGGER IF EXISTS trg_category_dirty_update;
        DROP TRIGGER IF EXISTS trg_category_dirty_vector; DROP TRIGGER IF EXISTS trg_category_dirty_vector_update;
        DROP TRIGGER IF EXISTS trg_category_dirty_delete;
        DROP TABLE category_dirty; DROP TABLE category_rule_vectors; DROP TABLE category_exclusions;
        DROP TABLE category_rules; DROP TABLE category_suggestions;
        DROP INDEX IF EXISTS idx_video_categories_order; DROP TABLE video_categories;
        CREATE TABLE video_categories (
            video_id TEXT NOT NULL, category_id INTEGER NOT NULL, PRIMARY KEY (video_id, category_id),
            FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE,
            FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE);
        DELETE FROM schema_version; INSERT INTO schema_version (version) VALUES (51);
        INSERT INTO videos (id, title, status, upload_date) VALUES ('alt', 'Alt', 'ready', '20200101'),
            ('neu', 'Neu', 'ready', '20240101'), ('mitte', 'Mitte', 'ready', '20220101');
        INSERT INTO categories (id, name, color) VALUES (7, 'Lieblinge', '#E91E63'), (8, 'Leer', '#607D8B');
        INSERT INTO video_categories (video_id, category_id) VALUES ('alt', 7), ('neu', 7), ('mitte', 7);
    """)
    await old.conn.commit()
    await old.disconnect()

    migrated = Database(db_path=path)
    await migrated.connect()
    try:
        assert await migrated.fetch_val("SELECT MAX(version) FROM schema_version") == 52
        assert [r["name"] for r in await migrated.fetch_all("SELECT name FROM categories ORDER BY id")] == ["Lieblinge", "Leer"]
        rows = await migrated.fetch_all(
            "SELECT video_id, origin, rule_id FROM video_categories WHERE category_id = 7 ORDER BY position")
        assert [(r["video_id"], r["origin"], r["rule_id"]) for r in rows] == [
            ("neu", "hand", None), ("mitte", "hand", None), ("alt", "hand", None)]
        for table in ("category_rules", "category_exclusions", "category_rule_vectors", "category_dirty",
                      "category_suggestions"):
            assert await migrated.fetch_val(f"SELECT COUNT(*) FROM {table}") == 0
    finally:
        await migrated.disconnect()
    # ein zweiter Start ändert nichts mehr
    again = Database(db_path=path)
    await again.connect()
    try:
        assert await again.fetch_val("SELECT COUNT(*) FROM video_categories") == 3
    finally:
        await again.disconnect()


# ─── Themen erkennen ──────────────────────────────────────────────────

def test_antwort_der_ki_wird_gesaeubert():
    answer = {"gruppen": [
        {"nummer": 1, "erkennbar": True, "name": "\u201eBacken\u201c", "beschreibung": "Backen \u2013 Brot, Kuchen\u2026"},
        {"nummer": 2, "erkennbar": True, "name": "backen", "beschreibung": "doppelt"},
        {"nummer": 3, "erkennbar": False, "name": "Gemisch", "beschreibung": "x"},
        {"nummer": 9, "erkennbar": True, "name": "Gibts nicht", "beschreibung": "y"},
        {"nummer": 4, "erkennbar": True, "name": "Schleife", "beschreibung": "entwicklungentwicklungentwicklungentwicklung"},
    ]}
    assert category_topics.read_answer(answer, 4) == [("Backen", "Backen - Brot, Kuchen...")]


def test_gruppieren_trennt_themen():
    import numpy as np
    rng = np.random.default_rng(3)
    blobs = [np.array(axis, dtype=np.float32) for axis in ([1, 0, 0], [0, 1, 0], [0, 0, 1])]
    rows = np.vstack([b + rng.normal(0, 0.05, (30, 3)) for b in blobs]).astype(np.float32)
    rows /= np.linalg.norm(rows, axis=1, keepdims=True)
    labels, centers = category_topics.cluster(rows, 3)
    assert len(centers) == 3 and all(len(set(labels[i * 30:(i + 1) * 30])) == 1 for i in range(3))
    assert len(set(labels)) == 3
    assert category_topics.group_count(194) == 4 and category_topics.group_count(32000) == 12


async def test_themen_erkennen_schlaegt_vor_und_uebernimmt(test_db, ai, monkeypatch):
    titles = {"b": ["Sauerteig ansetzen", "Pizza backen", "Hefeteig kneten", "Brot backen", "Kuchen backen"],
              "e": ["Platine löten", "Lötkolben kaufen", "Schaltung bauen", "Widerstand messen", "Löten lernen"],
              "s": ["Mond beobachten", "Teleskop kaufen", "Galaxie Andromeda", "Planet Saturn", "Stern Sirius"]}
    for key, names in titles.items():
        for round_ in range(3):
            for n, title in enumerate(names):
                await _video(test_db, f"{key}{round_}{n}", f"{title} {round_}", channel=f"UC{key}")
    await _index_all()
    monkeypatch.setattr(category_topics, "MIN_VIDEOS", 10)

    async def fake_model():
        return "sprachmodell"

    async def fake_answer(system, user, name, schema, timeout=0):
        assert "echten Umlauten" in system and "Gruppe 1" in user
        names = {"Sauerteig": ("Backen", "Backen: Brot, Kuchen, Teig"), "Platine": ("Elektronik", "Elektronik: löten, Platine"),
                 "Mond": ("Astronomie", "Astronomie: Stern, Planet, Teleskop")}
        groups = user.split("Gruppe ")[1:]
        result = []
        for number, block in enumerate(groups, start=1):
            topic = next((v for k, v in names.items() if any(k.lower() in line.lower() for line in block.splitlines())),
                         ("Gemisch", "x"))
            result.append({"nummer": number, "erkennbar": topic[0] != "Gemisch", "name": topic[0], "beschreibung": topic[1]})
        return {"gruppen": result}

    monkeypatch.setattr(ai_chat, "pick_model", fake_model)
    monkeypatch.setattr(ai_chat, "complete_json", fake_answer)
    assert category_topics.start() is True
    await category_topics._task
    state = await category_topics.state()
    assert state.error is None and not state.running
    found = {s.name: s for s in state.suggestions}
    assert set(found) == {"Backen", "Elektronik", "Astronomie"}
    assert found["Backen"].match_count == 15 and found["Backen"].channels == ["Kanal UCb"]
    assert not await test_db.fetch_val("SELECT COUNT(*) FROM categories")      # nur Vorschläge

    cid = await category_topics.accept(found["Backen"].id, TopicAccept())
    assert len(await _members(test_db, cid)) == 15
    rule = await test_db.fetch_one("SELECT kind, value FROM category_rules WHERE category_id = ?", (cid,))
    assert (rule["kind"], rule["value"]) == ("semantic", "Backen: Brot, Kuchen, Teig")
    await category_topics.dismiss(found["Elektronik"].id)
    assert [s.name for s in await category_topics.suggestions()] == ["Astronomie"]


async def test_themen_ohne_sprachmodell(test_db, ai, monkeypatch):
    for n in range(25):
        await _video(test_db, f"v{n}", f"Brot backen {n}")
    await _index_all()

    async def no_model():
        return None
    monkeypatch.setattr(ai_chat, "pick_model", no_model)
    category_topics.start()
    await category_topics._task
    state = await category_topics.state()
    assert state.error == "Kein Sprachmodell geladen" and state.suggestions == []


def test_ki_prosa_auf_gerade_zeichen():
    text = "\u201eMusik\u201c \u2013 live\u00a0und \u201alaut\u2018 \u2026 "
    assert ai_chat.plain(text) == "\"Musik\" - live und 'laut' ..."
