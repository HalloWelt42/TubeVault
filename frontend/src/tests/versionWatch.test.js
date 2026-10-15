/**
 * TubeVault – Versionswache: wann nach einem Update selbsttätig neu geladen wird
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { writable, get } from 'svelte/store';

vi.mock('../lib/api/client.js', () => ({ FE_VERSION: '1.0.0' }));

const served = (version) => vi.fn(async () => ({ json: async () => ({ version }) }));

async function start({ version, after = 0 }) {
  vi.resetModules();
  vi.stubGlobal('fetch', served(version));
  const watch = await import('../lib/utils/versionWatch.js');
  const reload = vi.spyOn(watch.page, 'reload').mockImplementation(() => {});
  vi.setSystemTime(Date.now() + after);
  const route = writable('/');
  watch.startVersionWatch(route);
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
});
