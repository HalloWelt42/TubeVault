// TubeVault – Ein Video von Hand als Musik festlegen oder nicht
//
// Eine Stelle für die Videoansicht, die Menüs und Kacheln der Videolisten
// und das Menü der Musik: die Wahl gilt als Nutzerwahl (die Automatik ändert
// sie nie mehr, backend music_flag.set_by_user). Musiklisten erfahren es über
// utils/musicChanges.js (music: { id, is_music }), auch das Liedtext-Fenster.
import { api } from '../api/client.js';
import { toast } from '../stores/notifications.js';
import { emitMusicChange } from './musicChanges.js';

/** Melden, dass ein Video jetzt Musik ist oder nicht mehr (gespeichert ist es schon) */
export function announceVideoMusic(id, isMusic) {
  const music = { id, is_music: isMusic };
  emitMusicChange(isMusic ? { music, restored: true, reload: true } : { music, removed: [id], reload: true });
}

/** Festlegen, melden, kurz bestätigen; liefert die neue Wahl */
export async function setVideoMusic(id, isMusic) {
  await api.setMusicBatch([id], isMusic);
  announceVideoMusic(id, isMusic);
  toast.success(isMusic ? 'Als Musik festgelegt' : 'Keine Musik mehr');
  return isMusic;
}

/** Menüeintrag "Als Musik" bzw. "Keine Musik" (ActionMenu); onChanged(isMusic) nach dem Speichern */
export function musicMenuItem(video, onChanged = () => {}) {
  const isMusic = !!video.is_music;
  return { icon: 'fa-music', label: isMusic ? 'Keine Musik' : 'Als Musik',
           run: async () => onChanged(await setVideoMusic(video.id, !isMusic)) };
}
