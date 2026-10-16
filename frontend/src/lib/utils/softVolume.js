/**
 * TubeVault – Lautstärke eines Ton-Elements, auch wo die Seite sie nicht setzen darf
 *
 * iOS lässt audio.volume nicht ändern: der Wert bleibt 1, nur die Tasten
 * am Gerät wirken (und eine Fernsteuerung dorthin lief ins Leere). Dort
 * führt der Ton über einen Verstärker im Browser (Web Audio, GainNode).
 *
 * Vorsicht mit dem Sperrbildschirm: iOS hält Web Audio im Hintergrund an,
 * außer die Seite hat eine Wiedergabe-Sitzung angemeldet
 * (navigator.audioSession, iOS ab 16.4). Darum:
 *   - ohne diese Anmeldung keine Lautstärke in der Seite (Wiedergabe geht vor),
 *   - umgeleitet wird erst, wenn jemand leiser als voll stellt; bis dahin
 *     bleibt das Element unberührt,
 *   - nur bei laufendem Verstärker: ein angehaltener ließe den Ton verstummen.
 * Die Umleitung gilt für das Element bis zum Neuladen (Web Audio kennt kein
 * Zurück); der Verstärker ruht, solange nichts spielt.
 *
 *   const mode = volumeMode({ gainAllowed });   // 'element', 'gain' oder null
 *   const volume = createVolume(audio, mode);
 *   volume.prepare();     // in einer Nutzeraktion (iOS gibt Ton nur dort frei)
 *   volume.set(0.6);
 */

/** Wirkt audio.volume auf diesem Gerät? (iOS: nein) */
export function elementVolumeWorks() {
  try {
    const probe = new Audio();
    probe.volume = 0.5;
    return probe.volume === 0.5;
  } catch {
    return false;
  }
}

/**
 * Wie die Lautstärke hier gestellt wird: 'element', 'gain' oder null (gar nicht).
 * gainAllowed: nur bei Ton vom eigenen Ursprung (fremder Ton ohne CORS kommt
 * im Verstärker als Stille an).
 */
export function volumeMode({ gainAllowed = true } = {}) {
  if (elementVolumeWorks()) return 'element';
  const gainReady = gainAllowed && typeof AudioContext !== 'undefined'
    && typeof navigator !== 'undefined' && 'audioSession' in navigator;
  return gainReady ? 'gain' : null;
}

/** Lautstärke für ein Element in der Art, die volumeMode() ergab */
export function createVolume(element, mode) {
  if (mode === 'gain') return new GainVolume(element);
  return {
    mode,
    prepare() {},
    set(value) { if (mode === 'element') element.volume = value; },
  };
}

class GainVolume {
  mode = 'gain';
  #element;
  #context = null;
  #gain = null;
  #value = 1;

  constructor(element) {
    this.#element = element;
    element.addEventListener('play', () => this.#wake());
    element.addEventListener('pause', () => this.#rest());
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible' && !element.paused) this.#wake();
    });
  }

  /** In einer Nutzeraktion: Wiedergabe-Sitzung anmelden und den Verstärker
   *  einmal starten. Danach darf er auch ohne Nutzeraktion wieder anlaufen
   *  (Fernsteuerung, Sperrbildschirm). */
  prepare() {
    try { navigator.audioSession.type = 'playback'; } catch { /* älteres Gerät */ }
    if (this.#context) return;
    try { this.#context = new AudioContext(); } catch { return; }
    this.#context.resume().then(() => {
      if (this.#value < 1) this.#route();    // schon vorher leiser gestellt (gemerkte Lautstärke)
      else this.#rest();
    }).catch(() => {});
  }

  set(value) {
    this.#value = value;
    if (this.#gain) this.#gain.gain.value = value;
    else if (value < 1) this.#route();
  }

  async #route() {
    const context = this.#context;
    if (!context || this.#gain) return;
    try { await context.resume(); } catch { return; }
    if (context.state !== 'running' || this.#gain) return;
    const gain = context.createGain();
    gain.gain.value = this.#value;
    context.createMediaElementSource(this.#element).connect(gain).connect(context.destination);
    this.#gain = gain;
    if (this.#element.paused) this.#rest();
  }

  #wake() {
    if (this.#gain && this.#context.state !== 'running') this.#context.resume().catch(() => {});
  }

  #rest() {
    if (this.#context?.state === 'running') this.#context.suspend().catch(() => {});
  }
}
