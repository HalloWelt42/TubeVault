"""
TubeVault - Vektoren für die Bedeutungssuche im Speicher

Die Vektoren der Videos liegen genau im Speicher (semantic_index, auch für
Regeln und Ähnliche). Abschnitte des Gesagten und Feed-Einträge sind dafür
zu viele - gemessen am 15.10.2026 auf dem Pi: 500.000 Vektoren belegen voll
2 GB und kosten 0,5 s je Suche. Für sie und die übrigen Arten (Kanäle,
Playlists, Liedtexte) gilt dieses Verfahren.

Deshalb zweistufig: Im Speicher liegt je Vektor nur sein Binärschlüssel
(Vorzeichen jeder Dimension, 128 Byte statt 4 KB; 500.000 Vektoren = 64 MB).
Die Suche wählt damit die CANDIDATES nächsten Kandidaten (Hamming-Abstand,
55 ms auf dem Pi) und bewertet nur diese genau, mit den Vektoren aus der
Datenbank. Die Schwelle "ragt aus der Masse heraus" (semantic_index.score_floor)
braucht Durchschnitt und Streuung über alle; die schätzt eine feste
Stichprobe von SAMPLE genauen Vektoren.

Die Schlüssel stehen neben dem Vektor in der Datenbank (Spalte code) und
werden über einen eigenen Index gelesen, ohne die Vektoren anzufassen.
"""
from typing import Optional

import numpy as np

# So viele Kandidaten bewertet die zweite Stufe genau: mindestens CANDIDATES,
# bei großen Beständen ein fester Anteil. Gemessen 15.10.2026 an echten
# Vektoren und Anfragen: 2.000 aus 55.000 Abschnitten bzw. 109.000
# Feed-Einträgen fanden 100 % der genauen 80 besten (1.000: 99,4 %).
CANDIDATES = 2_000
CANDIDATE_SHARE = 1 / 200
SAMPLE = 4_096            # Stichprobe für Durchschnitt und Streuung
CODE_BYTES = 128          # 1024 Dimensionen, ein Bit je Dimension


def codes_from_vectors(matrix: np.ndarray) -> np.ndarray:
    """Binärschlüssel vieler Vektoren als uint64-Matrix (Zeilen x 16 bei 1024
    Dimensionen): ein Bit je Dimension (Vorzeichen), auf volle 8 Byte aufgefüllt."""
    packed = np.packbits(np.atleast_2d(matrix) > 0, axis=1)
    padding = -packed.shape[1] % 8
    if padding:
        packed = np.pad(packed, ((0, 0), (0, padding)))
    return np.ascontiguousarray(packed).view(np.uint64)


def binary_code(vector: np.ndarray) -> bytes:
    """Binärschlüssel eines Vektors zum Speichern."""
    return codes_from_vectors(np.asarray(vector)).tobytes()


def codes_from_bytes(blobs: list[bytes]) -> np.ndarray:
    return np.frombuffer(b"".join(blobs), dtype=np.uint64).reshape(len(blobs), -1)


def vectors_from_bytes(blobs: list[bytes]) -> np.ndarray:
    return np.frombuffer(b"".join(blobs), dtype=np.float32).reshape(len(blobs), -1)


class BinaryIndex:
    """Binärschlüssel aller Vektoren einer Art, blockweise erweiterbar."""

    def __init__(self):
        self.refs: list = []
        self.blocks: list[np.ndarray] = []

    def __len__(self) -> int:
        return len(self.refs)

    def append(self, refs: list, codes: np.ndarray) -> None:
        if not refs:
            return
        self.refs.extend(refs)
        self.blocks.append(codes)
        if len(self.blocks) > 32:
            self.blocks = [np.vstack(self.blocks)]

    def candidates(self, query: np.ndarray, count: Optional[int] = None) -> list:
        """Die nächsten Einträge nach Hamming-Abstand (Kennungen); ohne count
        CANDIDATES bzw. der Anteil CANDIDATE_SHARE des Bestands."""
        if not self.refs:
            return []
        count = count or max(CANDIDATES, int(len(self.refs) * CANDIDATE_SHARE))
        code = codes_from_vectors(query)[0]
        distances = np.concatenate([np.bitwise_count(block ^ code).sum(axis=1, dtype=np.uint16)
                                    for block in self.blocks])
        if count < len(distances):
            positions = np.argpartition(distances, count)[:count]
        else:
            positions = np.arange(len(distances))
        return [self.refs[i] for i in positions]


def best(refs: list, vectors: np.ndarray, query: np.ndarray, floor: float, limit: int) -> list[tuple]:
    """(Kennung, Ähnlichkeit) der besten Treffer über der Schwelle, beste zuerst."""
    if not refs:
        return []
    scores = vectors @ query
    order = np.argsort(-scores)[:limit]
    return [(refs[i], float(scores[i])) for i in order if scores[i] >= floor]


def sample_positions(size: int, seed: int = 15) -> np.ndarray:
    """Feste Stichprobe aus size Einträgen (gleich bei gleichem Bestand)."""
    if size <= SAMPLE:
        return np.arange(size)
    return np.sort(np.random.default_rng(seed).choice(size, SAMPLE, replace=False))


def spread(sample: Optional[np.ndarray], query: np.ndarray) -> Optional[tuple[float, float]]:
    """Durchschnitt und Streuung der Ähnlichkeiten, geschätzt an der Stichprobe."""
    if sample is None or not len(sample):
        return None
    scores = sample @ query
    return float(scores.mean()), float(scores.std())
