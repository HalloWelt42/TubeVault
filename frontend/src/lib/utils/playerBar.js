/**
 * TubeVault – Gemeinsames der Abspielleisten unten (Musik und Fernsteuerung)
 *
 *   <div use:playerBarHeight>   Höhe als --tv-spielerleiste auf :root (0px, wenn
 *                               die Leiste fehlt): fest oder haftend platzierte
 *                               Bereiche ziehen sie ab und verschwinden nie darunter
 *   <div use:dragValue={(v) => ...}>   Klick oder Ziehen liefert 0..1 (Zeitleiste, Lautstärke)
 */
export function playerBarHeight(node) {
  const root = document.documentElement.style;
  const observer = new ResizeObserver(() => root.setProperty('--tv-spielerleiste', `${Math.round(node.offsetHeight)}px`));
  observer.observe(node);
  return { destroy() { observer.disconnect(); root.setProperty('--tv-spielerleiste', '0px'); } };
}

export function dragValue(node, onValue) {
  let callback = onValue;
  const at = (e) => {
    const box = node.getBoundingClientRect();
    return Math.max(0, Math.min(1, (e.clientX - box.left) / box.width));
  };
  function down(e) {
    node.setPointerCapture(e.pointerId);
    callback(at(e));
    node.onpointermove = (m) => callback(at(m));
    node.onpointerup = () => { node.onpointermove = null; node.onpointerup = null; };
  }
  node.addEventListener('pointerdown', down);
  return {
    update(next) { callback = next; },
    destroy() { node.removeEventListener('pointerdown', down); },
  };
}
