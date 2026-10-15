// Zustände von Aufträgen (Downloads und Systemaufträge) - eine Stelle für
// Anzeige, Reiter-Zuordnung und erlaubte Aktionen.

export const STATUS = {
  active:     { label: 'Lädt',         css: 'laeuft',  icon: 'fa-download' },
  queued:     { label: 'Wartet',       css: 'wartet',  icon: 'fa-clock' },
  retry_wait: { label: 'Neuer Versuch', css: 'warnung', icon: 'fa-hourglass-half' },
  error:      { label: 'Fehler',       css: 'fehler',  icon: 'fa-triangle-exclamation' },
  parked:     { label: 'Geparkt',      css: 'warnung', icon: 'fa-box-archive' },
  cancelled:  { label: 'Abgebrochen',  css: '',        icon: 'fa-ban' },
  done:       { label: 'Fertig',       css: 'fertig',  icon: 'fa-check' },
};

export function statusOf(status) {
  return STATUS[status] || { label: status, css: '', icon: 'fa-circle' };
}

// Reiter der Downloads-Seite
export const TABS = [
  { id: 'all', label: 'Alle', icon: 'fa-layer-group' },
  { id: 'active', label: 'Läuft', icon: 'fa-circle-play' },
  { id: 'wait', label: 'Wartet', icon: 'fa-hourglass-half' },
  { id: 'done', label: 'Fertig', icon: 'fa-check' },
  { id: 'error', label: 'Fehler', icon: 'fa-triangle-exclamation' },
  { id: 'cancelled', label: 'Abgebrochen', icon: 'fa-ban' },
];

export function matchesTab(item, tab) {
  if (tab === 'all') return true;
  if (tab === 'active') return item.status === 'active';
  if (tab === 'wait') return item.status === 'queued' || item.status === 'retry_wait';
  if (tab === 'done') return item.status === 'done';
  if (tab === 'error') return item.status === 'error' || item.status === 'parked';
  if (tab === 'cancelled') return item.status === 'cancelled';
  return true;
}

// Gruppen im Reiter "Alle", in dieser Reihenfolge
export const GROUPS = ['active', 'wait', 'error', 'cancelled', 'done'];

// Was mit einem Download in welchem Zustand geht
export const canRetry = (item) => ['retry_wait', 'error', 'cancelled', 'parked'].includes(item.status);
export const canDelay = (item) => ['error', 'cancelled', 'parked'].includes(item.status);
export const canCancel = (item) => ['queued', 'active', 'retry_wait'].includes(item.status);

// Priorität: Normal, Hoch, Sofort (Klick schaltet weiter)
export const PRIORITY_CYCLE = [0, 5, 10];
export const PRIORITY_LABELS = { 0: 'Normal', 5: 'Hoch', 10: 'Sofort' };
export function nextPriority(current) {
  const index = PRIORITY_CYCLE.indexOf(current || 0);
  return PRIORITY_CYCLE[(index + 1) % PRIORITY_CYCLE.length];
}
