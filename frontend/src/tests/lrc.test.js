import { describe, it, expect } from 'vitest';
import { parseLrc, lineAt } from '../lib/utils/lrc.js';

describe('LRC', () => {
  it('liest Zeiten mit zwei und drei Nachkommastellen richtig', () => {
    const lines = parseLrc('[ar:ABBA]\n[00:01.50] Eins\n[00:02.250] Zwei\n[01:00] Drei');
    expect(lines).toEqual([{ time: 1.5, text: 'Eins' }, { time: 2.25, text: 'Zwei' }, { time: 60, text: 'Drei' }]);
  });
  it('findet die laufende Zeile, mit Versatz', () => {
    const lines = parseLrc('[00:01.00] A\n[00:05.00] B');
    expect(lineAt(lines, 0.5)).toBe(-1);
    expect(lineAt(lines, 3)).toBe(0);
    expect(lineAt(lines, 5.2)).toBe(1);
    expect(lineAt(lines, 5.2, 0.5)).toBe(0);
  });
});
