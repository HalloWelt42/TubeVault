/**
 * TubeVault -  Format Utilities Tests v1.5.2
 * © HalloWelt42
 */

import { describe, it, expect } from 'vitest';
import {
  formatDuration,
  formatSize,
  formatDate,
  formatDateRelative,
  formatViews,
  truncate,
} from '../lib/utils/format.js';

// ============================================================
// formatDuration
// ============================================================
describe('formatDuration', () => {
  it('gibt 0:00 für null/undefined/0', () => {
    expect(formatDuration(null)).toBe('0:00');
    expect(formatDuration(undefined)).toBe('0:00');
    expect(formatDuration(0)).toBe('0:00');
  });

  it('gibt 0:00 für negative Werte', () => {
    expect(formatDuration(-1)).toBe('0:00');
    expect(formatDuration(-100)).toBe('0:00');
  });

  it('formatiert Sekunden < 60', () => {
    expect(formatDuration(1)).toBe('0:01');
    expect(formatDuration(9)).toBe('0:09');
    expect(formatDuration(30)).toBe('0:30');
    expect(formatDuration(59)).toBe('0:59');
  });

  it('formatiert Minuten', () => {
    expect(formatDuration(60)).toBe('1:00');
    expect(formatDuration(61)).toBe('1:01');
    expect(formatDuration(90)).toBe('1:30');
    expect(formatDuration(600)).toBe('10:00');
    expect(formatDuration(3599)).toBe('59:59');
  });

  it('formatiert Stunden', () => {
    expect(formatDuration(3600)).toBe('1:00:00');
    expect(formatDuration(3661)).toBe('1:01:01');
    expect(formatDuration(7200)).toBe('2:00:00');
    expect(formatDuration(36000)).toBe('10:00:00');
  });

  it('padded Minuten und Sekunden bei Stunden', () => {
    expect(formatDuration(3605)).toBe('1:00:05');
    expect(formatDuration(3660)).toBe('1:01:00');
  });

  // Typische YouTube-Längen
  it('YouTube Shorts (~60s)', () => {
    expect(formatDuration(58)).toBe('0:58');
  });

  it('YouTube Standard (~10min)', () => {
    expect(formatDuration(612)).toBe('10:12');
  });

  it('YouTube Livestream (~3h)', () => {
    expect(formatDuration(10800)).toBe('3:00:00');
  });
});

// ============================================================
// formatSize
// ============================================================
describe('formatSize', () => {
  it('gibt 0 B für null/undefined/0', () => {
    expect(formatSize(null)).toBe('0 B');
    expect(formatSize(undefined)).toBe('0 B');
    expect(formatSize(0)).toBe('0 B');
  });

  it('gibt 0 B für negative Werte', () => {
    expect(formatSize(-1)).toBe('0 B');
  });

  it('formatiert Bytes', () => {
    expect(formatSize(1)).toBe('1.0 B');
    expect(formatSize(512)).toBe('512.0 B');
    expect(formatSize(1023)).toBe('1023.0 B');
  });

  it('formatiert KB', () => {
    expect(formatSize(1024)).toBe('1.0 KB');
    expect(formatSize(1536)).toBe('1.5 KB');
    expect(formatSize(512000)).toBe('500.0 KB');
  });

  it('formatiert MB', () => {
    expect(formatSize(1048576)).toBe('1.0 MB');
    expect(formatSize(52428800)).toBe('50.0 MB');
    expect(formatSize(734003200)).toBe('700.0 MB');
  });

  it('formatiert GB', () => {
    expect(formatSize(1073741824)).toBe('1.0 GB');
    expect(formatSize(5368709120)).toBe('5.0 GB');
  });

  it('formatiert TB', () => {
    expect(formatSize(1099511627776)).toBe('1.0 TB');
    expect(formatSize(4398046511104)).toBe('4.0 TB');
  });

  // Typische Video-Größen
  it('720p Video (~500MB)', () => {
    const result = formatSize(524288000);
    expect(result).toBe('500.0 MB');
  });

  it('4K Video (~5GB)', () => {
    const result = formatSize(5368709120);
    expect(result).toBe('5.0 GB');
  });
});

// ============================================================
// formatDate
// ============================================================
describe('formatDate', () => {
  it('gibt -  für null/undefined', () => {
    expect(formatDate(null)).toBe('–');
    expect(formatDate(undefined)).toBe('–');
    expect(formatDate('')).toBe('–');
  });

  it('formatiert ISO-Datum im de-DE Format', () => {
    const result = formatDate('2025-03-15T10:30:00Z');
    // de-DE: DD.MM.YYYY
    expect(result).toMatch(/15\.03\.2025/);
  });

  it('formatiert verschiedene Datumsformate', () => {
    const result = formatDate('2024-12-25');
    expect(result).toMatch(/25\.12\.2024/);
  });
});

// ============================================================
// formatDateRelative
// ============================================================
describe('formatDateRelative', () => {
  it('gibt -  für null/undefined', () => {
    expect(formatDateRelative(null)).toBe('–');
    expect(formatDateRelative(undefined)).toBe('–');
    expect(formatDateRelative('')).toBe('–');
  });

  it('gerade eben für < 60 Sekunden', () => {
    const now = new Date();
    const recent = new Date(now - 30000).toISOString(); // 30s ago
    expect(formatDateRelative(recent)).toBe('gerade eben');
  });

  it('Minuten für < 1 Stunde', () => {
    const now = new Date();
    const mins = new Date(now - 5 * 60 * 1000).toISOString();
    expect(formatDateRelative(mins)).toMatch(/vor 5 Min\./);
  });

  it('Stunden für < 1 Tag', () => {
    const now = new Date();
    const hours = new Date(now - 3 * 60 * 60 * 1000).toISOString();
    expect(formatDateRelative(hours)).toMatch(/vor 3 Std\./);
  });

  it('Tage für < 1 Woche', () => {
    const now = new Date();
    const days = new Date(now - 2 * 24 * 60 * 60 * 1000).toISOString();
    expect(formatDateRelative(days)).toMatch(/vor 2 Tagen/);
  });

  it('Datum für >= 1 Woche', () => {
    const now = new Date();
    const old = new Date(now - 14 * 24 * 60 * 60 * 1000).toISOString();
    // Sollte formatDate zurückgeben (DD.MM.YYYY)
    expect(formatDateRelative(old)).toMatch(/\d{2}\.\d{2}\.\d{4}/);
  });
});

// ============================================================
// formatViews
// ============================================================
describe('formatViews', () => {
  it('gibt -  für null/undefined/0', () => {
    expect(formatViews(null)).toBe('–');
    expect(formatViews(undefined)).toBe('–');
    expect(formatViews(0)).toBe('–');
  });

  it('gibt exakte Zahl für < 1000', () => {
    expect(formatViews(1)).toBe('1');
    expect(formatViews(42)).toBe('42');
    expect(formatViews(999)).toBe('999');
  });

  it('formatiert K für >= 1000', () => {
    expect(formatViews(1000)).toBe('1.0K');
    expect(formatViews(1500)).toBe('1.5K');
    expect(formatViews(15000)).toBe('15.0K');
    expect(formatViews(999999)).toBe('1000.0K');
  });

  it('formatiert Mio. für >= 1.000.000', () => {
    expect(formatViews(1000000)).toBe('1.0 Mio.');
    expect(formatViews(2500000)).toBe('2.5 Mio.');
    expect(formatViews(150000000)).toBe('150.0 Mio.');
  });

  it('formatiert Mrd. für >= 1.000.000.000', () => {
    expect(formatViews(1000000000)).toBe('1.0 Mrd.');
    expect(formatViews(14000000000)).toBe('14.0 Mrd.');
  });

  // Typische YouTube-Aufrufe
  it('kleines Video (500 Views)', () => {
    expect(formatViews(500)).toBe('500');
  });

  it('virales Video (12M Views)', () => {
    expect(formatViews(12000000)).toBe('12.0 Mio.');
  });

  it('Gangnam Style (~5 Mrd.)', () => {
    expect(formatViews(5000000000)).toBe('5.0 Mrd.');
  });
});

// ============================================================
// truncate
// ============================================================
describe('truncate', () => {
  it('gibt leeren String für null/undefined', () => {
    expect(truncate(null)).toBe('');
    expect(truncate(undefined)).toBe('');
    expect(truncate('')).toBe('');
  });

  it('gibt kurzen Text unverändert zurück', () => {
    expect(truncate('Hello', 100)).toBe('Hello');
    expect(truncate('Test', 10)).toBe('Test');
  });

  it('schneidet bei maxLen ab und fügt … hinzu', () => {
    expect(truncate('Abcdefghij', 5)).toBe('Abcde…');
  });

  it('Standard maxLen ist 100', () => {
    const long = 'x'.repeat(150);
    const result = truncate(long);
    expect(result).toHaveLength(101); // 100 chars + '…'
    expect(result.endsWith('…')).toBe(true);
  });

  it('exakt maxLen wird nicht abgeschnitten', () => {
    const exact = 'x'.repeat(100);
    expect(truncate(exact, 100)).toBe(exact);
  });

  // YouTube Titel
  it('langer YouTube-Titel', () => {
    const title = 'How to Build a Self-Hosted Video Archive with Python and Docker - Complete Tutorial 2025 Edition Part 1';
    const result = truncate(title, 60);
    expect(result).toHaveLength(61);
    expect(result.endsWith('…')).toBe(true);
  });
});
