/**
 * Abspielbare Fassung eines Videos für dieses Gerät (HELF-242).
 *
 * Ob ein Gerät eine Datei abspielt, weiß nur das Gerät: der Server nennt
 * Container und Codecs, canPlayType entscheidet. Spielt das Gerät das
 * Original nicht, kommt die kompatible Fassung (H.264 in mp4); fehlt sie,
 * steht `blocked` an und convert() bestellt sie.
 *
 * mkv: canPlayType kennt den Container in manchen Browsern nicht, obwohl sie
 * ihn abspielen - dort wird probiert, und rejected() fängt den Fehlschlag.
 */
import { api } from '../api/client.js';

const POLL_MS = 3000;

export function canPlay(variant) {
  if (!variant || typeof document === 'undefined') return false;
  const probe = document.createElement('video');
  return probe.canPlayType(`${variant.mime}; codecs="${variant.codecs}"`) !== '';
}

export class PlayableSource {
  url = $state(null);        // gehört in <video src>; null, solange nichts abspielbar ist
  blocked = $state(null);    // { label, way }: das Gerät spielt das Original nicht
  job = $state(null);        // { status, progress }: Fassung wird gebaut
  #videoId = null;
  #media = null;
  #timer = null;

  async open(videoId) {
    this.close();
    this.#videoId = videoId;
    this.url = null; this.blocked = null; this.job = null; this.#media = null;
    let media;
    try {
      media = await api.getPlaybackMedia(videoId);
    } catch {
      if (this.#videoId === videoId) this.url = api.streamUrl(videoId);   // ohne Angaben: wie bisher
      return;
    }
    if (this.#videoId !== videoId) return;
    this.#media = media;
    if (canPlay(media.original)) {
      this.url = api.mediaUrl(media.original.url);
    } else if (media.compatible) {
      this.url = api.mediaUrl(media.compatible.url);
    } else if (media.original.mime === 'video/x-matroska') {
      this.url = api.mediaUrl(media.original.url);   // ausprobieren; rejected() fängt den Fehlschlag
    } else {
      this.#block();
    }
  }

  /** Das <video> meldet einen Fehler oder ein Bild ohne Breite (nur Ton). */
  rejected(element) {
    const media = this.#media;
    if (!media || !this.url || this.url !== api.mediaUrl(media.original.url)) return false;
    const noPicture = element && element.readyState >= 1 && element.videoWidth === 0
      && !media.original.label.startsWith('ohne Bild');
    if (element && !element.error && !noPicture) return false;
    if (media.compatible) this.url = api.mediaUrl(media.compatible.url);
    else this.#block();
    return true;
  }

  async convert() {
    if (!this.#videoId || this.job) return;
    const videoId = this.#videoId;
    const job = await api.makeCompatible(videoId);
    if (this.#videoId !== videoId) return;
    this.job = { status: job.status, progress: job.progress || 0 };
    this.#poll(videoId);
  }

  close() {
    clearTimeout(this.#timer);
    this.#timer = null;
  }

  #block() {
    this.url = null;
    this.blocked = { label: this.#media.original.label, way: this.#media.compatible_way };
    if (this.#media.job) {
      this.job = { status: this.#media.job.status, progress: this.#media.job.progress };
      this.#poll(this.#videoId);
    }
  }

  #poll(videoId) {
    clearTimeout(this.#timer);
    this.#timer = setTimeout(async () => {
      if (this.#videoId !== videoId) return;
      try {
        const media = await api.getPlaybackMedia(videoId);
        if (this.#videoId !== videoId) return;
        this.#media = media;
        if (media.compatible) {
          this.job = null; this.blocked = null;
          this.url = api.mediaUrl(media.compatible.url);
          return;
        }
        if (!media.job) { this.job = null; this.blocked = { ...this.blocked, failed: true }; return; }
        this.job = { status: media.job.status, progress: media.job.progress };
      } catch { /* nächster Versuch */ }
      this.#poll(videoId);
    }, POLL_MS);
  }
}
