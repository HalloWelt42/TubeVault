/**
 * Einem Hintergrundauftrag folgen (lib/utils/followJob).
 *
 * Kontrakt: Zwischenstände melden, am Ende genau einmal den Ausgang; ein
 * nicht mehr lesbarer (aufgeräumter) Auftrag endet mit null statt ewig zu fragen.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { api } from '../lib/api/client.js';
import { followJob } from '../lib/utils/followJob.js';

describe('followJob', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

  it('meldet Zwischenstände und einmal das Ende', async () => {
    const answers = [{ status: 'queued' }, { status: 'active', description: 'Scannt' }, { status: 'done', result: '12 neu' }];
    vi.spyOn(api, 'getJob').mockImplementation(async () => answers.shift() || { status: 'done' });
    const updates = [];
    const ends = [];
    followJob(7, { onUpdate: (job) => updates.push(job.status), onEnd: (job) => ends.push(job) });
    await vi.advanceTimersByTimeAsync(10000);
    expect(updates).toEqual(['queued', 'active']);
    expect(ends).toEqual([{ status: 'done', result: '12 neu' }]);
  });

  it('endet mit null, wenn der Auftrag nicht mehr lesbar ist', async () => {
    vi.spyOn(api, 'getJob').mockRejectedValue(new Error('Job nicht gefunden'));
    const ends = [];
    followJob(8, { onEnd: (job) => ends.push(job) });
    await vi.advanceTimersByTimeAsync(30000);
    expect(ends).toEqual([null]);
  });

  it('abgemeldet fragt nicht weiter', async () => {
    const getJob = vi.spyOn(api, 'getJob').mockResolvedValue({ status: 'active' });
    const stop = followJob(9, { onEnd: () => {} });
    await vi.advanceTimersByTimeAsync(4000);
    stop();
    const calls = getJob.mock.calls.length;
    await vi.advanceTimersByTimeAsync(10000);
    expect(getJob.mock.calls.length).toBe(calls);
  });
});
