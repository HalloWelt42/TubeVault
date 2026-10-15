import { describe, it, expect } from 'vitest';
import {
  languageChoices, languageInfo, languageLabel, mainLanguage, parseLanguageList, sourceLabel,
} from '../lib/utils/language.js';
import { filterChannels } from '../lib/components/channel/channelView.js';

// Ausschnitt des Katalogs, wie ihn GET /api/languages liefert
const catalog = {
  languages: [
    { code: 'de', name: 'Deutsch', flag: '🇩🇪' },
    { code: 'en', name: 'Englisch', flag: '🇬🇧' },
    { code: 'eu', name: 'Baskisch', flag: null },
  ],
  sources: [
    { key: 'hand', label: 'von Hand', rank: 5 },
    { key: 'quelle', label: 'Angabe beim Laden', rank: 4 },
    { key: 'text', label: 'erkannt aus Titel und Beschreibung', rank: 2 },
  ],
  unknown: { code: 'und', name: 'Unbekannt', flag: null },
  mixed: { code: 'mul', name: 'Gemischt', flag: null },
};

describe('Sprach-Labels', () => {
  it('zeigt kein Label für die Hauptsprache und für Unbekanntes', () => {
    expect(languageLabel(catalog, 'de', 'quelle', 'de')).toBeNull();
    expect(languageLabel(catalog, null, null, 'de')).toBeNull();
    expect(languageLabel(catalog, 'und', null, 'de')).toBeNull();
  });

  it('zeigt Flagge, Kürzel und Herkunft im Tooltip', () => {
    expect(languageLabel(catalog, 'en', 'quelle', 'de'))
      .toEqual({ code: 'en', short: 'EN', flag: '🇬🇧', mixed: false, title: 'Englisch (Quelle: Angabe beim Laden)' });
    expect(languageLabel(catalog, 'de', 'text', 'en').title).toBe('Deutsch (Quelle: erkannt aus Titel und Beschreibung)');
    expect(languageLabel(catalog, 'eu', null, 'de')).toMatchObject({ short: 'EU', flag: null, title: 'Baskisch' });
  });

  it('Kanäle: Mehrheit der Videos oder gemischt', () => {
    expect(languageLabel(catalog, 'en', null, 'de', true).title).toBe('Englisch: Sprache der meisten Videos');
    expect(languageLabel(catalog, 'mul', null, 'de', true)).toMatchObject({ short: 'gemischt', mixed: true });
  });

  it('Hauptsprache aus den Einstellungen, sonst Deutsch', () => {
    expect(mainLanguage({ 'language.main': 'en' })).toBe('en');
    expect(mainLanguage({})).toBe('de');
    expect(mainLanguage(null)).toBe('de');
  });

  it('Namen auch ohne geladenen Katalog', () => {
    expect(languageInfo(null, 'fr')).toEqual({ code: 'fr', name: 'FR', flag: null });
    expect(languageInfo(catalog, 'und').name).toBe('Unbekannt');
    expect(sourceLabel(catalog, 'hand')).toBe('von Hand');
    expect(sourceLabel(catalog, 'gibtsnicht')).toBeNull();
  });
});

describe('Sprachfilter', () => {
  it('Auswahl aus den Zählern, gewählte ohne Treffer bleiben sichtbar', () => {
    const counts = [{ code: 'de', count: 120 }, { code: 'en', count: 30 }, { code: 'und', count: 4 }];
    expect(languageChoices(catalog, counts, ['fr']).map((c) => `${c.name} ${c.count}`))
      .toEqual(['Deutsch 120', 'Englisch 30', 'Unbekannt 4', 'FR 0']);
    expect(parseLanguageList('en, de,,')).toEqual(['en', 'de']);
    expect(parseLanguageList(null)).toEqual([]);
  });

  it('filtert Kanäle nach ihrer Sprache', () => {
    const subs = [
      { id: 1, channel_id: 'UCa', channel_name: 'A', language: 'de' },
      { id: 2, channel_id: 'UCb', channel_name: 'B', language: 'en' },
      { id: 3, channel_id: 'UCc', channel_name: 'C', language: 'mul' },
      { id: 4, channel_id: 'UCd', channel_name: 'D', language: null },
    ];
    expect(filterChannels(subs, { languages: ['en', 'mul'] }).map((s) => s.id)).toEqual([2, 3]);
    expect(filterChannels(subs, { languages: ['und'] }).map((s) => s.id)).toEqual([4]);
    expect(filterChannels(subs, {}).length).toBe(4);
  });
});
