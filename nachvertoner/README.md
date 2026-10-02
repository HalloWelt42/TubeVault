# Nachvertoner

Eigenes Programm für den Rechner, der vertonen kann. TubeVault auf dem Pi
führt nur die Warteliste; dieses Programm holt Aufträge ab, wenn der
Vertonungsdienst frei ist, und liefert die fertige Tonspur zurück. In
TubeVault lässt sie sich dann in der Wiedergabe umschalten.

## Einrichten

1. In TubeVault unter Einstellungen → Erweiterungen die Nachvertonung
   einschalten und die Stimme eintragen.
2. Einstellungen anlegen:

   ```bash
   cp nachvertoner.beispiel.toml nachvertoner.toml
   ```

3. Prüfen, ob beide Seiten erreichbar sind und die Stimme gefunden wird:

   ```bash
   ./nachvertoner.py --pruefen
   ```

## Betrieb

```bash
./nachvertoner.py            # läuft dauerhaft, fragt regelmäßig nach Arbeit
./nachvertoner.py --einmal   # höchstens ein Auftrag
```

Das Programm arbeitet nur, wenn der Vertonungsdienst bereit ist und dort
gerade kein anderer Auftrag läuft. Es bearbeitet einen Auftrag nach dem
anderen. Wird ein Auftrag in TubeVault entfernt, bricht die Vertonung ab.
Stürzt der Rechner ab, kehrt der Auftrag nach 30 Minuten ohne Lebenszeichen
in die Warteliste zurück.

Voraussetzungen: `uv` und `ffmpeg`.

## Was übertragen wird

Zum Vertonen genügt der Ton. Das Programm baut deshalb eine leichte
Arbeitskopie (Originalton plus winziges schwarzes Bild) und gibt nur diese
an den Vertonungsdienst. Zurück an TubeVault geht ausschließlich die neue
Tonspur; Arbeitsdateien werden auf beiden Seiten wieder entfernt.
