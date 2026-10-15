/**
 * TubeVault - Treffer hervorheben
 *
 * Gleiche Regel wie das Backend (backend/app/services/search/text.py): ein
 * Wort trifft, wenn es mit dem Suchwort beginnt (prefix) bzw. ihm gleicht;
 * Wortfolgen Wort für Wort hintereinander. Verglichen wird klein und ohne
 * Akzente ("Löten" trifft "loten"). Die Begriffe liefert die Suche selbst
 * (terms: [{ words, prefix }]).
 */

const WORD = /[\p{L}\p{N}_]+/gu;

/** Klein und ohne Akzente, wie der Index vergleicht */
export function fold(text) {
  return (text || '').normalize('NFKD').replace(/\p{M}/gu, '').toLowerCase();
}

function tokens(text) {
  return [...(text || '').matchAll(WORD)].map((m) => ({ start: m.index, end: m.index + m[0].length, word: fold(m[0]) }));
}

function hits(token, word, prefix) {
  return prefix ? token.word.startsWith(word) : token.word === word;
}

/** Bereiche [von, bis] aller Fundstellen im Text, zusammengelegt */
export function hitRanges(text, terms = []) {
  const list = tokens(text);
  const ranges = [];
  for (let i = 0; i < list.length; i++) {
    for (const term of terms) {
      const words = term.words.map(fold);
      if (i + words.length > list.length) continue;
      const last = words.length - 1;
      if (words.every((word, k) => hits(list[i + k], word, term.prefix && k === last))) {
        ranges.push([list[i].start, list[i + last].end]);
      }
    }
  }
  ranges.sort((a, b) => a[0] - b[0]);
  const merged = [];
  for (const range of ranges) {
    const previous = merged[merged.length - 1];
    if (previous && range[0] <= previous[1]) previous[1] = Math.max(previous[1], range[1]);
    else merged.push([...range]);
  }
  return merged;
}

/** Text in Teile mit und ohne Treffer: [{ text, hit }] */
export function markParts(text, terms = []) {
  const value = text || '';
  const parts = [];
  let at = 0;
  for (const [start, end] of hitRanges(value, terms)) {
    if (start > at) parts.push({ text: value.slice(at, start), hit: false });
    parts.push({ text: value.slice(start, end), hit: true });
    at = end;
  }
  if (at < value.length) parts.push({ text: value.slice(at), hit: false });
  return parts;
}
