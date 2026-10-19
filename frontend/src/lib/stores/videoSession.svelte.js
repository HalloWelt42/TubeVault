/**
 * TubeVault – Die laufende Videowiedergabe dieses Fensters
 *
 * Die Wiedergabe am Rechner (routes/Watch.svelte) und am Handy
 * (mobile/views/Video.svelte) meldet hier ihr <video> an, die Tonspur-Wahl
 * ihre Spuren. So kann die Fernsteuerung (stores/remote.svelte.js) ein Video
 * bedienen, ohne die Seiten zu kennen.
 *
 *   videoSession.attach(el, { id, title, channel_name, duration }, { next, prev, hasNext, hasPrev, queue, canRemove, remove })
 *     canRemove/remove: läuft das Video aus einer Playlist, nimmt remove() es dort heraus
 *     (utils/playlistRemoval.js) und liefert das Rückgängig
 *   videoSession.detach(el)
 *   videoSession.setTracks(tracks, activeId, (id) => ...)   // null = Original
 */
const EVENTS = ['play', 'pause', 'volumechange', 'ended', 'loadedmetadata', 'seeked', 'ratechange'];

class VideoSession {
  el = $state(null);
  video = $state(null);          // { id, title, channel_name, duration }
  playing = $state(false);
  volume = $state(1);
  changes = $state(0);           // zählt Sprünge und Wechsel: Anlass, den Stand neu zu melden
  tracks = $state([]);           // [{ id, label, language }]
  trackId = $state(null);        // null: Original-Ton

  #nav = null;
  #choose = null;
  #release = null;

  attach(el, video, nav = null) {
    if (!el) return;
    this.#unbind();
    this.el = el;
    this.video = video;
    this.#nav = nav;
    const sync = () => { this.playing = !el.paused; this.volume = el.volume; this.changes++; };
    EVENTS.forEach((name) => el.addEventListener(name, sync));
    this.#release = () => EVENTS.forEach((name) => el.removeEventListener(name, sync));
    sync();
  }

  /** Nur das eigene Element abmelden: die nächste Seite kann schon angemeldet sein */
  detach(el) {
    if (!el || el !== this.el) return;
    this.#unbind();
    this.el = null;
    this.video = null;
    this.#nav = null;
    this.playing = false;
    this.clearTracks();
  }

  #unbind() {
    this.#release?.();
    this.#release = null;
  }

  setTracks(tracks, activeId, choose) {
    this.tracks = tracks || [];
    this.trackId = activeId ?? null;
    this.#choose = choose;
  }

  clearTracks() {
    this.tracks = [];
    this.trackId = null;
    this.#choose = null;
  }

  chooseTrack(id) {
    if (!this.#choose) return;
    this.#choose(id && this.tracks.some((t) => t.id === id) ? id : null);
  }

  get language() {
    return this.tracks.find((t) => t.id === this.trackId)?.language || null;
  }

  get canNext() { return !!this.#nav?.hasNext?.(); }
  get canPrev() { return !!this.#nav?.hasPrev?.(); }
  get canRemove() { return !!this.#nav?.canRemove?.(); }
  next() { this.#nav?.next?.(); }
  prev() { this.#nav?.prev?.(); }
  /** Aus der Playlist nehmen, aus der es läuft; liefert das Rückgängig (oder null) */
  remove() { return this.canRemove ? this.#nav.remove() : Promise.resolve(null); }

  /** Warteschlange, aus der das Video läuft: { liste, idx } oder leer */
  queue() { return this.#nav?.queue?.() || {}; }
}

export const videoSession = new VideoSession();
