"""
TubeVault – Schlüssel der Musik

Namen von Interpreten und Alben gelten unabhängig von der Schreibweise als
gleich: Groß- und Kleinschreibung und Leerraum zählen nicht ("ABBA" und
" abba " sind ein Interpret). Hier steht die eine Regel dafür, für
Musikbibliothek, Alben der Sammlung und Namen der Interpreten.
"""
import re

_SPACES = re.compile(r"\s+")


def group_key(name: str) -> str:
    """Schlüssel eines Namens: klein geschrieben, Leerraum einfach, ohne Rand."""
    return _SPACES.sub(" ", name.casefold()).strip()
