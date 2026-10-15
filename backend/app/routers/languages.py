"""
TubeVault - Sprachen (Katalog für Labels und Filter)

Namen, Flaggen und Herkünfte kommen aus language.py; die Oberfläche lädt sie
einmal und zeigt damit jede Sprachangabe gleich an.
"""
from fastapi import APIRouter

from app.models.language import LanguageCatalog
from app.services import language

router = APIRouter(prefix="/api/languages", tags=["Sprache"])


@router.get("", response_model=LanguageCatalog)
async def get_language_catalog() -> LanguageCatalog:
    return language.catalog()
