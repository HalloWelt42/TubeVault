// Ein Musiktitel ist entweder ein Musikvideo oder eine Datei der eigenen
// Sammlung (kind 'datei', Kennung 'f' + 15 Hexzeichen). Diese eine Stelle
// weiß, woher Bild, Ton, Liedtext kommen und wohin Wiedergaben und
// Lieblingssongs gehen - Spieler, Kacheln und Listen fragen nur hier.
import { api } from '../api/client.js';

const FILE_ID = /^f[0-9a-f]{15}$/;

/** Gilt für einen Titel oder eine Kennung (Collagen kennen nur Kennungen). */
export const isFile = (trackOrId) =>
  typeof trackOrId === 'string' ? FILE_ID.test(trackOrId) : trackOrId?.kind === 'datei';

const idOf = (trackOrId) => (typeof trackOrId === 'string' ? trackOrId : trackOrId.id);

export const coverUrl = (trackOrId) =>
  isFile(trackOrId) ? api.musicCoverUrl(idOf(trackOrId)) : api.thumbnailUrl(idOf(trackOrId));

export const audioSrc = (track) => (isFile(track) ? api.musicFileStreamUrl(track.id) : api.streamUrl(track.id));

export const downloadUrl = (track) =>
  isFile(track) ? api.musicFileDownloadUrl(track.id) : api.audioDownloadUrl(track.id, 'original');

export const loadLyrics = (track) => (isFile(track) ? api.musicFileLyrics(track.id) : api.getLyrics(track.id));

export const recordPlay = (track) => (isFile(track) ? api.musicFilePlayed(track.id) : api.recordPlay(track.id, 0));

export async function setFavorite(track, favorite) {
  if (isFile(track)) return api.musicFileFavorite(track.id, favorite);
  return favorite ? api.addFavorite({ video_id: track.id }) : api.removeFavorite(track.id);
}

/** "Gefällt nicht": ein Video wird gelöscht, eine Datei der Sammlung nur ausgeblendet
 *  (die Sammlung ist lesend eingebunden, die Datei bleibt unberührt) */
export const discard = (track) => (isFile(track) ? api.musicFileHidden(track.id, true) : api.deleteVideo(track.id));
