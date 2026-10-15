/**
 * TubeVault – Versionswache: wann nach einem Update selbsttätig neu geladen wird
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { writable, get } from 'svelte/store';

vi.mock('../lib/api/client.js', () => ({ FE_VERSION: '1.0.0' }));

const stops = [];   // jede gestartete Wache wird nach dem Test wieder abgebaut
const served = (version) => vi.fn(async () => ({ json: async () => ({ version }) }));

async function start({ version, after = 0, eager = false }) {
  vi.resetModules();
  vi.stubGlobal('fetch', served(version));
  const watch = await import('../lib/utils/versionWatch.js');
  const reload = vi.spyOn(watch.page, 'reload').mockImplementation(() => {});
  vi.setSystemTime(Date.now() + after);
  const route = writable('/');
  stops.push(watch.startVersionWatch(route, { eager }));
  await vi.waitFor(() => expect(fetch).toHaveBeenCalled());
  await new Promise(r => setTimeout(r));
  return { watch, reload, route };
}

describe('Versionswache', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date', 'setInterval'] });
    sessionStorage.clear();
    document.body.innerHTML = '';
  });
  afterEach(() => {
    stops.splice(0).forEach((stop) => stop());
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('bleibt still, solange die laufende Version aktuell ist', async () => {
    const { watch, reload } = await start({ version: '1.0.0' });
    expect(get(watch.newVersion)).toBeNull();
    expect(reload).not.toHaveBeenCalled();
  });

  it('lädt kurz nach dem Start sofort neu, aber je Version nur einmal', async () => {
    const first = await start({ version: '1.1.0' });
    expect(first.reload).toHaveBeenCalledTimes(1);
    const second = await start({ version: '1.1.0' });
    expect(second.reload).not.toHaveBeenCalled();
  });

  it('wartet bei offener Seite auf den nächsten Seitenwechsel', async () => {
    const { watch, reload, route } = await start({ version: '1.1.0', after: 20000 });
    expect(get(watch.newVersion)).toBe('1.1.0');
    expect(reload).not.toHaveBeenCalled();
    route.set('/downloads');
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it('unterbricht keine laufende Wiedergabe', async () => {
    const video = document.createElement('video');
    Object.defineProperty(video, 'paused', { value: false });
    document.body.append(video);
    const { reload, route } = await start({ version: '1.1.0' });
    route.set('/downloads');
    expect(reload).not.toHaveBeenCalled();
  });

  it('Handy-App: lädt sofort neu, sobald nichts spielt, auch bei offener Seite', async () => {
    const { reload } = await start({ version: '1.1.0', after: 20000, eager: true });
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it('Handy-App: lässt den laufenden Titel zu Ende spielen und lädt beim Anhalten neu', async () => {
    vi.useRealTimers();   // neu einrichten, diesmal mit setTimeout (Wartezeit nach dem Anhalten)
    vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'setTimeout'] });
    const audio = document.createElement('audio');
    let paused = false;
    Object.defineProperty(audio, 'paused', { get: () => paused });
    document.body.append(audio);
    vi.resetModules();
    vi.stubGlobal('fetch', served('1.1.0'));
    const watch = await import('../lib/utils/versionWatch.js');
    const reload = vi.spyOn(watch.page, 'reload').mockImplementation(() => {});
    vi.setSystemTime(Date.now() + 20000);
    stops.push(watch.startVersionWatch(writable('/'), { eager: true }));
    await vi.waitFor(() => expect(get(watch.newVersion)).toBe('1.1.0'));
    expect(reload).not.toHaveBeenCalled();

    // Titelwechsel: kurz angehalten, gleich weiter - kein Neuladen
    paused = true;
    audio.dispatchEvent(new Event('pause'));
    paused = false;
    vi.advanceTimersByTime(2000);
    expect(reload).not.toHaveBeenCalled();

    // Angehalten und bleibt so: jetzt
    paused = true;
    audio.dispatchEvent(new Event('pause'));
    vi.advanceTimersByTime(2000);
    expect(reload).toHaveBeenCalledTimes(1);
  });
});
