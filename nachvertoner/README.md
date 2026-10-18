# Nachvertoner

Eigenes Programm neben TubeVault. TubeVault führt nur die Warteliste; der
Nachvertoner holt Aufträge ab und gibt sie an die Apps, die die Arbeit tun:

- **Vertonen** über den Dienst der Vertonung. Die Stimme kommt aus deren
  Stimmen (Privat und Fremd, Vorgabe "Zeit Stimme"); die eingebauten Stimmen
  des Sprachmodells werden nie angeboten. Zurück an TubeVault geht nur die
  neue Tonspur; in der Kellerwolke bleibt nichts liegen (der Auftrag geht mit
  "nicht behalten" an die Vertonung und wird nach dem Abliefern abgeholt).
- **KI-Transkripte** über die Transkription: der Ton kommt in den eigenen
  Zweig der Kellerwolke und geht als Weitergabe (mit der Sprache des Videos)
  an die Transkription; das Transkript wird an TubeVault geliefert, danach
  liegt der Ton samt Transkript im Papierkorb der Kellerwolke.

Vertonungen gehen vor KI-Transkripten. Untertitel der Quelle werden
mitgeschickt, wenn TubeVault sie anbietet; sonst transkribiert die
Vertonung selbst (über die Transkription).

## Betrieb

Als Container `tubevault-nachvertoner` in `docker-compose.yml`, auf dem Pi
mit TubeVault ausgerollt. Er braucht:

- den App-Schlüssel des Zugangs "Nachvertoner" der Kellerwolke als Datei
  (`/home/pi/.nachvertoner_schluessel`, nur für pi lesbar),
- die Hausstelle der Vertonung (`/mnt/data/vertonung/zertifikate/rootCA.pem`),
- den Arbeitsordner `/mnt/data/tubevault/nachvertoner` (gehört pi).

ffmpeg kommt vom Pi (nur lesend eingehängt, `ffmpeg-vom-pi`).

Einstellungen (Umgebung, wahlweise in `nachvertoner/.env` auf dem Pi):

| Name | Vorgabe |
|---|---|
| `NACHVERTONER_VERTONUNG` | `https://192.168.178.49:8641` |
| `NACHVERTONER_KELLERWOLKE` | `http://192.168.178.49:39278` |
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
