// TubeVault – Handy-Ansicht oder volle Ansicht
//
// Telefone landen auf der eigenständigen Mobil-Ansicht (/m). "Volle Ansicht
// öffnen" gilt nur, bis Tab oder App schließen (sessionStorage); oben in der
// vollen Ansicht führt "Handy-Ansicht" jederzeit zurück. Die frühe
// Weiterleitung steht als Inline-Skript in index.html (läuft vor der App) und
// muss Merkmal und Abfrage genauso nennen wie hier (src/tests/mobileView.test.js
// prüft das).

export const FULL_VIEW_FLAG = 'tv_volle_ansicht';
export const PHONE_QUERY = '(pointer: coarse) and (max-width: 820px)';

const phoneQuery = () => (typeof window !== 'undefined' && window.matchMedia ? window.matchMedia(PHONE_QUERY) : null);

export const isPhone = () => !!phoneQuery()?.matches;

/** Meldet, ob gerade ein Telefon die Seite zeigt (auch nach dem Drehen); gibt die Abmeldung zurück */
export function watchPhone(onChange) {
  const query = phoneQuery();
  if (!query) return () => {};
  const handler = (e) => onChange(e.matches);
  query.addEventListener('change', handler);
  return () => query.removeEventListener('change', handler);
}

/** Passende Adresse der Mobil-Ansicht: ein Video bleibt dasselbe Video, sonst der Start */
export function mobilePath(pathname) {
  const watch = pathname.match(/^\/watch\/([^/]+)/);
  return watch ? `/m/video/${watch[1]}` : '/m/';
}

export function openFullView() {
  try { sessionStorage.setItem(FULL_VIEW_FLAG, '1'); } catch { /* Speicher gesperrt: die volle Ansicht gilt bis zum nächsten Laden */ }
  window.location.href = '/';
}

export function openMobileView() {
  try { sessionStorage.removeItem(FULL_VIEW_FLAG); } catch { /* Speicher gesperrt */ }
  window.location.href = mobilePath(window.location.pathname);
}
