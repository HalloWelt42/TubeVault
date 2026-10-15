// Aktionen an einem Kanal (Abo): die eine Stelle für Kanalübersicht,
// Kanalseite und ihr gemeinsames Seitenblatt (ChannelSettingsSheet).
// Die Seite sagt, wie sie ihren Stand nachzieht:
//   patch(sub, changes)  geänderte Felder in die eigene Anzeige übernehmen
//   reload()             neu laden (nach Prüfung, Drip, Typ-Änderung)
//   confirm(...)         Rückfrage über den ConfirmDialog der Seite
//   removed(sub)         ein Abo ist beendet (Liste kürzen, Seite verlassen)
//   checking             $state-Objekt der Seite: Abo-ID -> Prüfung läuft
import { api } from '../../api/client.js';
import { toast } from '../../stores/notifications.js';
import { channelName, dripCount, num, qualityShort } from './channelView.js';

export const MISSING_BATCH = 5;                  // "5 fehlende laden" im Menü
const REFRESH_SOON_MS = 800;

const onOff = (on) => (on ? 'an' : 'aus');
const watchUrl = (id) => `https://www.youtube.com/watch?v=${id}`;

export function createChannelActions({ patch, reload, confirm, removed = () => {}, checking = {} }) {
  let refreshTimer;

  /** Speichern; scheitert es, bleibt die Anzeige beim alten Wert und der Grund erscheint. */
  async function save(sub, changes) {
    try { await api.updateSubscription(sub.id, changes); }
    catch (e) { toast.error(`${channelName(sub)}: ${e.message}`); return false; }
    patch(sub, changes);
    return true;
  }

  async function change(sub, changes, message) {
    const ok = await save(sub, changes);
    if (ok) toast.info(`${channelName(sub)}: ${message}`);
    return ok;
  }

  async function setDrip(sub, on) {
    const ok = await change(sub, { drip_enabled: on }, on ? `Drip an, ${dripCount(sub)} am Tag` : 'Drip aus');
    if (ok) reload();      // nächster Lauf, Abschluss und Prognose kommen vom Server
  }

  async function setSuggest(sub, included) {
    const ok = await change(sub, { suggest_exclude: !included }, included ? 'wieder in Vorschlägen' : 'aus Vorschlägen ausgeschlossen');
    // Beim Einschließen gelten die Ausnahmen einzelner Videos nicht mehr
    if (ok && included) {
      try { await api.resetSuggestOverrides(sub.id); } catch (e) { toast.error(e.message); }
    }
  }

  async function saveMusic(sub, on) {
    try {
      const result = await api.setMusicChannel(sub.channel_id, on);
      patch(sub, { music_channel: on });
      return result;
    } catch (e) { toast.error(`${channelName(sub)}: ${e.message}`); return null; }
  }

  async function setMusic(sub, on) {
    const result = await saveMusic(sub, on);
    if (!result) return;
    toast.success(on ? `${channelName(sub)}: Musikkanal, ${num(result.changed)} Videos jetzt Musik`
                     : `${channelName(sub)}: kein Musikkanal mehr, ${num(result.changed)} Videos zurückgesetzt`);
  }

  async function setShortExempt(sub, on) {
    try {
      const result = await api.setShortExempt(sub.channel_id, on);
      patch(sub, { short_exempt: on });
      toast.success(on ? `${channelName(sub)}: nie als Short, ${num(result.changed)} Videos umgestellt`
                       : `${channelName(sub)}: Schutz aufgehoben, bestehende Videos bleiben Videos`);
      reload();
    } catch (e) { toast.error(`${channelName(sub)}: ${e.message}`); }
  }

  async function runCheck(sub) {
    if (checking[sub.id]) return null;
    checking[sub.id] = true;
    try { return await api.checkChannelNow(sub.id); }
    catch (e) { toast.error(`${channelName(sub)}: ${e.message}`); return null; }
    finally { checking[sub.id] = false; }
  }

  async function checkNow(sub) {
    const result = await runCheck(sub);
    if (result) {
      toast.success(result.new_videos > 0 ? `${channelName(sub)}: ${num(result.new_videos)} neue Videos` : `${channelName(sub)}: nichts Neues`);
    }
    reload();
  }

  async function scanFully(sub) {
    try {
      await api.fetchAllChannelVideos(sub.channel_id);
      toast.success(`${channelName(sub)}: Scan läuft, Fortschritt in der Aktivitätenleiste`);
    } catch (e) { toast.error(`${channelName(sub)}: ${e.message}`); }
  }

  /** Die nächsten count ladbaren Videos in die Warteschlange; Anzahl oder null. */
  async function queueMissing(sub, count = MISSING_BATCH, videoType = 'video') {
    try {
      const missing = await api.getMissingVideos(sub.channel_id, count, videoType);
      if (!missing.video_ids?.length) { toast.info(`${channelName(sub)}: nichts Ladbares offen`); return 0; }
      const result = await api.addBatchDownload({ urls: missing.video_ids.map(watchUrl) });
      const queued = result.results?.filter((r) => r.status === 'queued').length ?? missing.video_ids.length;
      toast.success(`${channelName(sub)}: ${num(queued)} Videos in die Warteschlange`);
      return queued;
    } catch (e) { toast.error(`${channelName(sub)}: ${e.message}`); return null; }
  }

  /** Abos beenden; mit geladenen Videos fragt der Dialog, ob sie mitgehen. */
  async function removeChannels(list) {
    const deleteVideos = await askRemoval(list);
    if (deleteVideos === null) return 0;
    let count = 0;
    let videos = 0;
    for (const sub of list) {
      try {
        const result = await api.removeSubscription(sub.id, { deleteVideos });
        count++;
        videos += result.videos_deleted || 0;
        removed(sub);
      } catch (e) { toast.error(`${channelName(sub)}: ${e.message}`); }
    }
    if (count) toast.info(removalMessage(list, count, deleteVideos, videos));
    return count;
  }

  /** true = samt Videos, false = nur das Abo, null = abgebrochen. */
  async function askRemoval(list) {
    const one = list.length === 1;
    const what = one ? `Kanal "${channelName(list[0])}"` : `${num(list.length)} Kanäle`;
    const count = list.reduce((sum, s) => sum + (s.downloaded_count || 0), 0);
    if (!count) {
      const ok = await confirm(`${what} entfernen?`, `Zu ${one ? 'diesem Kanal' : 'diesen Kanälen'} sind keine Videos geladen.`,
        { confirmLabel: one ? 'Kanal entfernen' : 'Kanäle entfernen' });
      return ok ? false : null;
    }
    const choice = await confirm(`${what} entfernen?`,
      `Zu ${one ? 'diesem Kanal' : 'diesen Kanälen'} sind ${num(count)} Videos geladen. Sollen sie mit gelöscht werden? `
      + 'Gelöschte Videos sind restlos weg (Dateien, Notizen, Verlauf).',
      { confirmLabel: `${one ? 'Kanal' : 'Kanäle'} und ${num(count)} Videos löschen`, alternativeLabel: one ? 'Nur Kanal entfernen' : 'Nur Kanäle entfernen' });
    if (choice === false) return null;
    return choice === true;
  }

  function removalMessage(list, count, deleteVideos, videos) {
    const channels = `${num(count)} ${count === 1 ? 'Kanal' : 'Kanäle'}`;
    if (list.length === 1) return deleteVideos ? `"${channelName(list[0])}" und ${num(videos)} Videos gelöscht` : `"${channelName(list[0])}" entfernt`;
    return deleteVideos ? `${channels} und ${num(videos)} Videos gelöscht` : `${channels} entfernt`;
  }

  function refreshSoon(ms = REFRESH_SOON_MS) {
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(reload, ms);
  }

  return {
    save, change, saveMusic, runCheck, queueMissing, removeChannels, refreshSoon,
    dispose: () => clearTimeout(refreshTimer),   // beim Verlassen der Seite
    setAuto: (sub, on) => change(sub, { auto_download: on }, `Auto-Download ${onOff(on)}`),
    setDripCount: (sub, count) => change(sub, { drip_count: count }, `Drip ${count} am Tag`),
    setArchive: (sub, on) => change(sub, { drip_auto_archive: on }, on ? 'neue Videos gleich ins Archiv' : 'neue Videos in die Bibliothek'),
    setAudioOnly: (sub, on) => change(sub, { audio_only: on }, on ? 'nur Ton' : 'Video und Ton'),
    setEnabled: (sub, on) => change(sub, { enabled: on }, on ? 'Prüfung an' : 'Prüfung abgeschaltet'),
    setQuality: (sub, value) => change(sub, { download_quality: value || null },
      value ? `Qualität ${qualityShort(value)}` : 'Qualität aus den Einstellungen'),
    setDrip, setSuggest, setMusic, setShortExempt, checkNow, scanFully,
    remove: (sub) => removeChannels([sub]),
  };
}
