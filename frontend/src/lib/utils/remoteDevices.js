/**
 * TubeVault – Fernsteuerung: reine Hilfen ohne Zustand
 * (Gerätearten, sichtbare Geräte, Stelle zwischen zwei Meldungen,
 * Wiedergabestand als Meldung). Genutzt von stores/remote.svelte.js und
 * den Ansichten; getestet in tests/remoteDevices.test.js.
 */
import { knownSeconds } from './mediaTime.js';

export const KIND_NAMES = { rechner: 'Rechner', handy: 'Handy', tablet: 'Tablet' };
export const KIND_ICONS = { rechner: 'fa-display', handy: 'fa-mobile-screen', tablet: 'fa-tablet-screen-button' };

/** Art des Geräts: grober Zeiger heißt Touch, die kurze Bildschirmseite trennt Handy und Tablet */
export function deviceKind(coarsePointer, screenWidth, screenHeight) {
  if (!coarsePointer) return 'rechner';
  const shortSide = Math.min(screenWidth || 0, screenHeight || 0);
  return shortSide > 0 && shortSide < 600 ? 'handy' : 'tablet';
}

/** Zufällige Kennung; crypto.randomUUID fehlt ohne https, getRandomValues nicht */
export function randomId() {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

function rank(device) {
  return (device.zustand?.laeuft ? 4e12 : 0) + (device.zustand ? 2e12 : 0) + (device.aktiv || 0);
}

/**
 * Die Geräte, wie man sie zeigt: dieses Fenster zuerst, dann je anderem
 * Browser genau ein Fenster (das spielende, sonst das zuletzt genutzte).
 * Weitere Fenster des eigenen Browsers bleiben verborgen.
 */
export function visibleDevices(devices, myId) {
  const me = devices.find((d) => d.id === myId) || null;
  const best = new Map();
  for (const device of devices) {
    if (device.id === myId || (me && device.geraet === me.geraet)) continue;
    const current = best.get(device.geraet);
    if (!current || rank(device) > rank(current)) best.set(device.geraet, device);
  }
  const others = [...best.values()].sort((a, b) => rank(b) - rank(a));
  return me ? [me, ...others] : others;
}

/** Das andere Gerät, das gerade spielt (das zuletzt genutzte), sonst null */
export function playingElsewhere(devices, myId) {
  return visibleDevices(devices, myId).find((d) => d.id !== myId && d.zustand?.laeuft) || null;
}

/** Stelle jetzt: zwischen zwei Meldungen läuft die Zeit beim spielenden Gerät weiter */
export function positionOf(state, receivedAt, now) {
  if (!state) return 0;
  if (!state.laeuft || receivedAt == null) return state.stelle || 0;
  const position = (state.stelle || 0) + Math.max(0, now - receivedAt) / 1000;
  return state.dauer ? Math.min(state.dauer, position) : position;
}

/** Was eine Musik- oder Hörbuchwiedergabe meldet (null: nichts geladen) */
export function musicState(player, canVolume) {
  const track = player.current;
  if (!track) return null;
  const book = !!player.audiobook;
  return {
    art: book ? 'hoerbuch' : 'musik',
    kennung: track.id,
    titel: track.title || '',
    untertitel: track.artist || '',
    quelle: book ? `Teil ${player.index + 1} von ${player.queue.length}`
      : player.segment ? `${player.segment.index + 1}/${player.segment.count} ${player.segment.title}` : (player.title || ''),
    stelle: knownSeconds(player.time),
    dauer: knownSeconds(player.duration, track.duration),
    laeuft: !!player.playing,
    lautstaerke: canVolume ? player.volume : null,
    zufall: book ? null : !!player.shuffle,
    wiederholen: book ? null : player.repeat,
    liebling: !!track.favorite,
    kann: ['sprung', ...(player.index + 1 < player.queue.length || player.repeat === 'all'
                         || (player.segment && player.segment.index + 1 < player.segment.count) ? ['weiter'] : []), 'zurueck'],
  };
}

/** Was eine Videowiedergabe meldet (null: kein Video offen) */
export function videoState(session, canVolume) {
  const el = session.el;
  if (!el || !session.video) return null;
  return {
    art: 'video',
    kennung: session.video.id,
    titel: session.video.title || '',
    untertitel: session.video.channel_name || '',
    quelle: '',
    stelle: knownSeconds(el.currentTime),
    dauer: knownSeconds(el.duration, session.video.duration),
    laeuft: !el.paused,
    lautstaerke: canVolume ? el.volume : null,
    tonspuren: session.tracks.map((t) => ({ id: t.id, label: t.label })),
    tonspur: session.trackId,
    kann: ['sprung', ...(session.canNext ? ['weiter'] : []), ...(session.canPrev ? ['zurueck'] : [])],
  };
}
