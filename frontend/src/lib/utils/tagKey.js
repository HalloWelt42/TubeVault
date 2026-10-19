// TubeVault – Schlüssel eines Schlagworts in der Oberfläche
//
// Der Server findet Schlagwörter über ihren Schlüssel (video_tags.search_key:
// Unicode NFC, ohne Groß und Klein, Leerraum einfach) - "Körper" und "körper"
// sind dasselbe Schlagwort. Leiste und Auswahl vergleichen hier genauso, damit
// ein Schlagwort aus der Wiedergabe in der Leiste als gewählt erscheint und
// nicht doppelt gewählt wird. (Der Server faltet mit casefold; toLowerCase mit
// ß -> ss trifft das für deutsche und kyrillische Schlagwörter.)
export const tagKey = (tag) => String(tag ?? '').normalize('NFC').toLowerCase().replace(/ß/g, 'ss').replace(/\s+/g, ' ').trim();

export const sameTag = (a, b) => tagKey(a) === tagKey(b);
