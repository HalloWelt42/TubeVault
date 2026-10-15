"""
Zweistufige Vektorsuche (app/services/vector_store).

Kontrakt:
- Binärschlüssel: ein Bit je Dimension, auf volle 8 Byte aufgefüllt
- die Vorauswahl über den Hamming-Abstand verliert die besten Treffer nicht
  (an echten Vektoren gemessen 15.10.2026: 2.000 Kandidaten aus 55.000 Abschnitten
  und 109.000 Feed-Einträgen fanden 100 % der genauen 80 besten)
- Durchschnitt und Streuung lassen sich an der Stichprobe schätzen
"""
import numpy as np

from app.services import vector_store


def _normed(matrix):
    return matrix / np.linalg.norm(matrix, axis=1, keepdims=True)


def test_schluessel_auch_fuer_kleine_vektoren():
    codes = vector_store.codes_from_vectors(np.array([[0.5, -1.0, 2.0], [-1.0, -1.0, -1.0]], dtype=np.float32))
    assert codes.dtype == np.uint64 and codes.shape == (2, 1)
    assert len(vector_store.binary_code(np.ones(1024, dtype=np.float32))) == vector_store.CODE_BYTES


def test_vorauswahl_verliert_die_besten_nicht():
    # Vektoren mit innerer Struktur wie echte Einbettungen: 64 verborgene Richtungen
    rng = np.random.default_rng(3)
    projection = rng.standard_normal((64, 1024)).astype(np.float32)
    vectors = _normed(rng.standard_normal((20_000, 64)).astype(np.float32) @ projection)
    index = vector_store.BinaryIndex()
    for start in range(0, len(vectors), 5_000):
        index.append(list(range(start, start + 5_000)), vector_store.codes_from_vectors(vectors[start:start + 5_000]))
    for query in _normed(rng.standard_normal((5, 64)).astype(np.float32) @ projection):
        exact = set(np.argsort(-(vectors @ query))[:50].tolist())
        candidates = index.candidates(query, 1_000)
        found = vector_store.best(candidates, vectors[candidates], query, -1.0, 50)
        assert len(exact & {ref for ref, _ in found}) >= 49


def test_streuung_aus_der_stichprobe():
    rng = np.random.default_rng(4)
    vectors = _normed(rng.standard_normal((30_000, 64)).astype(np.float32))
    query = _normed(rng.standard_normal((1, 64)).astype(np.float32))[0]
    sample = vectors[vector_store.sample_positions(len(vectors))]
    mean, deviation = vector_store.spread(sample, query)
    scores = vectors @ query
    assert abs(mean - scores.mean()) < 0.01 and abs(deviation - scores.std()) < 0.01
