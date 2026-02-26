<!--
  TubeVault – VideoSuggestion v1.8.76
  Zeigt zufällige Video-Empfehlung in der Sidebar wenn kein Mini-Player aktiv.
  Ein Cycle-Toggle schaltet durch die Pools: Alle → Bibliothek → Musik → Eigene → Archiv.
  © HalloWelt42 – Private Nutzung
-->
<script>
  import { api } from '../../api/client.js';
  import { navigate } from '../../router/router.js';
  import { formatDuration } from '../../utils/format.js';
  import { onDestroy } from 'svelte';

  const POOLS = [
    { key: 'all',     label: 'Alle',       icon: 'fa-solid fa-shuffle' },
    { key: 'library', label: 'Bibliothek', icon: 'fa-solid fa-book' },
    { key: 'music',   label: 'Musik',      icon: 'fa-solid fa-music' },
    { key: 'own',     label: 'Eigene',     icon: 'fa-solid fa-film' },
    { key: 'archive', label: 'Archiv',     icon: 'fa-solid fa-box-archive' },
  ];

  let poolIndex = $state(0);
  let suggestion = $state(null);
  let loading = $state(false);

  // Timer als plain variable, NICHT $state (kein Svelte-Tracking nötig)
  let rotateTimer = null;

  async function loadSuggestion() {
    loading = true;
    try {
      const pool = POOLS[poolIndex].key;
      const data = await api.getRandomVideo(null, pool);
      if (data && data.id) {
        suggestion = data;
      } else {
        suggestion = null;
      }
    } catch (err) {
      console.warn('[VideoSuggestion] Fehler:', err);
      suggestion = null;
    }
    loading = false;
  }

  function cyclePool() {
    poolIndex = (poolIndex + 1) % POOLS.length;
    loadSuggestion();
  }

  function nextSuggestion() {
    loadSuggestion();
  }

  function openVideo() {
    if (suggestion) navigate(`/watch/${suggestion.id}`);
  }

  // Init: sofort laden + Rotation
  loadSuggestion();
  rotateTimer = setInterval(loadSuggestion, 120000);
  onDestroy(() => { if (rotateTimer) clearInterval(rotateTimer); });
</script>

<div class="video-suggestion">
  <!-- Header: Pool-Toggle + Shuffle -->
  <div class="vs-header">
    <button class="vs-pool-btn" onclick={cyclePool} title="Quelle wechseln">
      <i class={POOLS[poolIndex].icon}></i>
      <span>{POOLS[poolIndex].label}</span>
      <i class="fa-solid fa-caret-down vs-caret"></i>
    </button>
    <button class="vs-shuffle" onclick={nextSuggestion} title="Nächster Vorschlag">
      <i class="fa-solid fa-rotate-right"></i>
    </button>
  </div>

  <!-- Video -->
  {#if suggestion}
    <button class="vs-card" onclick={openVideo}>
      <div class="vs-thumb">
        <img
          src={api.thumbnailUrl(suggestion.id)}
          alt=""
          loading="lazy"
          onerror={(e) => e.target.style.display = 'none'}
        />
        {#if suggestion.duration}
          <span class="vs-duration">{formatDuration(suggestion.duration)}</span>
        {/if}
        <div class="vs-play-overlay">
          <i class="fa-solid fa-play"></i>
        </div>
      </div>
      <div class="vs-info">
        <span class="vs-title">{suggestion.title || suggestion.id}</span>
        {#if suggestion.channel_name}
          <span class="vs-channel">{suggestion.channel_name}</span>
        {/if}
      </div>
    </button>
  {:else if !loading}
    <div class="vs-empty">Keine Videos in diesem Pool</div>
  {/if}
</div>

<style>
  .video-suggestion {
    margin: 0 4px;
    border-radius: 8px;
    overflow: hidden;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-primary);
  }

  .vs-header {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 5px 8px 4px;
  }

  .vs-pool-btn {
    display: flex;
    align-items: center;
    gap: 5px;
    padding: 2px 7px;
    border-radius: 4px;
    border: 1px solid var(--accent-primary);
    background: var(--accent-muted);
    color: var(--accent-primary);
    cursor: pointer;
    font-size: 0.62rem;
    font-weight: 600;
    transition: all 0.12s;
  }
  .vs-pool-btn i { font-size: 0.6rem; }
  .vs-caret { font-size: 0.5rem !important; opacity: 0.5; margin-left: 1px; }
  .vs-pool-btn:hover {
    background: var(--accent-primary);
    color: #fff;
  }

  .vs-shuffle {
    margin-left: auto;
    background: none;
    border: none;
    color: var(--text-tertiary);
    cursor: pointer;
    font-size: 0.7rem;
    padding: 2px 5px;
    border-radius: 4px;
    transition: all 0.12s;
  }
  .vs-shuffle:hover {
    color: var(--accent-primary);
    background: var(--bg-hover);
  }

  .vs-card {
    display: block;
    width: 100%;
    background: none;
    border: none;
    cursor: pointer;
    text-align: left;
    padding: 0;
  }
  .vs-card:hover .vs-title { color: var(--accent-primary); }
  .vs-card:hover .vs-play-overlay { opacity: 1; }

  .vs-thumb {
    position: relative;
    width: 100%;
    aspect-ratio: 16 / 9;
    background: #000;
    overflow: hidden;
  }
  .vs-thumb img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .vs-duration {
    position: absolute;
    bottom: 3px;
    right: 3px;
    background: rgba(0,0,0,0.8);
    color: #fff;
    font-size: 0.58rem;
    padding: 1px 4px;
    border-radius: 3px;
    font-variant-numeric: tabular-nums;
  }

  .vs-play-overlay {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(0,0,0,0.3);
    opacity: 0;
    transition: opacity 0.15s;
  }
  .vs-play-overlay i {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    background: var(--accent-primary);
    color: #fff;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.65rem;
    box-shadow: 0 2px 10px rgba(0,0,0,0.4);
  }

  .vs-info {
    padding: 4px 8px 6px;
  }
  .vs-title {
    display: block;
    font-size: 0.68rem;
    font-weight: 600;
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    transition: color 0.15s;
  }
  .vs-channel {
    display: block;
    font-size: 0.58rem;
    color: var(--text-tertiary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .vs-empty {
    padding: 16px 8px;
    text-align: center;
    font-size: 0.62rem;
    color: var(--text-tertiary);
  }
</style>
