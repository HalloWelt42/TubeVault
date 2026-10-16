// Lautstärke auch dort, wo die Seite audio.volume nicht setzen darf (iOS):
// über den Verstärker, aber nur mit Wiedergabe-Sitzung, erst beim Leiserstellen
// und nur bei laufendem Verstärker (sonst verstummte der Ton).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createVolume, elementVolumeWorks, volumeMode } from '../lib/utils/softVolume.js';

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

class FakeContext {
  static made = [];
  state = 'suspended';
  allowed = true;          // false: der Browser gibt den Ton nicht frei
  routed = 0;
  gains = [];
  destination = {};
  constructor() { FakeContext.made.push(this); }
  async resume() { if (this.allowed) this.state = 'running'; }
  async suspend() { this.state = 'suspended'; }
  createGain() {
    const node = { gain: { value: 1 }, connect: (next) => next };
    this.gains.push(node);
    return node;
  }
  createMediaElementSource() {
    this.routed += 1;
    return { connect: (next) => next };
  }
}

function lockedVolume() {
  // wie iOS: der Wert bleibt bei 1
  vi.stubGlobal('Audio', class { get volume() { return 1; } set volume(_) {} });
}

describe('Lautstärke: welche Art', () => {
  afterEach(() => { vi.unstubAllGlobals(); delete navigator.audioSession; });

  it('nimmt das Element, wo audio.volume wirkt', () => {
    expect(elementVolumeWorks()).toBe(true);
    expect(volumeMode()).toBe('element');
  });

  it('nimmt den Verstärker nur mit Wiedergabe-Sitzung und eigenem Ton', () => {
    lockedVolume();
    vi.stubGlobal('AudioContext', FakeContext);
    expect(volumeMode()).toBeNull();                       // älteres iOS: keine Sitzung, keine Lautstärke
    navigator.audioSession = { type: 'auto' };
    expect(volumeMode()).toBe('gain');
    expect(volumeMode({ gainAllowed: false })).toBeNull(); // fremder Ursprung käme als Stille an
  });
});

describe('Lautstärke über den Verstärker', () => {
  let audio;
  beforeEach(() => {
    FakeContext.made = [];
    vi.stubGlobal('AudioContext', FakeContext);
    navigator.audioSession = { type: 'auto' };
    audio = document.createElement('audio');
  });
  afterEach(() => { vi.unstubAllGlobals(); delete navigator.audioSession; });

  it('lässt das Element unberührt, solange voll', async () => {
    const volume = createVolume(audio, 'gain');
    volume.set(1);
    volume.prepare();
    await settle();
    const [context] = FakeContext.made;
    expect(navigator.audioSession.type).toBe('playback');
    expect(context.routed).toBe(0);
    expect(context.state).toBe('suspended');              // ruht, bis er gebraucht wird
  });

  it('leitet beim Leiserstellen um und stellt danach nur noch nach', async () => {
    const volume = createVolume(audio, 'gain');
    volume.prepare();
    await settle();
    volume.set(0.4);
    await settle();
    const [context] = FakeContext.made;
    expect(context.routed).toBe(1);
    expect(context.gains[0].gain.value).toBe(0.4);
    volume.set(1);
    volume.set(0.7);
    await settle();
    expect(context.routed).toBe(1);
    expect(context.gains[0].gain.value).toBe(0.7);
  });

  it('übernimmt eine gemerkte Lautstärke mit der ersten Nutzeraktion', async () => {
    const volume = createVolume(audio, 'gain');
    volume.set(0.5);                                      // vor der Nutzeraktion: noch kein Verstärker
    expect(FakeContext.made).toHaveLength(0);
    volume.prepare();
    await settle();
    expect(FakeContext.made[0].routed).toBe(1);
    expect(FakeContext.made[0].gains[0].gain.value).toBe(0.5);
  });

  it('leitet nie in einen angehaltenen Verstärker um', async () => {
    const volume = createVolume(audio, 'gain');
    volume.prepare();
    await settle();
    FakeContext.made[0].allowed = false;
    volume.set(0.3);
    await settle();
    expect(FakeContext.made[0].routed).toBe(0);
  });

  it('ruht in der Pause und läuft mit dem Abspielen wieder an', async () => {
    const volume = createVolume(audio, 'gain');
    volume.prepare();
    await settle();
    volume.set(0.5);
    await settle();
    const [context] = FakeContext.made;
    audio.dispatchEvent(new Event('play'));
    await settle();
    expect(context.state).toBe('running');
    audio.dispatchEvent(new Event('pause'));
    await settle();
    expect(context.state).toBe('suspended');
    audio.dispatchEvent(new Event('play'));
    await settle();
    expect(context.state).toBe('running');
  });
});
