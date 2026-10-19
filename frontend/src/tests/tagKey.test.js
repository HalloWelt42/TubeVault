// Schlagwörter in der Oberfläche: Schreibweise egal wie beim Server
// (utils/tagKey.js, Server: video_tags.search_key).
import { describe, it, expect, beforeEach } from 'vitest';
import { sameTag, tagKey } from '../lib/utils/tagKey.js';
import { createVideoListFilters } from '../lib/utils/videoListFilters.svelte.js';

describe('Schlüssel eines Schlagworts', () => {
  it('ohne Groß und Klein, Leerraum einfach, gleiche Unicode-Form', () => {
    expect(tagKey('  Einfach   Erklärt ')).toBe('einfach erklärt');
    expect(tagKey('Körper')).toBe(tagKey('Körper'));
    expect(tagKey('ТЕХНО')).toBe('техно');
    expect(sameTag('Straße', 'STRASSE')).toBe(true);
    expect(sameTag('100%', '100')).toBe(false);
  });
});

describe('Schlagwort wählen', () => {
  beforeEach(() => { localStorage.clear(); window.history.replaceState({}, '', '/library'); });

  it('nimmt eine andere Schreibweise als dasselbe Schlagwort', () => {
    const filters = createVideoListFilters('schlagworttest');
    filters.toggleTag('Körper');
    filters.toggleTag('körper');
    expect(filters.activeTags).toEqual([]);
    filters.toggleTag('Körper');
    filters.toggleTag('техно');
    expect(filters.activeTags).toEqual(['Körper', 'техно']);
    expect(filters.apiParams().tags).toBe('Körper,техно');
  });

  it('zählt die Schlagwörter mit denselben Filtern wie die Liste', () => {
    const filters = createVideoListFilters('schlagworttest2');
    filters.setMulti({ search: 'brot', is_music: true, extra_audio: true, types: 'video' });
    expect(filters.tagParams()).toMatchObject({ search: 'brot', is_music: true, has_extra_audio: true, video_types: 'video' });
  });
});

describe('Schlagwort aus der Beschreibung', () => {
  it('macht Hashtags jeder Schrift klickbar', async () => {
    const { formatDescription } = await import('../lib/utils/description.js');
    const html = formatDescription('Mehr unter #Körper und #техно');
    expect(html).toContain('data-tag="Körper"');
    expect(html).toContain('data-tag="техно"');
  });
});
