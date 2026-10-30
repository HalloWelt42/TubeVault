# Nachvertoner

Eigenes Programm neben TubeVault. TubeVault führt nur die Warteliste; der
Nachvertoner holt Aufträge ab und gibt sie an die Apps, die die Arbeit tun:

- **Vertonen** über den Dienst der Vertonung. Zur Wahl stehen nur deren
  private Stimmen, die die Erlaubnisliste der Vertonung dem Nachvertoner
  freigibt (Vorgabe "Zeit Stimme"); die fremden (aus Videos gesammelt, nur
  vorübergehend) und die eingebauten Stimmen des Sprachmodells werden nie
  angeboten. Zurück an TubeVault gehen das Transkript der Quelle (wenn die
  Vertonung transkribieren ließ; wird KI-Transkript), sobald die Vertonung
  es hat, nicht erst mit der Tonspur (es bleibt, auch wenn die Vertonung
  danach scheitert), und am Ende die neue Tonspur mit dem Text der neuen
  Tonspur an seinen Zeiten (wird Untertitel "Text der Vertonung"). In der
  Kellerwolke bleibt nichts liegen (der Auftrag geht mit "nicht behalten" an
  die Vertonung und wird nach dem Abliefern abgeholt).
- **Originalstimmen**: wer beim Vormerken die Stimme "Originalstimmen" wählt,
  bekommt je Sprecher seine eigene Stimme aus dem Video (eine früher
  gewonnene wird wiederverwendet, sonst schneidet die Vertonung die beste
  Stelle aus); wer keine brauchbare Stelle hat, spricht mit der Vorgabestimme.
- **KI-Transkripte** über die Transkription: der Ton kommt in den eigenen
  Zweig der Kellerwolke und geht als Weitergabe (mit der Sprache des Videos)
  an die Transkription; das Transkript wird an TubeVault geliefert, danach
  liegt der Ton samt Transkript im Papierkorb der Kellerwolke.

Vertonungen gehen vor KI-Transkripten. Untertitel der Quelle werden
mitgeschickt, wenn TubeVault sie anbietet; sonst transkribiert die
Vertonung selbst (über die Transkription).

Der Nachvertoner rechnet keinen Ton: aus dem Video löst er nur die Tonspur,
Paket für Paket umgepackt in Matroska (jede Kodierung passt, nie neu
kodiert). Gewandelt wird im Tondienst auf dem Mac.

## Betrieb

Als Container `tubevault-nachvertoner` in `docker-compose.yml`, auf dem Pi
mit TubeVault ausgerollt. Er braucht:

- den App-Schlüssel des Zugangs "Nachvertoner" der Kellerwolke als Datei
  (`NACHVERTONER_SCHLUESSEL` in der .env, nur für den Benutzer des Pi lesbar),
- die Hausstelle der Vertonung (`NACHVERTONER_CA` in der .env),
- den Arbeitsordner `nachvertoner` unter `TUBEVAULT_INDEX` (gehört dem Benutzer des Pi).

ffmpeg kommt vom Pi (nur lesend eingehängt, `ffmpeg-vom-pi`) und packt nur um.

Adressen (Pflicht, in der .env neben `docker-compose.yml`, Beispiele in `.env.example`):

| Name | Beispiel |
|---|---|
| `NACHVERTONER_VERTONUNG` | `https://192.168.1.20:8641` |
| `NACHVERTONER_KELLERWOLKE` | `http://192.168.1.20:39278` |

Weitere Einstellungen (Umgebung, wahlweise in `nachvertoner/.env` auf dem Pi):

| Name | Vorgabe |
|---|---|
| `NACHVERTONER_STIMME` | `Zeit Stimme` (wenn der Auftrag keine nennt) |
| `NACHVERTONER_TRANSKRIPTION` | `Transkription` (Name der App in der Kellerwolke) |
| `NACHVERTONER_ABFRAGE_S` | `60` (Pause, wenn nichts zu tun war) |
| `NACHVERTONER_FORTSCHRITT_S` | `15` (Takt der Lebenszeichen) |

Prüfen, ob alles erreichbar ist und die Stimmen da sind:

```bash
docker exec tubevault-nachvertoner python nachvertoner.py --pruefen
```

## Entwicklung

```bash
python3 -m venv nachvertoner/.venv
nachvertoner/.venv/bin/pip install -r nachvertoner/requirements.txt pytest pytest-asyncio
cd nachvertoner && .venv/bin/python -m pytest -q
```

Die Tests stellen TubeVault, Vertonung und Kellerwolke nach; ffmpeg arbeitet
echt.
