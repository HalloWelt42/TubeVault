// TubeVault – Die Genannten eines Musiktitels
//
// Ein Titel kann mehrere Interpreten nennen ("50 Cent, Nate Dogg"); er zählt
// bei jedem (Server: music_artists). track.artist ist die Angabe, wie sie im
// Tag steht, track.artists die Genannten mit ihrer Gruppe ({ name, source }).
// Hier kommen beide für Verweise, Menü und "Zur Stelle" zusammen.

/** Die Genannten; ein Titel aus einer älteren gemerkten Warteschlange kennt nur artist_source */
export function artistRefs(track) {
  if (track?.artists?.length) return track.artists;
  return track?.artist_source ? [{ name: track.artist, source: track.artist_source }] : [];
}

/** Die Angabe in Stücken zum Anzeigen: jeder Genannte mit seiner Gruppe (source),
 *  dazwischen der Text, wie er dasteht (", ", " feat. "). Steht ein Name nicht
 *  in der Angabe, folgen die Genannten durch Komma getrennt. */
export function artistSegments(track) {
  const text = track?.artist || '';
  const refs = artistRefs(track);
  const segments = [];
  let at = 0;
  for (const ref of refs) {
    const found = text.indexOf(ref.name, at);
    if (found < 0) return refs.flatMap((r, i) => [...(i ? [{ text: ', ' }] : []), { text: r.name, source: r.source }]);
    if (found > at) segments.push({ text: text.slice(at, found) });
    segments.push({ text: ref.name, source: ref.source });
    at = found + ref.name.length;
  }
  if (at < text.length) segments.push({ text: text.slice(at) });
  return segments;
}
