/**
 * Live-Log im Browser (lib/utils/frontendLog, stores/liveLog).
 *
 * Kontrakt:
 * - Werte werden sicher zu Text: Fehler mit Name und Meldung, Kreisbezüge
 *   und große Ganzzahlen ohne Absturz - der Mitschnitt wirft nie.
 * - Gesendet wird gebündelt (höchstens 50 je Anfrage), bis nichts mehr ansteht.
 * - Das Terminal beginnt nach einem Neustart des Backends neu, statt alles
 *   mit kleinerer Nummer zu verwerfen, und meldet Lücken.
 */
import { describe as suite, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { describe as text, report } from '../lib/utils/frontendLog.js';
import { liveLog } from '../lib/stores/liveLog.svelte.js';

suite('frontendLog', () => {
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

  it('macht aus allem sicher Text', () => {
    const loop = { name: 'a' };
    loop.self = loop;
    expect(text(new TypeError('kaputt'))).toBe('TypeError: kaputt');
    expect(text(loop)).toBe('{"name":"a","self":"[Kreisbezug]"}');
    expect(text({ zahl: 10n })).toBe('{"zahl":"10n"}');
    expect(text(undefined)).toBe('undefined');
  });

  it('sendet gebündelt, bis nichts mehr ansteht', async () => {
    vi.useFakeTimers();
    const bodies = [];
    vi.stubGlobal('fetch', vi.fn(async (url, options) => { bodies.push(JSON.parse(options.body)); return { ok: true }; }));
    for (let i = 0; i < 120; i++) report('WARNING', 'test', [`Meldung ${i}`]);
    await vi.advanceTimersByTimeAsync(2500);
    expect(bodies.map((body) => body.length)).toEqual([50, 50, 20]);
    expect(bodies[0][0]).toEqual({ level: 'WARNING', source: 'test', msg: 'Meldung 0' });
  });
});

class FakeSocket {
  static last = null;
  constructor(url) { this.url = url; FakeSocket.last = this; }
  close() { this.onclose?.(); }
  send() {}
  frame(data) { this.onmessage?.({ data: JSON.stringify(data) }); }
}

suite('liveLog', () => {
  beforeEach(() => { vi.stubGlobal('WebSocket', FakeSocket); liveLog.clear(); });
  afterEach(() => { liveLog.close(); vi.unstubAllGlobals(); });

  const entry = (seq, msg = `m${seq}`) => ({ seq, msg, level: 'INFO', ts: '10:00:00', epoch: 1_790_000_000 + seq });

  it('beginnt nach einem Neustart des Backends neu', () => {
    liveLog.open();
    FakeSocket.last.frame({ boot: 'eins', entries: [entry(4999), entry(5000)], gap: 0 });
    FakeSocket.last.close();                                   // Backend startet neu
    vi.useFakeTimers();
    liveLog.open();
    expect(FakeSocket.last.url).toContain('boot=eins&after=5000');
    FakeSocket.last.frame({ boot: 'zwei', entries: [entry(1, 'nach dem Neustart')], gap: 0, restarted: true });
    vi.useRealTimers();
    expect(liveLog.entries.map((e) => e.msg)).toEqual(['m4999', 'm5000', 'Backend neu gestartet', 'nach dem Neustart']);
    // seq beginnt neu bei 1 - die Schlüssel der Anzeige müssen trotzdem eindeutig bleiben
    const keys = liveLog.entries.map((e) => e.key);
    expect(new Set(keys).size).toBe(keys.length);
  });

  it('meldet Lücken und verwirft Doppeltes', () => {
    liveLog.open();
    FakeSocket.last.frame({ boot: 'b', entries: [entry(1), entry(2)], gap: 0 });
    FakeSocket.last.frame({ boot: 'b', entries: [entry(2), entry(40)], gap: 37 });
    expect(liveLog.entries.map((e) => e.msg)).toEqual(['m1', 'm2', expect.stringContaining('37 Einträge'), 'm40']);
  });

  it('hält während der Pause zurück und zeigt danach alles', () => {
    liveLog.open();
    liveLog.togglePause();
    FakeSocket.last.frame({ boot: 'c', entries: [entry(1), entry(2)], gap: 0 });
    expect(liveLog.entries).toEqual([]);
    expect(liveLog.held).toBe(2);
    liveLog.togglePause();
    expect(liveLog.entries.map((e) => e.msg)).toEqual(['m1', 'm2']);
  });
});
