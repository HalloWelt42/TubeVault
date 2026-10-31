"""
TubeVault - Blättern ab einem Eintrag (Keyset) statt ab einem Versatz.

Warum: Eine Liste, die seitenweise per OFFSET nachlädt, verliert Einträge,
sobald zwischen zwei Seiten etwas aus der Trefferliste fällt (archiviert, als
Musik markiert, von einer Hintergrundarbeit umgestuft): alles rückt nach vorn,
der Versatz der nächsten Seite springt über genau so viele Einträge hinweg.
Kommt etwas hinzu, erscheinen Einträge doppelt. Der Cursor merkt sich stattdessen
die Sortierwerte des zuletzt gelieferten Eintrags; die nächste Seite beginnt
direkt dahinter, gleich was sich davor verändert hat.

Ein Cursor ist für den Aufrufer undurchsichtig (Base64 aus JSON) und gilt nur für
die Sortierung, mit der er entstand.
"""
import base64
import binascii
import json
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class SortKey:
    """Ein Glied der Sortierung: SQL-Ausdruck, Richtung und Stellung von NULL."""
    expr: str
    desc: bool
    nulls_first: bool

    def order_sql(self) -> str:
        return f"{self.expr} {'DESC' if self.desc else 'ASC'} NULLS {'FIRST' if self.nulls_first else 'LAST'}"


class CursorError(ValueError):
    """Cursor unlesbar oder für eine andere Sortierung ausgestellt."""


def order_by(keys: list[SortKey]) -> str:
    return ", ".join(k.order_sql() for k in keys)


def _strictly_after(key: SortKey, value: Any) -> tuple[str, list]:
    """Bedingung: dieser Schlüssel steht in der Sortierung hinter `value`."""
    if value is None:
        # Hinter NULL kommen nur noch Werte, wenn NULL vorn steht
        return (f"{key.expr} IS NOT NULL", []) if key.nulls_first else ("0", [])
    cmp = "<" if key.desc else ">"
    if key.nulls_first:
        return f"{key.expr} {cmp} ?", [value]
    return f"({key.expr} {cmp} ? OR {key.expr} IS NULL)", [value]


def after_condition(keys: list[SortKey], values: list[Any]) -> tuple[str, list]:
    """WHERE-Teil für "nach dem Eintrag mit diesen Sortierwerten": für jedes Glied
    gilt, alle vorderen sind gleich und dieses steht dahinter."""
    if len(keys) != len(values):
        raise CursorError("Cursor passt nicht zur Sortierung")
    teile, params = [], []
    for i, key in enumerate(keys):
        gleich = [f"{k.expr} IS ?" for k in keys[:i]]
        hinter, hinter_params = _strictly_after(key, values[i])
        teile.append("(" + " AND ".join([*gleich, hinter]) + ")")
        params.extend([*values[:i], *hinter_params])
    return "(" + " OR ".join(teile) + ")", params


def encode(signature: str, values: list[Any]) -> str:
    raw = json.dumps([signature, values], ensure_ascii=False, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def decode(cursor: str, signature: str) -> list[Any]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        sig, values = json.loads(raw.decode("utf-8"))
    except (binascii.Error, ValueError, TypeError, UnicodeDecodeError) as e:
        raise CursorError("Cursor unlesbar") from e
    if sig != signature or not isinstance(values, list):
        raise CursorError("Cursor gehört zu einer anderen Sortierung")
    return values


def next_cursor(signature: str, last_row: Optional[dict], key_columns: list[str], has_more: bool) -> Optional[str]:
    """Cursor hinter der letzten gelieferten Zeile, oder None am Ende der Liste."""
    if not has_more or last_row is None:
        return None
    return encode(signature, [last_row[c] for c in key_columns])
