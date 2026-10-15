"""
TubeVault - Kategorien

Übersicht, Anlegen und Ändern, Regeln samt Vorschau, von Hand hinein und
heraus, eigene Reihenfolge und "Themen erkennen". Die Videos einer
Kategorie liest die Seite als Sammlung (collections, Quelle category:<id>).
Entschieden wird in den Diensten categories, category_rules und
category_topics - hier nur Ein- und Ausgang.
"""
from fastapi import APIRouter, HTTPException, Query

from app.models.categories import (
    ApplyResult, CategoryBrief, CategoryCreate, CategoryOverview, CategoryUpdate, ChannelChoice, Membership,
    PreviewRequest, RestoreRequest, RulePreview, RulesUpdate, TopicAccept, TopicState, VideoIds,
)
from app.services import categories, category_rules, category_topics

router = APIRouter(prefix="/api/categories", tags=["Kategorien"])


async def _known(category_id: int) -> None:
    if not await categories.exists(category_id):
        raise HTTPException(status_code=404, detail="Kategorie nicht gefunden")


def _bad_request(e: Exception) -> HTTPException:
    if isinstance(e, categories.CategoryExists):
        return HTTPException(status_code=409, detail=str(e))
    if isinstance(e, category_rules.RulesUnavailable):
        return HTTPException(status_code=503, detail=str(e))
    return HTTPException(status_code=400, detail=str(e))


# ─── Lesen ────────────────────────────────────────────────────────────

@router.get("", response_model=list[CategoryBrief])
async def list_categories():
    """Alle Kategorien kurz (Auswahl in Wiedergabe und Filtern)."""
    return await categories.briefs()


@router.get("/flat", response_model=list[CategoryBrief])
async def list_categories_flat():
    """Wie GET /api/categories (älterer Name, von Filtern genutzt)."""
    return await categories.briefs()


@router.get("/overview", response_model=CategoryOverview)
async def overview():
    """Kennzahlen, Kacheln mit Regeln und die Kanäle mit den meisten Videos ohne Kategorie."""
    return await categories.overview()


@router.get("/channels", response_model=list[ChannelChoice])
async def channel_choices(q: str = Query("", max_length=100)):
    """Kanäle für die Regel "Kanal ist" (Name enthält q)."""
    return await categories.channel_choices(q)


# ─── Themen erkennen (vor /{category_id}) ─────────────────────────────

@router.get("/topics", response_model=TopicState)
async def topics_state():
    """Stand des Laufs und die gespeicherten Vorschläge."""
    return await category_topics.state()


@router.post("/topics", response_model=TopicState)
async def start_topics():
    """Themen erkennen starten (läuft im Hintergrund)."""
    category_topics.start()
    return await category_topics.state()


@router.post("/topics/{suggestion_id}/accept")
async def accept_topic(suggestion_id: int, changes: TopicAccept = TopicAccept()):
    """Vorschlag übernehmen: Kategorie samt Regel anlegen und füllen."""
    try:
        return {"id": await category_topics.accept(suggestion_id, changes)}
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (ValueError, categories.CategoryExists, category_rules.RulesUnavailable) as e:
        raise _bad_request(e)


@router.delete("/topics/{suggestion_id}")
async def dismiss_topic(suggestion_id: int):
    await category_topics.dismiss(suggestion_id)
    return {"dismissed": True}


@router.post("/preview", response_model=RulePreview)
async def preview(request: PreviewRequest):
    """Was Regeln ergäben (passend, neu, fallen heraus), ohne etwas zu ändern."""
    if request.category_id is not None:
        await _known(request.category_id)
    try:
        return await category_rules.preview(request.category_id, request.rules)
    except ValueError as e:
        raise _bad_request(e)


# ─── Video in Kategorien (Wiedergabe, Bearbeiten) ─────────────────────

@router.get("/videos/{video_id}", response_model=list[CategoryBrief])
async def video_categories(video_id: str):
    return await categories.video_categories(video_id)


@router.post("/videos/{video_id}")
async def set_video_categories(video_id: str, category_ids: list[int]):
    """Kategorien eines Videos von Hand festlegen (Abgewähltes gilt als herausgenommen)."""
    await category_rules.set_video_categories(video_id, category_ids)
    return {"video_id": video_id, "categories": [c.id for c in await categories.video_categories(video_id)]}


# ─── Eine Kategorie ───────────────────────────────────────────────────

@router.post("")
async def create_category(data: CategoryCreate):
    """Neue Kategorie, wahlweise gleich mit Regeln (füllt sich sofort)."""
    try:
        return {"id": await categories.create(data)}
    except (ValueError, categories.CategoryExists, category_rules.RulesUnavailable) as e:
        raise _bad_request(e)


@router.put("/{category_id}")
async def update_category(category_id: int, data: CategoryUpdate):
    """Name, Beschreibung oder Farbe ändern."""
    await _known(category_id)
    try:
        await categories.update(category_id, data)
    except (ValueError, categories.CategoryExists) as e:
        raise _bad_request(e)
    return {"id": category_id, "updated": True}


@router.delete("/{category_id}")
async def delete_category(category_id: int):
    """Kategorie mit Regeln löschen; die Videos bleiben in der Bibliothek."""
    await _known(category_id)
    await categories.delete(category_id)
    return {"deleted": True}


@router.put("/{category_id}/rules", response_model=ApplyResult)
async def save_rules(category_id: int, data: RulesUpdate):
    """Regeln speichern und die Kategorie danach neu füllen."""
    await _known(category_id)
    try:
        return await category_rules.save_rules(category_id, data.rules)
    except (ValueError, category_rules.RulesUnavailable) as e:
        raise _bad_request(e)


@router.post("/{category_id}/videos")
async def add_videos(category_id: int, data: VideoIds):
    """Videos von Hand hineinlegen."""
    await _known(category_id)
    return {"added": await category_rules.add_by_hand(category_id, data.video_ids)}


@router.post("/{category_id}/videos/remove", response_model=list[Membership])
async def remove_videos(category_id: int, data: VideoIds):
    """Videos herausnehmen; keine Regel bringt sie zurück. Antwort: die
    entfernten Einträge (für Rückgängig)."""
    await _known(category_id)
    return await category_rules.remove_by_hand(category_id, data.video_ids)


@router.post("/{category_id}/videos/restore")
async def restore_videos(category_id: int, data: RestoreRequest):
    """Herausnehmen rückgängig machen."""
    await _known(category_id)
    return {"restored": await category_rules.restore(category_id, data.entries)}


@router.put("/{category_id}/order")
async def reorder(category_id: int, data: VideoIds):
    """Eigene Reihenfolge (alle Videos der Kategorie, von oben)."""
    await _known(category_id)
    await category_rules.reorder(category_id, data.video_ids)
    return {"ok": True}
