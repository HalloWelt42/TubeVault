<!--
  Gemerkte Suchen in der Übersicht: was seit dem letzten Öffnen neu dazukam.
  Erscheint nur, wenn etwas gemerkt ist.
-->
<script>
  import { onMount } from 'svelte';
  import { api } from '../../api/client.js';
  import OverviewSection from './OverviewSection.svelte';
  import SavedSearchList from '../search/SavedSearchList.svelte';

  let items = $state([]);

  async function load() {
    try { items = await api.savedSearches(); } catch { items = []; }
  }

  onMount(load);
</script>

{#if items.length}
  <OverviewSection title="Gemerkte Suchen" more={{ label: 'Zur Suche', path: '/search' }}>
    <SavedSearchList {items} onchange={load} />
  </OverviewSection>
{/if}
