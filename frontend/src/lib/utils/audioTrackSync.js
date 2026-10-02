/**
 * TubeVault – Zusatz-Tonspur im Gleichlauf mit dem Video
 *
 * Eine zusätzliche Tonspur (z.B. deutsche Nachvertonung) ist eine eigene
 * Audiodatei. Zum Umschalten wird das Video stumm geschaltet und ein
 * <audio>-Element im Gleichlauf geführt: Start, Pause, Sprung, Tempo und
 * Lautstärke folgen dem Video. Gemeinsam genutzt von der grossen und der
 * Mobil-Ansicht.
 *
 *   const sync = followVideo(videoEl, audioEl);
 *   ...
 *   sync.stop();   // Original-Ton wieder an
 */
const MAX_DRIFT_S = 0.25;

export function followVideo(video, audio) {
  const userMuted = video.muted;

  const align = () => {
    if (Math.abs(audio.currentTime - video.currentTime) > MAX_DRIFT_S) {
      audio.currentTime = video.currentTime;
    }
  };
  const play = () => { align(); audio.playbackRate = video.playbackRate; audio.play().catch(() => {}); };
  const pause = () => audio.pause();
  const seek = () => { audio.currentTime = video.currentTime; };
  const rate = () => { audio.playbackRate = video.playbackRate; };
  const volume = () => {
    audio.volume = video.volume;
    // Das Video bleibt stumm. Hebt der Nutzer die Stummschaltung am Player
    // auf, gilt das der Zusatzspur: sie wird umgeschaltet, das Video wieder
    // stumm - sonst liefen beide Sprachen gleichzeitig.
    if (!video.muted) {
      audio.muted = !audio.muted;
      video.muted = true;
    }
  };

  const listeners = [
    ['play', play], ['playing', play], ['pause', pause], ['waiting', pause], ['ended', pause],
    ['seeking', seek], ['seeked', seek], ['ratechange', rate], ['volumechange', volume],
    ['timeupdate', () => { if (!video.paused) align(); }],
  ];

  audio.volume = video.volume;
  audio.muted = userMuted;
  video.muted = true;
  audio.currentTime = video.currentTime;
  listeners.forEach(([name, handler]) => video.addEventListener(name, handler));
  if (!video.paused) play();

  return {
    stop() {
      listeners.forEach(([name, handler]) => video.removeEventListener(name, handler));
      const wasMuted = audio.muted;
      audio.pause();
      video.muted = wasMuted;
    },
  };
}

const PREFERENCE_KEY = 'tv_tonspur_sprache';

/** Zuletzt gewählte Tonspur-Sprache ('' = Original). Gilt für alle Videos. */
export function preferredLanguage() {
  try { return localStorage.getItem(PREFERENCE_KEY) || ''; } catch { return ''; }
}

export function rememberLanguage(language) {
  try { localStorage.setItem(PREFERENCE_KEY, language || ''); } catch { /* ohne Speicher: nur diese Sitzung */ }
}
