// Abspielen einer Sammlung (Favoritenliste, Playlist): als Warteschlange der
// Videowiedergabe oder ganz als Ton im Musikspieler. Eine Stelle für alle
// Seiten, damit "Alle abspielen", "Zufällig" und "Weiterschauen" überall
// gleich arbeiten.
import { navigate } from '../router/router.js';
import { startQueue, queueNext, playlistQueue } from '../stores/playlistQueue.js';
import { musicPlayer } from '../stores/musicPlayer.svelte.js';
import { toast } from '../stores/notifications.js';
import { shuffled, continueIndex } from './collection.js';
import { get } from 'svelte/store';

/** Ab index abspielen. resume: an gemerkten Stellen fortsetzen. Noch nicht
 * geladene (vorgemerkte) Videos werden übersprungen. */
export function playCollection(source, title, items, index = 0, { resume = false, shuffle = false, repeat = false } = {}) {
  const wanted = items[Math.max(0, Math.min(index, items.length - 1))];
  const playable = items.filter(i => i.loaded !== false);
  if (!playable.length) { toast.info('Noch ist keines dieser Videos geladen'); return; }
  if (wanted && wanted.loaded === false && !shuffle) { toast.info('Dieses Video ist noch nicht geladen'); return; }
  const list = shuffle ? shuffled(playable) : playable;
  const start = shuffle ? 0 : Math.max(0, list.indexOf(wanted));
  startQueue(source, title, list, start, { resume, repeat });
  navigate(`/watch/${list[start].id}`);
}

/** Beim angefangenen Video weitermachen, sonst beim ersten neuen. */
export function continueCollection(source, title, items, options = {}) {
  items = items.filter(i => i.loaded !== false);
  const index = continueIndex(items);
  if (index < 0) {
    toast.info('Alles gesehen - startet von vorn');
    playCollection(source, title, items, 0, options);
    return;
  }
  playCollection(source, title, items, index, { ...options, resume: true });
}

/** Ganz als Ton im Musikspieler (auch Videos, die keine Musik sind). */
export function listenCollection(source, { shuffle = false } = {}) {
  musicPlayer.playSource(`sammlung:${source}`, { shuffle });
}

/** "Als Nächstes" gibt es nur, wenn gerade eine Warteschlange läuft. */
export function queueIsActive() {
  return get(playlistQueue).active;
}

export function playAfterCurrent(item) {
  queueNext(item);
  toast.info('Läuft als Nächstes');
}
