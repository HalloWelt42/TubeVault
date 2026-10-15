// Warteschlange des Musikspielers bearbeiten, ohne den laufenden Titel zu
// verlieren: jede Rechnung liefert die neue Liste und die neue Stelle des
// laufenden Titels. Dazu die Rechnung fürs Umordnen durch Ziehen.

/** Eintrag von from nach to verschieben */
export function moveItem(queue, index, from, to) {
  if (from === to) return { queue, index };
  const items = [...queue];
  const [item] = items.splice(from, 1);
  items.splice(to, 0, item);
  let current = index;
  if (from === index) current = to;
  else if (from < index && to >= index) current -= 1;
  else if (from > index && to <= index) current += 1;
  return { queue: items, index: current };
}

/** Eintrag herausnehmen; der laufende Titel bleibt immer */
export function removeItem(queue, index, position) {
  if (position === index || position < 0 || position >= queue.length) return { queue, index };
  return { queue: queue.filter((_, i) => i !== position), index: position < index ? index - 1 : index };
}

/** Eintrag an eine Stelle setzen (Rückgängig nach dem Herausnehmen) */
export function insertItem(queue, index, item, position) {
  const at = Math.max(0, Math.min(position, queue.length));
  return { queue: [...queue.slice(0, at), item, ...queue.slice(at)], index: at <= index && index >= 0 ? index + 1 : index };
}

/** Zielplatz beim Ziehen: so viele Zeilen weiter, wie der Finger gewandert ist, innerhalb [min, max] */
export function dragTarget(from, dy, rowHeight, min, max) {
  if (!rowHeight) return from;
  return Math.max(min, Math.min(max, from + Math.round(dy / rowHeight)));
}

/** Wie eine andere Zeile während des Ziehens ausweicht: -1 eine Zeile hoch, 1 runter, 0 bleibt */
export function dragShift(i, from, to) {
  if (i === from) return 0;
  if (from < to && i > from && i <= to) return -1;
  if (from > to && i >= to && i < from) return 1;
  return 0;
}
