/**
 * TubeVault – Lautstärke des Players
 * Der Player startet mit der zuletzt benutzten Lautstärke dieses Geräts.
 */
const KEY = 'player.lastVolume';
const FALLBACK = 0.8;

function stored() {
  try {
    const value = parseFloat(localStorage.getItem(KEY));
    return value >= 0 && value <= 1 ? value : FALLBACK;
  } catch { return FALLBACK; }
}

/** Letzte Lautstärke setzen und künftige Änderungen merken. */
export function keepVolume(player) {
  player.volume = stored();
  player.addEventListener('volumechange', () => {
    try { localStorage.setItem(KEY, String(player.volume)); } catch { /* Speicher gesperrt */ }
  });
}
