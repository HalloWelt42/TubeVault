<!--
  TubeVault – SearchDropdown v1.5.98
  Zentrale Suche: Lokal, RSS, YouTube, Favoriten, Playlists.
  URL-Erkennung: YouTube-URLs → Downloads-Seite mit Auto-Resolve.
  © HalloWelt42 – Private Nutzung
-->
<script>
  import { api } from '../../api/client.js';
  import { navigate } from '../../router/router.js';
  import { pendingDownloadUrl } from '../../stores/app.js';
  import { toast } from '../../stores/notifications.js';
  import { formatDuration, formatViews } from '../../utils/format.js';
  import StreamDialog from '../common/StreamDialog.svelte';
  import LikeBar from '../common/LikeBar.svelte';
  import QuickPlaylistBtn from '../common/QuickPlaylistBtn.svelte';

  let query = $state('');
  let open = $state(false);
  let focused = $state(false);

  // Ergebnisse
  let localResults = $state([]);
  let rssResults = $state([]);
  let ytResults = $state([]);
  let ytPlaylists = $state([]);
  let ytChannels = $state([]);
  let favResults = $state([]);
  let plResults = $state([]);
  let ownResults = $state([]);

  // Loading states
  let loadingLocal = $state(false);
  let loadingRss = $state(false);
  let loadingYt = $state(false);
  let searched = $state(false);
  let ytSearched = $state(false);

  // Actions
  let downloading = $state(new Set());
  let subscribing = $state(new Set());
  let subscribedChannels = $state(new Set());

  // Suchverlauf
  let history = $state(loadHistory());
  let showHistory = $state(false);

  // Filter-Badges (persistent)
  let scopes = $state(loadScopes());

  // Debounce
  let debounceTimer = null;

  // StreamDialog
  let streamDialog = $state(null);

  // Refs
  let dropdownRef = $state(null);
  let inputRef = $state(null);

  const MAX_PER_SECTION = 5;

  // ═══ Scope-Filter ═══
  const scopeDefs = [
    { id: 'local', label: 'Lokal', icon: 'fa-solid fa-hard-drive', color: 'var(--status-success)' },
    { id: 'rss', label: 'RSS', icon: 'fa-solid fa-satellite-dish', color: '#3b82f6' },
    { id: 'youtube', label: 'YouTube', icon: 'fa-brands fa-youtube', color: '#cc0000' },
    { id: 'favorites', label: 'Favoriten', icon: 'fa-solid fa-heart', color: '#ef4444' },
    { id: 'playlists', label: 'Playlists', icon: 'fa-solid fa-list-ul', color: '#8b5cf6' },
    { id: 'own', label: 'Eigene', icon: 'fa-solid fa-film', color: '#f59e0b' },
  ];

  function loadScopes() {
    try {
      const s = JSON.parse(localStorage.getItem('tv_search_scopes'));
      if (s && typeof s === 'object') return s;
    } catch {}
    return { local: true, rss: true, youtube: true, favorites: false, playlists: false, own: true };
  }
  function saveScopes() { localStorage.setItem('tv_search_scopes', JSON.stringify(scopes)); }
  function toggleScope(id) {
    const active = Object.entries(scopes).filter(([, v]) => v).length;
    if (active === 1 && scopes[id]) return; // mindestens 1
    scopes = { ...scopes, [id]: !scopes[id] };
    saveScopes();
    if (query.trim().length >= 2) runSearch();
  }

  // ═══ Suchverlauf ═══
  function loadHistory() {
    try { return JSON.parse(localStorage.getItem('tv_search_history') || '[]'); } catch { return []; }
  }
  function saveHistory(h) { localStorage.setItem('tv_search_history', JSON.stringify(h)); history = h; }
  function addToHistory(q) {
    const f = history.filter(h => h.query !== q);
    saveHistory([{ query: q, date: new Date().toISOString() }, ...f].slice(0, 20));
  }
  function removeFromHistory(q) { saveHistory(history.filter(h => h.query !== q)); }
  function clearHistory() { saveHistory([]); }

  // ═══ Suche ═══
  function onInput() {
    clearTimeout(debounceTimer);
    const q = query.trim();
    if (q.length < 2) {
      localResults = []; rssResults = []; favResults = []; plResults = []; ownResults = [];
      searched = false;
      showHistory = q.length === 0;
      return;
    }
    showHistory = false;
    debounceTimer = setTimeout(() => runSearch(), 300);
  }

  async function runSearch() {
    const q = query.trim();
    if (q.length < 2) return;
    searched = true;
    open = true;
    showHistory = false;

    const promises = [];

    // Lokal
    if (scopes.local) {
      loadingLocal = true;
      promises.push(
        api.searchLocal(q, { per_page: MAX_PER_SECTION + 1 })
          .then(r => { localResults = (r.videos || []).filter(v => v.status === 'ready').slice(0, MAX_PER_SECTION + 1); })
          .catch(() => { localResults = []; })
          .finally(() => { loadingLocal = false; })
      );
    } else { localResults = []; }

    // RSS
    if (scopes.rss) {
      loadingRss = true;
      promises.push(
        api.searchRss(q)
          .then(r => { rssResults = (r.results || []).slice(0, MAX_PER_SECTION + 1); })
          .catch(() => { rssResults = []; })
          .finally(() => { loadingRss = false; })
      );
    } else { rssResults = []; }

    // Favoriten (lokale Suche mit scope)
    if (scopes.favorites) {
      promises.push(
        api.searchLocal(q, { per_page: MAX_PER_SECTION + 1, scope: 'favorites' })
          .then(r => { favResults = (r.videos || []).filter(v => v.status === 'ready').slice(0, MAX_PER_SECTION + 1); })
          .catch(() => { favResults = []; })
      );
    } else { favResults = []; }

    // Playlists (lokale Suche mit scope)
    if (scopes.playlists) {
      promises.push(
        api.getPlaylists()
          .then(pls => {
            const qLower = q.toLowerCase();
            plResults = pls
              .filter(p => p.name?.toLowerCase().includes(qLower) || p.description?.toLowerCase().includes(qLower))
              .slice(0, MAX_PER_SECTION + 1)
              .map(p => ({ ...p, _isPlaylist: true }));
          })
          .catch(() => { plResults = []; })
      );
    } else { plResults = []; }

    // Eigene Videos (Scan-Index: sucht Titel, Dateiname, Ordner, Kanal)
    if (scopes.own) {
      promises.push(
        api.scanIndex({ search: q, per_page: MAX_PER_SECTION + 1 })
          .then(r => { ownResults = (r.items || []).slice(0, MAX_PER_SECTION + 1).map(i => ({ ...i, _isScan: true })); })
          .catch(() => { ownResults = []; })
      );
    } else { ownResults = []; }

    await Promise.allSettled(promises);

    // Deduplizieren: lokale Videos aus RSS entfernen (Scan-Items haben separate IDs)
    const localIds = new Set(localResults.map(v => v.id));
    rssResults = rssResults.filter(v => !localIds.has(v.video_id || v.id));
  }

  async function searchYouTube() {
    const q = query.trim();
    if (!q || !scopes.youtube) return;
    loadingYt = true;
    ytSearched = true;
    open = true;
    showHistory = false;
    addToHistory(q);
    try {
      const res = await api.searchYouTubeFull(q, 10);
      const all = res.videos || [];
      const localIds = new Set(localResults.map(v => v.id));
      const rssIds = new Set(rssResults.map(v => v.video_id || v.id));
      ytResults = all
        .filter(v => !localIds.has(v.id))
        .map(v => ({ ...v, in_rss: rssIds.has(v.id) }))
        .slice(0, MAX_PER_SECTION + 1);
      ytPlaylists = (res.playlists || []).slice(0, 4);
      ytChannels = (res.channels || []).slice(0, 3);
    } catch (e) { toast.error('YouTube-Suche: ' + e.message); }
    loadingYt = false;
  }

  // URL-Erkennung: YouTube-URLs direkt zur Download-Seite weiterleiten
  function isYouTubeUrl(text) {
    return /(?:youtube\.com|youtu\.be)\//.test(text) || /^[a-zA-Z0-9_-]{11}$/.test(text);
  }

  function onKeydown(e) {
    if (e.key === 'Enter') {
      e.preventDefault();
      const q = query.trim();
      // URL erkannt → direkt zur Downloads-Seite mit Auto-Resolve
      if (q.length > 10 && isYouTubeUrl(q)) {
        $pendingDownloadUrl = q;
        navigate('/downloads');
        closeDropdown();
        return;
      }
      if (q.length >= 2) {
        clearTimeout(debounceTimer);
        runSearch();
      }
      if (scopes.youtube) searchYouTube();
    }
    if (e.key === 'Escape') {
      closeDropdown();
      inputRef?.blur();
    }
  }

  function onFocus() {
    focused = true;
    if (query.trim().length >= 2 && searched) {
      open = true;
    } else if (query.trim().length === 0 && history.length > 0) {
      showHistory = true;
      open = true;
    }
  }

  let dropdownClicked = false;

  function onBlur() {
    focused = false;
    setTimeout(() => {
      if (!focused && !dropdownClicked) { open = false; showHistory = false; }
      dropdownClicked = false;
    }, 200);
  }

  // Click-Outside: Dropdown schließen wenn Klick außerhalb sd-wrap
  $effect(() => {
    function handleClickOutside(e) {
      if (open && dropdownRef && !dropdownRef.contains(e.target)) {
        closeDropdown();
        inputRef?.blur();
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  });

  function closeDropdown() {
    open = false;
    showHistory = false;
  }

  function clearSearch() {
    query = '';
    localResults = []; rssResults = []; ytResults = []; ytPlaylists = []; ytChannels = []; favResults = []; plResults = []; ownResults = [];
    searched = false; ytSearched = false;
    closeDropdown();
  }

  // ═══ Actions ═══
  function openVideo(v) {
    const id = v.video_id || v.id;
    navigate(`/watch/${id}`);
    closeDropdown();
  }

  function openChannel(channelId, e) {
    e.stopPropagation();
    if (!channelId) return;
    navigate(`/channel/${channelId}`);
    closeDropdown();
  }

  async function quickDownload(v, e) {
    e.stopPropagation();
    const id = v.video_id || v.id;
    if (downloading.has(id)) return;
    downloading = new Set([...downloading, id]);
    try {
      await api.addDownload({ url: `https://www.youtube.com/watch?v=${id}`, quality: 'best' });
      v.already_in_queue = true;
      ytResults = [...ytResults]; rssResults = [...rssResults];
      toast.success(`Zur Queue hinzugefügt`);
    } catch (e2) { toast.error(e2.message); }
    downloading = new Set([...downloading].filter(x => x !== id));
  }

  async function openStreamDialog(v, e) {
    e.stopPropagation();
    const id = v.video_id || v.id;
    streamDialog = { video: { ...v, id }, loading: true, streams: [], videoStreams: [], audioStreams: [], captions: [], selectedVideoItag: null, selectedAudioItag: null, mergeAudio: true };
    try {
      const info = await api.getVideoInfo(`https://www.youtube.com/watch?v=${id}`);
      const videoStreams = (info.streams || []).filter(s => s.type === 'video').sort((a, b) => (parseInt(b.quality) || 0) - (parseInt(a.quality) || 0));
      const audioStreams = (info.streams || []).filter(s => s.type === 'audio').sort((a, b) => (parseInt(b.quality) || 0) - (parseInt(a.quality) || 0));
      streamDialog = {
        ...streamDialog, streams: info.streams || [], videoStreams, audioStreams,
        captions: info.captions || [], loading: false, alreadyDownloaded: info.already_downloaded,
        selectedVideoItag: videoStreams[0]?.itag || null,
        selectedAudioItag: videoStreams[0]?.is_progressive ? null : (audioStreams[0]?.itag || null),
      };
    } catch (e2) {
      toast.error(`Stream-Info: ${e2.message}`);
      streamDialog = null;
    }
  }

  async function startDownload({ itag = null, audioItag = null, mergeAudio = true, audioOnly = false, priority = 0 } = {}) {
    if (!streamDialog) return;
    const v = streamDialog.video;
    downloading = new Set([...downloading, v.id]);
    try {
      await api.addDownload({ url: `https://www.youtube.com/watch?v=${v.id}`, quality: 'best', audio_only: audioOnly, itag, audio_itag: audioItag, merge_audio: mergeAudio, priority });
      toast.success(priority >= 10 ? 'Sofort-Download gestartet' : 'In Queue gelegt');
      streamDialog = null;
    } catch (e2) { toast.error(e2.message); }
    downloading = new Set([...downloading].filter(id => id !== v.id));
  }

  async function subscribe(v, e) {
    e.stopPropagation();
    const chId = v.channel_id;
    if (!chId || subscribing.has(chId)) return;
    subscribing = new Set([...subscribing, chId]);
    try {
      await api.addSubscription({ channel_id: chId, channel_name: v.channel_name || 'Unbekannt' });
      subscribedChannels = new Set([...subscribedChannels, chId]);
      toast.success(`"${v.channel_name}" abonniert`);
    } catch (e2) {
      if (e2.message?.includes('bereits') || e2.message?.includes('UNIQUE')) {
        subscribedChannels = new Set([...subscribedChannels, chId]);
      } else { toast.error(e2.message); }
    }
    subscribing = new Set([...subscribing].filter(id => id !== chId));
  }

  // Gesamtzahl sichtbare Ergebnisse
  let totalResults = $derived(
    Math.min(localResults.length, MAX_PER_SECTION) +
    Math.min(rssResults.length, MAX_PER_SECTION) +
    Math.min(ytResults.length, MAX_PER_SECTION) +
    ytPlaylists.length + ytChannels.length +
    Math.min(favResults.length, MAX_PER_SECTION) +
    Math.min(plResults.length, MAX_PER_SECTION) +
    Math.min(ownResults.length, MAX_PER_SECTION)
  );

  let hasAnyResults = $derived(searched && totalResults > 0);
  let noResults = $derived(searched && !loadingLocal && !loadingRss && !loadingYt && totalResults === 0);
</script>

<div class="sd-wrap" bind:this={dropdownRef}>
  <!-- Suchleiste -->
  <div class="sd-bar" class:sd-bar-open={open}>
    <i class="fa-solid fa-magnifying-glass sd-icon"></i>
    <input
      bind:this={inputRef}
      type="text"
      class="sd-input"
      placeholder="Videos suchen…"
      bind:value={query}
      oninput={onInput}
      onkeydown={onKeydown}
      onfocus={onFocus}
      onblur={onBlur}
    />
    {#if query}
      <button class="sd-clear" title="Leeren" onclick={clearSearch}>
        <i class="fa-solid fa-xmark"></i>
      </button>
    {/if}
    <button class="sd-yt-btn" onclick={searchYouTube} disabled={loadingYt || !query.trim() || !scopes.youtube}
      title="YouTube durchsuchen (Enter)">
      {#if loadingYt}<i class="fa-solid fa-spinner fa-spin"></i>{:else}<i class="fa-brands fa-youtube"></i>{/if}
      <span class="sd-yt-label">YouTube</span>
    </button>
  </div>

  <!-- Dropdown -->
  {#if open}
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="sd-dropdown" onmousedown={() => { dropdownClicked = true; }}>
      <!-- Filter-Badges -->
      <div class="sd-filters">
        {#each scopeDefs as s}
          <button class="sd-badge" class:active={scopes[s.id]} onclick={() => toggleScope(s.id)}
            style="--badge-color: {s.color}">
            <i class={s.icon}></i>
            <span>{s.label}</span>
          </button>
        {/each}
      </div>

      <!-- Suchverlauf -->
      {#if showHistory && history.length > 0 && !searched}
        <div class="sd-history">
          <div class="sd-history-head">
            <span>Suchverlauf</span>
            <button onclick={clearHistory}><i class="fa-solid fa-trash-can"></i></button>
          </div>
          {#each history.slice(0, 10) as h}
            <div class="sd-history-item">
              <button class="sd-history-query" onclick={() => { query = h.query; onInput(); if (scopes.youtube) searchYouTube(); }}>
                <i class="fa-solid fa-clock-rotate-left"></i> {h.query}
              </button>
              <button class="sd-history-rm" onclick={() => removeFromHistory(h.query)}>
                <i class="fa-solid fa-xmark"></i>
              </button>
            </div>
          {/each}
        </div>
      {/if}

      <!-- Ergebnisse -->
      {#if searched}
        <!-- Hints -->
        {#if !ytSearched && scopes.youtube && query.trim().length >= 2}
          <div class="sd-yt-hint">
            <i class="fa-solid fa-arrow-turn-down fa-rotate-90"></i> Enter für YouTube-Suche
          </div>
        {/if}

        <!-- Bibliothek -->
        {#if scopes.local && (localResults.length > 0 || loadingLocal)}
          <div class="sd-section">
            <div class="sd-sec-head">
              <span class="sd-sec-dot" style="background: var(--status-success)"></span>
              <span class="sd-sec-label">Bibliothek</span>
              <span class="sd-sec-count">{localResults.length > MAX_PER_SECTION ? `${MAX_PER_SECTION}+` : localResults.length}</span>
              {#if loadingLocal}<i class="fa-solid fa-spinner fa-spin sd-spin"></i>{/if}
            </div>
            {#each localResults.slice(0, MAX_PER_SECTION) as v (v.id)}
              <button class="sd-row" onclick={() => openVideo(v)}>
                <div class="sd-thumb">
                  <img src={api.thumbnailUrl(v.id)} alt="" loading="lazy" onerror={(e) => e.target.style.display='none'} />
                  {#if v.duration}<span class="sd-dur">{formatDuration(v.duration)}</span>{/if}
                  <span class="sd-src-dot" style="background: var(--status-success)" title="Lokal"></span>
                  {#if v.like_count && v.dislike_count != null}<LikeBar likes={v.like_count} dislikes={v.dislike_count} mode="thumbnail" />{/if}
                </div>
                <div class="sd-info">
                  <span class="sd-title">{v.title}</span>
                  <span class="sd-channel">{v.channel_name || '–'}</span>
                </div>
                <div class="sd-acts">
                  <span class="sd-act-btn play" title="Abspielen"><i class="fa-solid fa-play"></i></span>
                </div>
              </button>
            {/each}
          </div>
        {/if}

        <!-- Favoriten -->
        {#if scopes.favorites && favResults.length > 0}
          <div class="sd-section">
            <div class="sd-sec-head">
              <span class="sd-sec-dot" style="background: #ef4444"></span>
              <span class="sd-sec-label">Favoriten</span>
              <span class="sd-sec-count">{favResults.length > MAX_PER_SECTION ? `${MAX_PER_SECTION}+` : favResults.length}</span>
            </div>
            {#each favResults.slice(0, MAX_PER_SECTION) as v (v.id)}
              <button class="sd-row" onclick={() => openVideo(v)}>
                <div class="sd-thumb">
                  <img src={api.thumbnailUrl(v.id)} alt="" loading="lazy" onerror={(e) => e.target.style.display='none'} />
                  {#if v.duration}<span class="sd-dur">{formatDuration(v.duration)}</span>{/if}
                  <span class="sd-src-dot" style="background: #ef4444" title="Favorit"></span>
                  {#if v.like_count && v.dislike_count != null}<LikeBar likes={v.like_count} dislikes={v.dislike_count} mode="thumbnail" />{/if}
                </div>
                <div class="sd-info">
                  <span class="sd-title">{v.title}</span>
                  <span class="sd-channel">{v.channel_name || '–'}</span>
                </div>
                <div class="sd-acts">
                  <span class="sd-act-btn play" title="Abspielen"><i class="fa-solid fa-play"></i></span>
                </div>
              </button>
            {/each}
          </div>
        {/if}

        <!-- Playlists -->
        {#if scopes.playlists && plResults.length > 0}
          <div class="sd-section">
            <div class="sd-sec-head">
              <span class="sd-sec-dot" style="background: #8b5cf6"></span>
              <span class="sd-sec-label">Playlists</span>
              <span class="sd-sec-count">{plResults.length > MAX_PER_SECTION ? `${MAX_PER_SECTION}+` : plResults.length}</span>
            </div>
            {#each plResults.slice(0, MAX_PER_SECTION) as pl (pl.id)}
              <button class="sd-row" onclick={() => { navigate('/playlists', { open: pl.id }); closeDropdown(); }}>
                <div class="sd-thumb sd-thumb-pl">
                  {#if pl.cover_video_id}
                    <img src={api.thumbnailUrl(pl.cover_video_id)} alt="" loading="lazy" onerror={(e) => e.target.style.display='none'} />
                  {:else}
                    <i class="fa-solid fa-list-ul sd-thumb-icon"></i>
                  {/if}
                  <span class="sd-src-dot" style="background: #8b5cf6" title="Playlist"></span>
                </div>
                <div class="sd-info">
                  <span class="sd-title">{pl.name}</span>
                  <span class="sd-channel">{pl.video_count || 0} Videos{pl.description ? ` · ${pl.description}` : ''}</span>
                </div>
                <div class="sd-acts">
                  <span class="sd-act-btn play" title="Öffnen"><i class="fa-solid fa-arrow-right"></i></span>
                </div>
              </button>
            {/each}
          </div>
        {/if}

        <!-- Eigene Videos (Scan-Index) -->
        {#if scopes.own && ownResults.length > 0}
          <div class="sd-section">
            <div class="sd-sec-head">
              <span class="sd-sec-dot" style="background: #f59e0b"></span>
              <span class="sd-sec-label">Eigene Videos</span>
              <span class="sd-sec-count">{ownResults.length > MAX_PER_SECTION ? `${MAX_PER_SECTION}+` : ownResults.length}</span>
            </div>
            {#each ownResults.slice(0, MAX_PER_SECTION) as v (v.id)}
              <button class="sd-row" onclick={() => { navigate('/own-videos', { search: query.trim() }); closeDropdown(); }}>
                <div class="sd-thumb">
                  {#if v.has_thumb}
                    <img src={api.scanThumbUrl(v.id)} alt="" loading="lazy" onerror={(e) => e.target.style.display='none'} />
                  {:else}
                    <div class="sd-thumb-icon"><i class="fa-solid fa-film"></i></div>
                  {/if}
                  {#if v.duration}<span class="sd-dur">{formatDuration(v.duration)}</span>{/if}
                  <span class="sd-src-dot" style="background: #f59e0b" title="Eigenes Video"></span>
                </div>
                <div class="sd-info">
                  <span class="sd-title">{v.title || v.filename}</span>
                  <span class="sd-channel">{v.channel_name || v.folder || '–'}</span>
                </div>
                <div class="sd-acts">
                  <span class="sd-status-badge" class:registered={v.status === 'registered'} class:discovered={v.status === 'discovered'}>{v.status}</span>
                </div>
              </button>
            {/each}
          </div>
        {/if}

        <!-- RSS-Katalog -->
        {#if scopes.rss && (rssResults.length > 0 || loadingRss)}
          <div class="sd-section">
            <div class="sd-sec-head">
              <span class="sd-sec-dot" style="background: #3b82f6"></span>
              <span class="sd-sec-label">RSS-Katalog</span>
              <span class="sd-sec-count">{rssResults.length > MAX_PER_SECTION ? `${MAX_PER_SECTION}+` : rssResults.length}</span>
              {#if loadingRss}<i class="fa-solid fa-spinner fa-spin sd-spin"></i>{/if}
            </div>
            {#each rssResults.slice(0, MAX_PER_SECTION) as v (v.video_id || v.id)}
              <div class="sd-row sd-row-clickable" role="button" tabindex="0"
                onclick={() => { navigate(`/watch/${v.video_id || v.id}`); closeDropdown(); }}
                onkeydown={(e) => e.key === 'Enter' && (navigate(`/watch/${v.video_id || v.id}`), closeDropdown())}>
                <div class="sd-thumb">
                  <img src={api.rssThumbUrl(v.video_id || v.id)} alt="" loading="lazy" onerror={(e) => e.target.style.display='none'} />
                  <span class="sd-src-dot" style="background: #3b82f6" title="RSS"></span>
                </div>
                <div class="sd-info">
                  <span class="sd-title">{v.title}</span>
                  <span class="sd-channel">{v.channel_name || '–'}</span>
                </div>
                <div class="sd-acts" onclick={(e) => e.stopPropagation()}>
                  {#if v.already_in_queue || downloading.has(v.video_id || v.id)}
                    <span class="sd-act-btn queued" title="In Queue"><i class="fa-solid fa-clock"></i></span>
                  {:else}
                    <button class="sd-act-btn dl" title="Herunterladen" onclick={(e) => quickDownload(v, e)}><i class="fa-solid fa-download"></i></button>
                    <button class="sd-act-btn" title="Download-Optionen" onclick={(e) => openStreamDialog(v, e)}><i class="fa-solid fa-sliders"></i></button>
                  {/if}
                </div>
              </div>
            {/each}
          </div>
        {/if}

        <!-- YouTube -->
        {#if scopes.youtube && (ytResults.length > 0 || loadingYt)}
          <div class="sd-section">
            <div class="sd-sec-head">
              <span class="sd-sec-dot" style="background: #cc0000"></span>
              <span class="sd-sec-label">YouTube</span>
              <span class="sd-sec-count">{ytResults.length > MAX_PER_SECTION ? `${MAX_PER_SECTION}+` : ytResults.length}</span>
              {#if loadingYt}<i class="fa-solid fa-spinner fa-spin sd-spin"></i>{/if}
            </div>
            {#each ytResults.slice(0, MAX_PER_SECTION) as v (v.id)}
              <div class="sd-row" class:sd-row-rss={v.in_rss}>
                <div class="sd-thumb">
                  <img src={v.already_downloaded ? api.thumbnailUrl(v.id) : api.rssThumbUrl(v.id)} alt="" loading="lazy" onerror={(e) => e.target.style.display='none'} />
                  {#if v.duration}<span class="sd-dur">{formatDuration(v.duration)}</span>{/if}
                  {#if v.already_downloaded}
                    <span class="sd-src-dot" style="background: var(--status-success)" title="Lokal"></span>
                  {:else if v.in_rss}
                    <span class="sd-src-dot" style="background: #3b82f6" title="In RSS"></span>
                  {:else}
                    <span class="sd-src-dot" style="background: #cc0000" title="YouTube"></span>
                  {/if}
                </div>
                <div class="sd-info">
                  <span class="sd-title">{v.title}</span>
                  <div class="sd-channel-row">
                    <button class="sd-channel-link" onclick={(e) => openChannel(v.channel_id, e)}>{v.channel_name || '–'}</button>
                    {#if v.channel_id && !subscribedChannels.has(v.channel_id)}
                      <button class="sd-sub-btn" onclick={(e) => subscribe(v, e)} disabled={subscribing.has(v.channel_id)}>
                        <i class="fa-solid fa-rss"></i>
                      </button>
                    {:else if subscribedChannels.has(v.channel_id)}
                      <i class="fa-solid fa-check sd-sub-ok"></i>
                    {/if}
                  </div>
                  {#if v.view_count}<span class="sd-meta">{formatViews(v.view_count)} Aufrufe</span>{/if}
                </div>
                <div class="sd-acts">
                  <QuickPlaylistBtn videoId={v.id} title={v.title} channelName={v.channel_name} channelId={v.channel_id} size="sm" />
                  {#if v.already_downloaded}
                    <button class="sd-act-btn play" title="Abspielen" onclick={() => openVideo(v)}><i class="fa-solid fa-play"></i></button>
                  {:else if v.already_in_queue || downloading.has(v.id)}
                    <span class="sd-act-btn queued" title="In Queue"><i class="fa-solid fa-clock"></i></span>
                  {:else}
                    <button class="sd-act-btn dl" title="Herunterladen" onclick={(e) => quickDownload(v, e)}><i class="fa-solid fa-download"></i></button>
                    <button class="sd-act-btn" title="Download-Optionen" onclick={(e) => openStreamDialog(v, e)}><i class="fa-solid fa-sliders"></i></button>
                  {/if}
                </div>
              </div>
            {/each}
          </div>
        {/if}

        <!-- YouTube Playlists -->
        {#if scopes.youtube && ytPlaylists.length > 0}
          <div class="sd-section">
            <div class="sd-sec-head">
              <span class="sd-sec-dot" style="background: #cc0000"></span>
              <span class="sd-sec-label">YT Playlists</span>
              <span class="sd-sec-count">{ytPlaylists.length}</span>
            </div>
            {#each ytPlaylists as p (p.id)}
              <div class="sd-row sd-row-compact">
                <div class="sd-thumb sd-thumb-pl">
                  <i class="fa-solid fa-list-ul"></i>
                </div>
                <div class="sd-info">
                  <span class="sd-title">{p.title}</span>
                  <span class="sd-meta">{p.owner || '–'}{p.video_count ? ` · ${p.video_count} Videos` : ''}</span>
                </div>
                <div class="sd-acts">
                  <button class="sd-act-btn dl" title="Im Download-Bereich öffnen"
                    onclick={() => { $pendingDownloadUrl = p.url; navigate('/downloads'); closeDropdown(); }}>
                    <i class="fa-solid fa-arrow-right"></i>
                  </button>
                </div>
              </div>
            {/each}
          </div>
        {/if}

        <!-- YouTube Kanäle -->
        {#if scopes.youtube && ytChannels.length > 0}
          <div class="sd-section">
            <div class="sd-sec-head">
              <span class="sd-sec-dot" style="background: #cc0000"></span>
              <span class="sd-sec-label">YT Kanäle</span>
              <span class="sd-sec-count">{ytChannels.length}</span>
            </div>
            {#each ytChannels as c (c.id)}
              <div class="sd-row sd-row-compact">
                <div class="sd-thumb sd-thumb-ch">
                  <i class="fa-solid fa-user"></i>
                </div>
                <div class="sd-info">
                  <span class="sd-title">{c.name}</span>
                  <span class="sd-meta">{c.id}</span>
                </div>
                <div class="sd-acts">
                  <button class="sd-act-btn" title="Kanal öffnen" onclick={(e) => openChannel(c.id, e)}>
                    <i class="fa-solid fa-arrow-right"></i>
                  </button>
                </div>
              </div>
            {/each}
          </div>
        {/if}

        <!-- Keine Ergebnisse -->
        {#if noResults}
          <div class="sd-empty">
            <i class="fa-solid fa-search"></i>
            <span>Keine Treffer für „{query}"</span>
          </div>
        {/if}
      {/if}
    </div>
  {/if}
</div>

<StreamDialog
  dialog={streamDialog ? { ...streamDialog, title: streamDialog.video?.title } : null}
  showAudioOnly={true}
  ondownload={({ itag, audioItag, mergeAudio, audioOnly, priority }) => startDownload({ itag, audioItag, mergeAudio, audioOnly, priority })}
  onclose={() => streamDialog = null}
/>

<style>
  .sd-wrap { position: relative; flex: 1; max-width: 600px; margin: 0 auto; }

  /* Suchleiste */
  .sd-bar {
    display: flex; align-items: center; gap: 8px;
    background: var(--bg-tertiary); border: 1px solid var(--border-primary);
    border-radius: 24px; padding: 5px 6px 5px 14px; transition: all 0.2s;
  }
  .sd-bar:focus-within { border-color: var(--accent-primary); }
  .sd-bar-open { border-radius: 14px 14px 0 0; border-bottom-color: transparent; }
  .sd-icon { color: var(--text-tertiary); flex-shrink: 0; font-size: 0.85rem; }
  .sd-input {
    flex: 1; background: none; border: none; color: var(--text-primary);
    font-size: 0.88rem; outline: none; min-width: 0;
  }
  .sd-input::placeholder { color: var(--text-tertiary); }
  .sd-clear {
    background: none; border: none; color: var(--text-tertiary);
    cursor: pointer; font-size: 0.78rem; padding: 4px;
  }
  .sd-clear:hover { color: var(--text-primary); }

  /* YouTube-Button */
  .sd-yt-btn {
    display: flex; align-items: center; gap: 5px;
    padding: 6px 14px; background: #cc0000; color: #fff; border: none;
    border-radius: 20px; font-size: 0.78rem; font-weight: 600; cursor: pointer;
    white-space: nowrap; flex-shrink: 0; transition: background 0.15s;
  }
  .sd-yt-btn:disabled { opacity: 0.35; cursor: default; }
  .sd-yt-btn:hover:not(:disabled) { background: #aa0000; }
  .sd-yt-label { display: none; }
  @media (min-width: 640px) { .sd-yt-label { display: inline; } }

  /* Dropdown */
  .sd-dropdown {
    position: absolute; top: 100%; left: 0; right: 0; z-index: 200;
    background: var(--bg-secondary); border: 1px solid var(--border-primary);
    border-top: none; border-radius: 0 0 14px 14px;
    box-shadow: 0 12px 40px rgba(0,0,0,0.25);
    max-height: 70vh; overflow-y: auto;
    scrollbar-width: thin;
  }

  /* Filter-Badges */
  .sd-filters {
    display: flex; gap: 4px; padding: 8px 12px; border-bottom: 1px solid var(--border-primary);
    flex-wrap: wrap;
  }
  .sd-badge {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 3px 10px; border-radius: 12px; font-size: 0.7rem; font-weight: 600;
    border: 1px solid var(--border-primary); background: var(--bg-tertiary);
    color: var(--text-tertiary); cursor: pointer; transition: all 0.15s;
  }
  .sd-badge i { font-size: 0.65rem; }
  .sd-badge.active {
    background: color-mix(in srgb, var(--badge-color) 15%, transparent);
    border-color: var(--badge-color);
    color: var(--badge-color);
  }
  .sd-badge:hover { border-color: var(--badge-color); }

  /* YT-Hint */
  .sd-yt-hint {
    text-align: center; padding: 6px; font-size: 0.72rem;
    color: var(--text-tertiary); display: flex; align-items: center;
    justify-content: center; gap: 6px;
  }

  /* Suchverlauf */
  .sd-history { padding: 4px 0; }
  .sd-history-head {
    display: flex; justify-content: space-between; align-items: center;
    padding: 4px 14px; font-size: 0.68rem; color: var(--text-tertiary);
    text-transform: uppercase; font-weight: 600; letter-spacing: 0.04em;
  }
  .sd-history-head button {
    background: none; border: none; color: var(--text-tertiary);
    cursor: pointer; font-size: 0.68rem;
  }
  .sd-history-head button:hover { color: var(--status-error); }
  .sd-history-item { display: flex; align-items: center; }
  .sd-history-query {
    flex: 1; background: none; border: none; color: var(--text-primary);
    padding: 7px 14px; text-align: left; cursor: pointer; font-size: 0.82rem;
    display: flex; align-items: center; gap: 10px;
  }
  .sd-history-query i { color: var(--text-tertiary); font-size: 0.72rem; }
  .sd-history-query:hover { background: var(--bg-hover); }
  .sd-history-rm {
    background: none; border: none; color: var(--text-tertiary);
    padding: 7px 10px; cursor: pointer; font-size: 0.7rem;
  }
  .sd-history-rm:hover { color: var(--status-error); }

  /* Sektionen */
  .sd-section { padding: 4px 0; border-bottom: 1px solid var(--border-primary); }
  .sd-section:last-child { border-bottom: none; }
  .sd-sec-head {
    display: flex; align-items: center; gap: 6px;
    padding: 6px 14px 2px; font-size: 0.72rem; font-weight: 600;
    color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.03em;
  }
  .sd-sec-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
  .sd-sec-count {
    margin-left: auto; font-size: 0.65rem; padding: 0 6px;
    background: var(--bg-tertiary); border-radius: 8px;
  }
  .sd-spin { font-size: 0.7rem; color: var(--text-tertiary); }

  /* Ergebnis-Zeile */
  .sd-row {
    display: flex; align-items: center; gap: 10px;
    padding: 6px 12px; cursor: pointer; transition: background 0.1s;
    border: none; background: none; width: 100%; text-align: left; color: inherit;
  }
  .sd-row:hover { background: var(--bg-hover); }
  .sd-row-rss { border-left: 2px solid #3b82f6; }

  /* Thumbnail */
  .sd-thumb {
    position: relative; width: 96px; min-width: 96px; aspect-ratio: 16/9;
    border-radius: 6px; overflow: hidden; background: var(--bg-tertiary); flex-shrink: 0;
  }
  .sd-thumb img { width: 100%; height: 100%; object-fit: cover; }
  .sd-thumb-icon { display: flex; align-items: center; justify-content: center; width: 100%; height: 100%; color: var(--text-tertiary); font-size: 1.2rem; }
  .sd-dur {
    position: absolute; bottom: 2px; right: 2px; background: rgba(0,0,0,0.8);
    color: #fff; font-size: 0.6rem; padding: 0 4px; border-radius: 2px; font-weight: 500;
  }
  .sd-src-dot {
    position: absolute; top: 3px; left: 3px; width: 7px; height: 7px;
    border-radius: 50%; border: 1px solid rgba(0,0,0,0.3);
  }

  /* Info */
  .sd-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
  .sd-title {
    font-size: 0.8rem; font-weight: 600; color: var(--text-primary);
    display: -webkit-box; -webkit-line-clamp: 1; -webkit-box-orient: vertical; overflow: hidden;
  }
  .sd-channel { font-size: 0.72rem; color: var(--text-tertiary); }
  .sd-channel-row { display: flex; align-items: center; gap: 4px; }
  .sd-channel-link {
    background: none; border: none; color: var(--text-tertiary); font-size: 0.72rem;
    cursor: pointer; padding: 0;
  }
  .sd-channel-link:hover { color: var(--accent-primary); }
  .sd-meta { font-size: 0.65rem; color: var(--text-tertiary); }
  .sd-sub-btn {
    background: none; border: 1px solid var(--border-primary); color: var(--text-tertiary);
    border-radius: 3px; padding: 0 4px; font-size: 0.58rem; cursor: pointer;
  }
  .sd-sub-btn:hover { border-color: var(--accent-primary); color: var(--accent-primary); }
  .sd-sub-ok { color: var(--status-success); font-size: 0.62rem; }

  /* Action-Buttons */
  .sd-acts { display: flex; gap: 4px; flex-shrink: 0; align-items: center; }
  .sd-act-btn {
    width: 30px; height: 30px; border-radius: 6px; border: 1px solid var(--border-primary);
    background: var(--bg-tertiary); cursor: pointer; font-size: 0.78rem;
    display: flex; align-items: center; justify-content: center;
    color: var(--text-secondary); transition: all 0.12s;
  }
  .sd-act-btn:hover { border-color: var(--accent-primary); color: var(--accent-primary); }
  .sd-act-btn.play { color: var(--status-success); }
  .sd-act-btn.play:hover { border-color: var(--status-success); }
  .sd-act-btn.dl { color: var(--accent-primary); }
  .sd-act-btn.queued { color: var(--text-tertiary); cursor: default; opacity: 0.5; }

  /* Empty */
  .sd-empty {
    display: flex; align-items: center; justify-content: center; gap: 8px;
    padding: 20px; color: var(--text-tertiary); font-size: 0.82rem;
  }
  .sd-empty i { font-size: 1rem; opacity: 0.5; }

  /* Playlist/Channel compact rows */
  .sd-row-compact { min-height: 36px; }
  .sd-thumb-pl, .sd-thumb-ch {
    display: flex; align-items: center; justify-content: center;
    background: var(--bg-tertiary); color: var(--text-tertiary); font-size: 0.8rem;
  }
  .sd-thumb-pl { background: rgba(204, 0, 0, 0.08); color: #cc0000; }
  .sd-thumb-ch { background: rgba(59, 130, 246, 0.08); color: #3b82f6; }

  /* Scan status badge */
  .sd-status-badge { font-size:0.58rem; font-weight:600; padding:1px 5px; border-radius:3px; background:var(--bg-tertiary); color:var(--text-tertiary); text-transform:uppercase; white-space:nowrap; }
  .sd-status-badge.registered { background:rgba(34,197,94,0.15); color:var(--status-success); }
  .sd-status-badge.discovered { background:rgba(59,130,246,0.15); color:var(--status-info); }
</style>
