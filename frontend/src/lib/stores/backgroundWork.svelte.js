// Hintergrundarbeiten (/api/system/background): ein Abruf für alle Anzeigen.
// Statusleiste und Übersichtskarte fragten bisher je für sich alle 8 s - je
// Fenster zwei teure Abfragen (gemessen 1,1 s Datenbankzeit). Wer die Daten
// zeigt, meldet sich mit use() an; abgerufen wird, solange jemand zusieht.
import { api } from '../api/client.js';
import { switchWork } from '../utils/backgroundWork.js';

const REFRESH_MS = 8000;

class BackgroundWork {
  items = $state(null);          // null: noch nicht geladen

  #users = 0;
  #timer = null;

  /** Anmelden; liefert die Abmeldung (in onMount zurückgeben). */
  use() {
    if (this.#users++ === 0) {
      this.load();
      this.#timer = setInterval(() => this.load(), REFRESH_MS);
    }
    return () => {
      if (--this.#users === 0) {
        clearInterval(this.#timer);
        this.#timer = null;
      }
    };
  }

  async load() {
    try { this.items = (await api.getBackgroundWork()).items || []; } catch { /* bleibt beim letzten Stand */ }
  }

  /** Angehaltene Arbeit fortsetzen, laufende anhalten - danach frisch laden. */
  async toggle(item) {
    await switchWork(item);
    await this.load();
  }
}

export const backgroundWork = new BackgroundWork();
