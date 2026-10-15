// Liedtext eines Musiktitels, zeitgenau, wenn es ihn so gibt. Eine Stelle
// für das Liedtext-Fenster am Rechner (components/music/NowPlaying.svelte)
// und den Liedtext am Handy; woher der Text kommt, weiß utils/musicTrack.js.
import { loadLyrics } from './musicTrack.js';
import { parseLrc, lineAt } from './lrc.js';

export class TrackLyrics {
  id = $state(null);          // Titel, zu dem der Text gehört
  plain = $state('');
  synced = $state([]);        // [{ time, text }] in Zeitfolge
  offset = $state(0);         // Versatz in Sekunden
  loading = $state(false);

  /** Für diesen Titel laden; ist er schon da oder unterwegs, geschieht nichts.
   *  Liest und schreibt id: in einem $effect nur über untrack aufrufen. */
  load(track) {
    const id = track?.id || null;
    if (id === this.id) return;
    Object.assign(this, { id, plain: '', synced: [], offset: 0, loading: !!id });
    if (!id) return;
    loadLyrics(track)
      .then((res) => {
        if (this.id !== id) return;
        Object.assign(this, { plain: res?.plain || '', synced: parseLrc(res?.synced), offset: res?.offset || 0 });
      })
      .catch(() => {})
      .finally(() => { if (this.id === id) this.loading = false; });
  }

  /** Index der Zeile, die zur Zeit t läuft (-1 davor oder ohne Zeitangaben) */
  lineAt(t) { return lineAt(this.synced, t, this.offset); }

  /** Stelle in Sekunden, an der Zeile i beginnt */
  timeOf(i) { return (this.synced[i]?.time ?? 0) + this.offset; }
}
