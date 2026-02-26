/**
 * TubeVault -  Beschreibungs-Formatter
 * Konvertiert YouTube-Beschreibungen in klickbares HTML.
 * Verknüpfte Videos werden als Inline-Karten mit Thumbnail + Titel angezeigt.
 * © HalloWelt42
 */

/**
 * YouTube-Video-ID aus URL extrahieren.
 */
export function extractYtId(url) {
  const m = url.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/|youtube\.com\/shorts\/)([a-zA-Z0-9_-]{11})/);
  return m ? m[1] : null;
}

/**
 * Escape HTML-Zeichen.
 */
function esc(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/**
 * Beschreibungstext in HTML konvertieren.
 * @param {string} text - Rohtext
 * @param {Object} links - Map von video_id → { title, channel_name, thumbnail_path, status }
 */
export function formatDescription(text, links = {}) {
  if (!text) return '';
  let html = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  // URLs verarbeiten
  html = html.replace(
    /(https?:\/\/[^\s<]+)/g,
    (match, url) => {
      const ytId = extractYtId(url);
      if (ytId) {
        const link = links[ytId];
        if (link && link.title && link.status === 'ready') {
          // ✅ Verknüpft + lokal vorhanden → Inline-Karte
          const thumb = link.thumbnail_path
            ? `<img src="/api/player/${esc(ytId)}/thumbnail" alt="" class="desc-vcard-thumb">`
            : `<span class="desc-vcard-ph"><i class="fa-solid fa-film"></i></span>`;
          const ch = link.channel_name ? `<span class="desc-vcard-ch">${esc(link.channel_name)}</span>` : '';
          return `<a href="#" class="desc-vcard" data-videoid="${esc(ytId)}">${thumb}<span class="desc-vcard-info"><strong>${esc(link.title)}</strong>${ch}</span></a>`;
        }
        // Nicht verknüpft → YT-Link mit Such-Klick
        return `<a href="#" class="desc-yt-link" data-videoid="${esc(ytId)}" title="Video suchen: ${ytId}"><i class="fa-brands fa-youtube"></i> ${ytId}</a><a href="${url}" target="_blank" rel="noopener" class="desc-yt-ext" title="Auf YouTube öffnen"><i class="fa-solid fa-arrow-up-right-from-square"></i></a>`;
      }
      return `<a href="${url}" target="_blank" rel="noopener" class="desc-link">${url}</a>`;
    }
  );

  // Timestamps klickbar
  html = html.replace(
    /(?:^|[\s(])(\d{1,2}:\d{2}(?::\d{2})?)(?=[\s),.]|$)/gm,
    (match, ts) => {
      const parts = ts.split(':').map(Number);
      const secs = parts.length === 3 ? parts[0]*3600 + parts[1]*60 + parts[2] : parts[0]*60 + parts[1];
      return match.replace(ts, `<a href="#" class="desc-ts" data-time="${secs}">${ts}</a>`);
    }
  );

  // Hashtags klickbar
  html = html.replace(
    /#([\wäöüÄÖÜß]{2,})/g,
    '<a href="#" class="desc-tag" data-tag="$1">#$1</a>'
  );
  return html.replace(/\n/g, '<br>');
}

/**
 * Click-Handler für Beschreibungs-Links (delegiert).
 * Gibt { type, value } zurück oder null.
 */
export function parseDescClick(e) {
  // Verknüpfte Video-Karte → internes Öffnen
  const vcard = e.target.closest('.desc-vcard');
  if (vcard) {
    e.preventDefault();
    return { type: 'open_video', value: vcard.dataset.videoid };
  }
  const ytLink = e.target.closest('.desc-yt-link');
  if (ytLink) {
    e.preventDefault();
    return { type: 'youtube', value: ytLink.dataset.videoid };
  }
  const tag = e.target.closest('.desc-tag');
  if (tag) {
    e.preventDefault();
    return { type: 'tag', value: tag.dataset.tag };
  }
  const ts = e.target.closest('.desc-ts');
  if (ts) {
    e.preventDefault();
    return { type: 'timestamp', value: Number(ts.dataset.time) };
  }
  return null;
}
