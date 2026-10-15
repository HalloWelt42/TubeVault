/**
 * TubeVault – Wie die Musikleiste am Rechner erscheint: groß über der
 * Fußleiste oder schlank in der Fußleiste (nur Steuerung). Die Wahl gilt je
 * Browser und bleibt über das Neuladen hinaus.
 */
const KEY = 'musik.leiste_schlank';

function read() {
  try { return localStorage.getItem(KEY) === '1'; } catch { return false; }
}

class PlayerBar {
  compact = $state(typeof window !== 'undefined' && read());

  setCompact(value) {
    this.compact = !!value;
    try { localStorage.setItem(KEY, this.compact ? '1' : '0'); } catch { /* nur diese Sitzung */ }
  }
}

export const playerBar = new PlayerBar();
