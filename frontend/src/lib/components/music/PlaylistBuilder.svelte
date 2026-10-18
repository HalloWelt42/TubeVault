<!--
  Listen-Baukasten der Musik (Rechner): links alle Titel (TrackPool), rechts
  die gewählte Wiedergabeliste. Titel von links an jede Stelle der Liste
  ziehen, in der Liste per Ziehen umordnen, mit x herausnehmen; eine neue
  Liste entsteht mit einem Namen und Eingabetaste und ist sofort gewählt.
  Abspielen geht jederzeit, ganz oder je Titel (Cover oder Titel: spielt die
  Liste ab dort, beim laufenden Titel anhalten und fortsetzen). Videos und Dateien der Sammlung mischen sich
  (backend/app/services/playlist_items.py). Die gewählte Liste steht in der
  Adresse (?liste=).
-->
<script>
  import { onMount } from 'svelte';
  import { get } from 'svelte/store';
  import { api } from '../../api/client.js';
  import { formatDuration, formatDurationLong } from '../../utils/format.js';
  import { route, updateParams } from '../../router/router.js';
  import { carriesTracks, draggedTracks, dropIndex, moveTarget } from '../../utils/trackDrag.js';
  import { isRemoved, onMusicChange } from '../../utils/musicChanges.js';
  import { musicPlayer as player } from '../../stores/musicPlayer.svelte.js';
  import { toast } from '../../stores/notifications.js';
  import TrackPool from './TrackPool.svelte';
  import CoverPlay from './CoverPlay.svelte';
  import ConfirmDialog from '../common/ConfirmDialog.svelte';

  let lists = $state([]);
  let chosenId = $state(get(route).params?.liste || null);
  let current = $state(null);          // { source, title, tracks }
  let newName = $state('');
  let dropAt = $state(null);           // Ablagestelle beim Ziehen
  let movingFrom = $state(null);       // Zeile, die gerade innerhalb der Liste wandert
  let confirm;

  let key = $derived(chosenId ? `playlist:${chosenId}` : null);
  let inList = $derived(new Set(current?.tracks.map((t) => t.id) || []));
  let duration = $derived((current?.tracks || []).reduce((sum, t) => sum + (t.duration || 0), 0));

  async function loadLists() {
    try { lists = await api.musicPlaylists(); } catch (e) { toast.error(e.message); }
  }

  async function loadCurrent() {
    if (!key) { current = null; return; }
    const wanted = key;
    try {
      const list = await api.musicPlay(wanted);
      if (wanted === key) current = list;
    } catch (e) {
      toast.error(e.message);
      choose(null);
    }
  }

  function choose(id) {
    chosenId = id ? String(id) : null;
    updateParams({ liste: chosenId });
    loadCurrent();
  }

  async function create(e) {
    e.preventDefault();
    const name = newName.trim();
    if (!name) return;
    try {
      const group = await api.musicCreatePlaylist(name);
      newName = '';
      await loadLists();
      choose(group.key.split(':')[1]);
    } catch (err) { toast.error(err.message); }
  }

  async function removeList() {
    if (!current) return;
    const ok = await confirm.ask(`Liste "${current.title}" löschen?`, 'Die Titel selbst bleiben erhalten.');
    if (!ok) return;
    try {
      await api.deletePlaylist(chosenId);
      choose(null);
      await loadLists();
    } catch (e) { toast.error(e.message); }
  }

  // ─── Ändern: sofort sichtbar, dann beim Server; schlägt es fehl, gilt wieder dessen Stand ───
  async function save(tracks, work) {
    const id = chosenId;
    current = { ...current, tracks };
    try {
      await work(id);
      if (id === chosenId) await api.musicOrderPlaylist(id, tracks.map((t) => t.id));
    } catch (e) {
      toast.error(e.message);
      await loadCurrent();
    }
    loadLists();
  }

  function add(tracks, at = current.tracks.length) {
    const fresh = tracks.filter((t) => !inList.has(t.id));
    if (!fresh.length) return toast.info(tracks.length === 1 ? 'Steht schon in der Liste' : 'Stehen schon in der Liste');
    const next = [...current.tracks];
    next.splice(at, 0, ...fresh);
    save(next, (id) => api.musicAddToPlaylist(id, fresh.map((t) => t.id)));
  }

  function move(from, at) {
    const to = moveTarget(from, at);
    if (to === from) return;
    const next = [...current.tracks];
    next.splice(to, 0, ...next.splice(from, 1));
    save(next, async () => {});
  }

  function remove(track) {
    save(current.tracks.filter((t) => t.id !== track.id), (id) => api.musicRemoveFromPlaylist(id, track.id));
  }

  // ─── Ziehen und Ablegen ───
  const accepts = (e) => movingFrom !== null || carriesTracks(e);

  function overRow(e, index) {
    if (!accepts(e)) return;
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = movingFrom !== null ? 'move' : 'copy';
    dropAt = dropIndex(e, index);
  }

  function overList(e) {
    if (!accepts(e)) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = movingFrom !== null ? 'move' : 'copy';
    dropAt = current.tracks.length;
  }

  function leaveList(e) {
    if (!e.currentTarget.contains(e.relatedTarget)) dropAt = null;
  }

  function drop(e) {
    if (!accepts(e)) return;
    e.preventDefault();
    const at = dropAt ?? current.tracks.length;
    if (movingFrom !== null) move(movingFrom, at);
    else add(draggedTracks(e), at);
    dropAt = null;
    movingFrom = null;
  }

  function startMove(e, index) {
    movingFrom = index;
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', current.tracks[index].title);
  }

  const play = (options = {}) => player.playSource(key, options).catch((e) => toast.error(e.message));
  // Ein Titel der Liste: läuft er schon, anhalten bzw. fortsetzen, sonst die Liste ab ihm
  const playTrack = (track) => (player.current?.id === track.id ? player.toggle() : play({ start: track.id }));

  onMount(() => {
    loadLists();
    loadCurrent();
    return onMusicChange((change) => {
      const gone = isRemoved(change);
      if (current) current = { ...current, tracks: current.tracks.filter((t) => !gone(t)) };
      if (change.reload) { loadLists(); if (change.restored || change.playlist === key) loadCurrent(); }
    });
  });
</script>

<div class="baukasten">
  <TrackPool {inList} canAdd={!!current} onAdd={(tracks) => add(tracks)} />

  <section class="ziel">
    <div class="wahl">
      <form class="neu" onsubmit={create}>
        <input class="tv-eingabe" bind:value={newName} placeholder="Neue Liste: Name, dann Eingabetaste" maxlength="120" />
        <button class="tv-knopf klein" type="submit" disabled={!newName.trim()}><i class="fa-solid fa-plus"></i> Anlegen</button>
      </form>
      {#if lists.length}
        <div class="listen" role="listbox" aria-label="Wiedergabelisten">
          {#each lists as list (list.key)}
            {@const id = list.key.split(':')[1]}
            <button role="option" aria-selected={chosenId === id} class:an={chosenId === id} onclick={() => choose(id)}>
              <i class="fa-solid fa-list-ul"></i> {list.name}<span class="zahl">{list.count}</span></button>
          {/each}
        </div>
      {/if}
    </div>

    {#if current}
      <div class="listenkopf">
        <div class="name">
          <h2>{current.title}</h2>
          <span class="tv-leise tv-klein zahl">{current.tracks.length} Titel · {formatDurationLong(duration)}</span>
        </div>
        <button class="tv-knopf haupt klein" onclick={() => play()} disabled={!current.tracks.length}><i class="fa-solid fa-play"></i> Abspielen</button>
        <button class="tv-knopf klein" onclick={() => play({ shuffle: true })} disabled={!current.tracks.length}><i class="fa-solid fa-shuffle"></i> Zufällig</button>
        <button class="tv-knopf ohne klein" onclick={removeList} title="Liste löschen (die Titel bleiben)"><i class="fa-solid fa-trash-can"></i></button>
      </div>

      <div class="ablage" class:zieht={dropAt !== null} data-scroll-root role="list"
           ondragover={overList} ondragleave={leaveList} ondrop={drop}>
        {#each current.tracks as track, i (track.id)}
          {#if dropAt === i}<div class="marke" aria-hidden="true"></div>{/if}
          <div class="zeile" class:wandert={movingFrom === i} class:laeuft={player.current?.id === track.id} role="listitem"
               draggable="true" ondragstart={(e) => startMove(e, i)} ondragend={() => { movingFrom = null; dropAt = null; }}
               ondragover={(e) => overRow(e, i)}>
            <span class="nr zahl">{i + 1}</span>
            <span class="spielen">
              <CoverPlay {track} onplay={() => play({ start: track.id })} />
              <button class="text" onclick={() => playTrack(track)} title="Ab hier abspielen">
                <span class="t">{track.title}</span><span class="w">{track.artist}</span></button>
            </span>
            <span class="zahl dauer">{formatDuration(track.duration || 0)}</span>
            <button class="weg" onclick={() => remove(track)} title="Aus der Liste nehmen"><i class="fa-solid fa-xmark"></i></button>
          </div>
        {/each}
        {#if dropAt === current.tracks.length && current.tracks.length}<div class="marke" aria-hidden="true"></div>{/if}
        {#if !current.tracks.length}
          <div class="leer"><i class="fa-solid fa-arrow-left"></i> Titel von links hierher ziehen, doppelt klicken oder + drücken.</div>
        {/if}
      </div>
    {:else}
      <div class="tv-leer">Rechts oben eine Liste wählen oder mit einem Namen neu anlegen, dann Titel von links hineinziehen.</div>
    {/if}
  </section>
</div>

<ConfirmDialog bind:this={confirm} />

<style>
  .baukasten { height: 100%; min-height: 0; display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: var(--tv-a5); }
  .ziel { min-height: 0; display: flex; flex-direction: column; gap: var(--tv-a3); }
  .wahl { flex: none; display: flex; flex-direction: column; gap: var(--tv-a2); }
  .neu { display: flex; gap: var(--tv-a2); }
  .neu input { flex: 1; min-width: 0; }
  .listen { display: flex; flex-wrap: wrap; gap: 6px; max-height: 120px; overflow-y: auto; }
  .listen button { display: inline-flex; align-items: center; gap: 6px; height: 32px; padding: 0 10px; border: 1px solid var(--tv-rand);
                   border-radius: var(--tv-ecke); background: var(--tv-flaeche); color: var(--tv-text-2); font: inherit;
                   font-size: var(--tv-gr-klein); cursor: pointer; }
  .listen button:hover { color: var(--tv-text); border-color: var(--tv-rand-stark); }
  .listen button.an { color: var(--tv-akzent); border-color: rgba(var(--tv-akzent-rgb), 0.55); background: rgba(var(--tv-akzent-rgb), 0.12); }
  .listen .zahl { color: var(--tv-text-3); font-size: var(--tv-gr-marke); }
  .listenkopf { flex: none; display: flex; align-items: center; gap: var(--tv-a2); flex-wrap: wrap; }
  .name { flex: 1 1 100%; min-width: 0; display: flex; align-items: baseline; gap: var(--tv-a3); }
  .name h2 { min-width: 0; margin: 0; font-size: var(--tv-gr-titel); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .name span { flex: none; }
  .ablage { flex: 1; min-height: 120px; overflow-y: auto; padding: var(--tv-a2); border-radius: var(--tv-ecke);
            background: var(--tv-mulde); outline: 2px dashed transparent; outline-offset: -2px; }
  .ablage.zieht { outline-color: rgba(var(--tv-akzent-rgb), 0.5); }
  .zeile { display: grid; grid-template-columns: 28px minmax(0, 1fr) auto 32px; gap: var(--tv-a2); align-items: center;
           padding: 4px 6px; border-radius: var(--tv-ecke); cursor: grab; }
  .zeile:hover { background: var(--tv-flaeche); }
  .zeile.wandert { opacity: 0.4; }
  .zeile.laeuft .t { color: var(--tv-akzent); }
  .nr { text-align: right; font-size: var(--tv-gr-klein); color: var(--tv-text-3); }
  .spielen { min-width: 0; display: flex; align-items: center; gap: var(--tv-a2); }
  .text { min-width: 0; display: flex; flex-direction: column; padding: 0; border: 0; background: none; color: var(--tv-text);
          font: inherit; text-align: left; cursor: pointer; }
  .text:focus-visible { outline: 2px solid var(--tv-akzent); outline-offset: 2px; }
  .text > span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .t { font-weight: 600; }
  .w { font-size: var(--tv-gr-klein); color: var(--tv-text-2); }
  .dauer { font-size: var(--tv-gr-klein); color: var(--tv-text-3); }
  .weg { width: 32px; height: 32px; border: 0; border-radius: var(--tv-ecke-klein); background: none; color: var(--tv-text-3); cursor: pointer; }
  .weg:hover { color: var(--tv-gefahr); background: var(--tv-karte-2); }
  .marke { height: 3px; margin: 1px 6px; border-radius: 2px; background: var(--tv-akzent); }
  .leer { padding: var(--tv-a6) var(--tv-a4); text-align: center; color: var(--tv-text-3); }
  @media (max-width: 860px) {
    .baukasten { grid-template-columns: minmax(0, 1fr); grid-template-rows: minmax(0, 1fr) minmax(0, 1fr); }
  }
</style>
