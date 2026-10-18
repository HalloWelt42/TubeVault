// Handy-Ansicht oder volle Ansicht: die volle Ansicht gilt nur bis Tab oder
// App schließen, der Rückweg führt an dieselbe Stelle (utils/mobileView.js).
import { describe, it, expect, beforeEach } from 'vitest';
import html from '../../index.html?raw';
import { FULL_VIEW_FLAG, PHONE_QUERY, mobilePath, openFullView, openMobileView } from '../lib/utils/mobileView.js';

beforeEach(() => {
  sessionStorage.clear();
  window.location.href = 'http://localhost:8032/';
  window.location.pathname = '/';
});

describe('Rückweg zur Handy-Ansicht', () => {
  it('führt ein Video zum selben Video, alles andere zum Start', () => {
    expect(mobilePath('/watch/dQw4w9WgXcQ')).toBe('/m/video/dQw4w9WgXcQ');
    expect(mobilePath('/music')).toBe('/m/');
    expect(mobilePath('/')).toBe('/m/');
  });

  it('merkt die volle Ansicht nur für diese Sitzung', () => {
    openFullView();
    expect(sessionStorage.getItem(FULL_VIEW_FLAG)).toBe('1');
    expect(localStorage.getItem(FULL_VIEW_FLAG)).toBeNull();
    expect(window.location.href).toBe('/');
  });

  it('vergisst die Wahl beim Wechsel zurück', () => {
    sessionStorage.setItem(FULL_VIEW_FLAG, '1');
    window.location.pathname = '/watch/abcdefghijk';
    openMobileView();
    expect(sessionStorage.getItem(FULL_VIEW_FLAG)).toBeNull();
    expect(window.location.href).toBe('/m/video/abcdefghijk');
  });

  it('die frühe Weiterleitung in index.html nennt Merkmal und Abfrage gleich und befreit alte Wahl', () => {
    expect(html).toContain(`sessionStorage.getItem('${FULL_VIEW_FLAG}')`);
    expect(html).toContain(`localStorage.removeItem('${FULL_VIEW_FLAG}')`);
    expect(html).toContain(`window.matchMedia('${PHONE_QUERY}')`);
    expect(html).not.toContain(`localStorage.getItem('${FULL_VIEW_FLAG}')`);
  });
});
