<!--
  TubeVault – Admin-Hauptseite v1.0.0
  Eigener Bereich für Datenmanagement, Sync-Jobs, System-Inspektion.
  Fullsize-Layout (kein max-width). Kein Login, aber eigene Menü-Gruppe.
-->
<script>
  import { navigate } from '../lib/router/router.js';

  const cards = [
    {
      title: 'Textexport',
      desc: 'Beschreibungen, Kapitel, Tags aus der DB in Dateien auslagern. DB wird Referenz-Index, Dateien bleiben als dauerhaftes Backup erhalten.',
      icon: 'fa-solid fa-file-lines',
      path: '/admin/texts',
      ready: true,
    },
    {
      title: 'Wiederaufbau',
      desc: 'Meta-Redundanz neben den Videos: info.json-Sidecars, täglicher Nutzerdaten-Export, kompletter Offline-Wiederaufbau der Datenbank aus Dateien.',
      icon: 'fa-solid fa-life-ring',
      path: '/admin/rebuild',
      ready: true,
    },
    {
      title: 'DB-Inspektor',
      desc: 'Rohe DB-Abfragen, Schema-Version, Tabellengrößen. (geplant)',
      icon: 'fa-solid fa-database',
      path: null,
      ready: false,
    },
    {
      title: 'Job-Monitor',
      desc: 'Laufende Hintergrund-Jobs, Queue-Tiefe, Retry-Verlauf. (geplant)',
      icon: 'fa-solid fa-list-check',
      path: null,
      ready: false,
    },
    {
      title: 'Dateisystem',
      desc: 'Video-Files, Thumbnails, Waisen, Speicherplatz pro Kanal. (geplant)',
      icon: 'fa-solid fa-folder-tree',
      path: null,
      ready: false,
    },
  ];
</script>

<div class="admin-page">
  <header class="admin-header">
    <div>
      <h1><i class="fa-solid fa-screwdriver-wrench"></i> Admin</h1>
      <p class="subtitle">Datenmanagement, Inspektion, manuelle Jobs</p>
    </div>
  </header>

  <div class="admin-grid">
    {#each cards as card}
      <button
        class="admin-card"
        class:disabled={!card.ready}
        disabled={!card.ready}
        onclick={() => card.path && navigate(card.path)}
      >
        <div class="card-icon"><i class={card.icon}></i></div>
        <div class="card-body">
          <h3>{card.title}</h3>
          <p>{card.desc}</p>
        </div>
        {#if !card.ready}
          <span class="card-coming">bald</span>
        {:else}
          <i class="fa-solid fa-arrow-right card-arrow"></i>
        {/if}
      </button>
    {/each}
  </div>
</div>

<style>
  .admin-page { padding: 32px 40px; width: 100%; }
  .admin-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 28px; }
  .admin-header h1 { margin: 0; font-size: 1.8rem; color: var(--text-primary); display: flex; align-items: center; gap: 14px; }
  .admin-header h1 i { color: var(--accent-primary); }
  .subtitle { margin: 6px 0 0; color: var(--text-tertiary); font-size: 0.92rem; }

  .admin-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 16px; }

  .admin-card {
    display: flex; align-items: flex-start; gap: 16px;
    padding: 20px; text-align: left; cursor: pointer;
    background: var(--bg-secondary);
    border: 1px solid var(--border-primary);
    border-radius: 14px;
    transition: all 0.15s;
    color: inherit;
  }
  .admin-card:hover:not(:disabled) {
    border-color: var(--accent-primary);
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(0,0,0,0.2);
  }
  .admin-card.disabled { opacity: 0.55; cursor: not-allowed; }

  .card-icon {
    width: 44px; height: 44px; border-radius: 10px;
    background: var(--accent-muted);
    display: flex; align-items: center; justify-content: center;
    color: var(--accent-primary); font-size: 1.2rem;
    flex-shrink: 0;
  }
  .card-body { flex: 1; min-width: 0; }
  .card-body h3 { margin: 0 0 6px; font-size: 1rem; color: var(--text-primary); }
  .card-body p { margin: 0; font-size: 0.85rem; color: var(--text-secondary); line-height: 1.45; }

  .card-arrow { color: var(--text-tertiary); align-self: center; }
  .card-coming {
    font-size: 0.7rem; color: var(--text-tertiary);
    padding: 3px 8px; border-radius: 5px;
    background: var(--bg-tertiary); align-self: flex-start;
  }
</style>
