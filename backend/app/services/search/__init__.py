"""
TubeVault - Suche

Eine Suche über alles, was TubeVault kennt. Aufbau:

  query       Suchtext verstehen: Wörter, "Wortfolgen", -Ausschlüsse, oder,
              Angaben wie kanal:, sprache:, länge:, jahr:, in:
  text        Wörter vergleichen und Textausschnitte um eine Fundstelle
  filters     Filter der Seite (Sprache, Länge, Zeitraum, Ort, Stand, Ordnung)
              samt den SQL-Bausteinen dafür
  index       Volltext über Kapitel und Feed (die Videos pflegt search_index,
              das Gesagte transcripts)
  sources     je Bereich eine Quelle: Videos, Gesagtes, Kapitel, Abos, Kanäle,
              Playlists, Musik, Sinngemäßes
  engine      alle Bereiche auf einmal (Seite "Alles", Aufklappliste) oder
              einer seitenweise; Fundstellen eines Videos für die Vorschau
  vocabulary  Wortschatz aus Titeln: Ergänzen beim Tippen, "Meintest du"
  saved       gemerkte Suchen und ihre neuen Treffer

Die Quelle (YouTube) wird nur auf Wunsch gefragt (routers/search).
"""
