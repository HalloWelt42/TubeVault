/**
 * TubeVault – videoListFilters v1.0.0
 *
 * DER zentrale Filter-Zustand für Video-Listen (Bibliothek, Archiv).
 * Vorher hielt jede Seite Sortierung, Tags und Mehrfachfilter selbst und
 * glich sie an drei Stellen ab (URL, localStorage, Filterleiste). Folge:
 * gespeicherte Filter wirkten weiter, ohne dass die Filterleiste sie zeigte -
 * die Liste war still gekürzt.
 *
 * Regeln (eine Wahrheit):
 *   1. Start: Stehen Filter in der URL (Verweis, z.B. Tag-Klick), gelten NUR
 *      diese. Sonst gilt die zuletzt gespeicherte Auswahl der Seite.
 *   2. Danach ist dieser Zustand die Wahrheit; URL und Speicher werden bei
 *      jeder Änderung nachgezogen (persist()).
 *   3. Die Filterleiste bekommt den Startzustand über `multi` und zeigt damit
 *      immer genau das an, was die Liste filtert.
 *
 * Nutzung:
 *   const filters = createVideoListFilters('archives');
 *   $effect(() => { filters.signature; filters.persist(); list.load(true); });
 *   api.getVideos({ page, ...filters.apiParams() })
 */
import { get } from 'svelte/store';
import { route, updateParams } from '../router/router.js';
import { getFilter, saveFilters } from '../stores/filterPersist.js';

const DEFAULT_SORT = 'upload_date';
const DEFAULT_ORDER = 'desc';
const EMPTY_MULTI = { types: null, channels: null, categories: null, search: null, is_music: null, extra_audio: null };

/** URL-Parameter, die einen Filter tragen (Sortierung zählt nicht als Filter). */
const URL_FILTER_KEYS = ['tags', 'types', 'channels', 'categories', 'q', 'music', 'ton'];

function normalizeMulti(f = {}) {
  return {
    types: f.types || null,
    channels: f.channels || null,
    categories: f.categories || null,
    search: f.search || null,
    is_music: f.is_music || null,
    extra_audio: f.extra_audio || null,
  };
}

function readInitial(routeKey) {
  const p = get(route).params || {};
  const urlHasFilter = URL_FILTER_KEYS.some(k => p[k]);
  const sortBy = p.sort || getFilter(routeKey, 'sortBy', DEFAULT_SORT);
  const sortOrder = p.order || getFilter(routeKey, 'sortOrder', DEFAULT_ORDER);
  if (urlHasFilter) {
    return {
      sortBy, sortOrder,
      activeTags: p.tags ? p.tags.split(',').filter(Boolean) : [],
      multi: normalizeMulti({
        types: p.types, channels: p.channels, categories: p.categories,
        search: p.q, is_music: p.music === '1', extra_audio: p.ton === '1',
      }),
    };
  }
  return {
    sortBy, sortOrder,
    activeTags: getFilter(routeKey, 'activeTags', []),
    multi: normalizeMulti(getFilter(routeKey, 'multiFilter', EMPTY_MULTI)),
  };
}

export function createVideoListFilters(routeKey) {
  const initial = readInitial(routeKey);

  let sortBy = $state(initial.sortBy);
  let sortOrder = $state(initial.sortOrder);
  let activeTags = $state(initial.activeTags);
  let multi = $state(initial.multi);

  const signature = $derived(JSON.stringify([sortBy, sortOrder, activeTags, multi]));
  const hasActive = $derived(
    activeTags.length > 0 || !!(multi.types || multi.channels || multi.categories || multi.search || multi.is_music || multi.extra_audio)
  );

  function toggleTag(tag) {
    activeTags = activeTags.includes(tag) ? activeTags.filter(t => t !== tag) : [...activeTags, tag];
  }

  function changeSort(field) {
    if (sortBy === field) sortOrder = sortOrder === 'desc' ? 'asc' : 'desc';
    else { sortBy = field; sortOrder = 'desc'; }
  }

  /** Auswahl in Speicher und URL nachziehen. */
  function persist() {
    saveFilters(routeKey, { sortBy, sortOrder, activeTags: [...activeTags], multiFilter: { ...multi } });
    updateParams({
      sort: sortBy !== DEFAULT_SORT ? sortBy : null,
      order: sortOrder !== DEFAULT_ORDER ? sortOrder : null,
      tags: activeTags.length > 0 ? activeTags.join(',') : null,
      types: multi.types,
      channels: multi.channels,
      categories: multi.categories,
      q: multi.search,
      music: multi.is_music ? '1' : null,
      ton: multi.extra_audio ? '1' : null,
    });
  }

  /** Filter-Teil der Abfrage für /api/videos (ohne Seite und Archiv-Kennzeichen). */
  function apiParams() {
    const params = { sort_by: sortBy, sort_order: sortOrder };
    if (activeTags.length > 0) params.tags = activeTags.join(',');
    if (multi.types) params.video_types = multi.types;
    if (multi.channels) params.channel_ids = multi.channels;
    if (multi.categories) params.category_ids = multi.categories;
    if (multi.search) params.search = multi.search;
    if (multi.is_music) params.is_music = true;
    if (multi.extra_audio) params.has_extra_audio = true;
    return params;
  }

  /** Filter-Teil für /api/videos/tags (Tag-Leiste passend zur Liste). */
  function tagParams() {
    return {
      video_types: multi.types || undefined,
      channel_ids: multi.channels || undefined,
      category_ids: multi.categories || undefined,
    };
  }

  return {
    get sortBy() { return sortBy; },
    get sortOrder() { return sortOrder; },
    get activeTags() { return activeTags; },
    get multi() { return multi; },
    get signature() { return signature; },
    get hasActive() { return hasActive; },
    setMulti(f) { multi = normalizeMulti(f); },
    clearTags() { activeTags = []; },
    toggleTag,
    changeSort,
    persist,
    apiParams,
    tagParams,
  };
}
