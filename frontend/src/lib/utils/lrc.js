// Zeitgenaue Liedtexte (LRC, "[mm:ss.xx] Zeile"): eine Stelle für das
// Liedtext-Fenster der Wiedergabe und den Musikspieler.

const LINE = /^\[(\d+):(\d+)(?:[.:](\d+))?\]\s*(.*)$/;

/** Zeilen [{ time: Sekunden, text }] in Zeitfolge; Kopfangaben wie [ar:...] entfallen. */
export function parseLrc(text) {
  const lines = [];
  for (const raw of (text || '').split('\n')) {
    const m = raw.trim().match(LINE);
    if (!m) continue;
    // Bruchteil wie geschrieben: ".5" = 0,5 s, ".05" = 0,05 s, ".500" = 0,5 s
    const fraction = m[3] ? parseFloat(`0.${m[3]}`) : 0;
    lines.push({ time: parseInt(m[1], 10) * 60 + parseInt(m[2], 10) + fraction, text: m[4] });
  }
  return lines.sort((a, b) => a.time - b.time);
}

/** Index der Zeile, die zur Zeit t gerade läuft (-1 vor der ersten). */
export function lineAt(lines, t, offset = 0) {
  let index = -1;
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].time + offset <= t) index = i; else break;
  }
  return index;
}
