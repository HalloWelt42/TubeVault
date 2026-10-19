// TubeVault – Zur Stelle dauerhaft: eingeschaltet folgt die Titelliste auf dem
// Schirm von selbst dem laufenden Titel (utils/trackSpot.js), ausgeschaltet ist
// alles wie zuvor. Gemerkt je Gerät. Das Folgen rollt nur in der Liste, die
// gerade zu sehen ist; die Seite wechselt allein beim Einschalten (wie der Klick).
import { untrack } from 'svelte';
import { showTrack } from '../utils/trackSpot.js';
import { musicPlayer } from './musicPlayer.svelte.js';

const KEY = 'tv_titel_folgen';

function read() {
  try { return localStorage.getItem(KEY) === '1'; } catch { return false; }
}

function write(on) {
  try { localStorage.setItem(KEY, on ? '1' : '0'); } catch { /* Speicher gesperrt */ }
}

/** Ob bei diesem Stand gefolgt wird: eingeschaltet und ein anderer Titel als zuletzt
 *  (das Einschalten selbst springt über den Knopf, nicht hier) */
export function followsChange(on, previousId, id) {
  return on && !!id && id !== previousId;
}

class TrackFollow {
  on = $state(false);
  #id = $derived(musicPlayer.current?.id ?? null);
  #previousId = null;

  constructor() {
    if (typeof window === 'undefined') return;
    this.on = read();
    $effect.root(() => {
      $effect(() => {
        const id = this.#id;
        untrack(() => {
          if (followsChange(this.on, this.#previousId, id)) showTrack(musicPlayer.current);
          this.#previousId = id;
        });
      });
    });
  }

  /** Umschalten; liefert, ob es jetzt eingeschaltet ist */
  toggle() {
    this.on = !this.on;
    write(this.on);
    return this.on;
  }
}

export const trackFollow = new TrackFollow();
