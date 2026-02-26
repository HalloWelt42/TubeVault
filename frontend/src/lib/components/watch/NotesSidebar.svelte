<!--
  TubeVault -  NotesSidebar v1.8.49
  Live-Preview Markdown Editor für Video-Notizen
  Auto-Save nach 1s Tippause
  © HalloWelt42 -  Private Nutzung
-->
<script>
  import { api } from '../../api/client.js';
  import { toast } from '../../stores/notifications.js';

  let { videoId, initialNotes = '', onNotesChange = null } = $props();

  let text = $state(initialNotes || '');
  let saveTimer = null;
  let saving = $state(false);
  let lastSaved = $state('');
  let dirty = $derived(text !== lastSaved);
  let mode = $state('live'); // 'edit' | 'live' | 'preview'

  // Initialisierung
  $effect(() => {
    text = initialNotes || '';
    lastSaved = initialNotes || '';
  });

  function onInput() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => autoSave(), 1000);
  }

  async function autoSave() {
    if (!dirty || saving) return;
    saving = true;
    try {
      await api.saveNotes(videoId, text);
      lastSaved = text;
      if (onNotesChange) onNotesChange(text);
    } catch (e) {
      toast.error('Notizen speichern fehlgeschlagen');
    }
    saving = false;
  }

  // Markdown → HTML (einfach aber effektiv)
  function renderMd(src) {
    if (!src) return '<span class="empty">Keine Notizen…</span>';
    let h = src
      // Escaping
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      // Headers
      .replace(/^### (.+)$/gm, '<h4>$1</h4>')
      .replace(/^## (.+)$/gm, '<h3>$1</h3>')
      .replace(/^# (.+)$/gm, '<h2>$1</h2>')
      // Bold/Italic
      .replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/~~(.+?)~~/g, '<del>$1</del>')
      .replace(/`(.+?)`/g, '<code>$1</code>')
      // Links
      .replace(/\[(.+?)\]\((.+?)\)/g, '<a href="$2" target="_blank">$1</a>')
      // Checkboxes
      .replace(/^- \[x\] (.+)$/gm, '<div class="cb done">☑ $1</div>')
      .replace(/^- \[ \] (.+)$/gm, '<div class="cb">☐ $1</div>')
      // Lists
      .replace(/^- (.+)$/gm, '<li>$1</li>')
      .replace(/^(\d+)\. (.+)$/gm, '<li>$2</li>')
      // Blockquote
      .replace(/^&gt; (.+)$/gm, '<blockquote>$1</blockquote>')
      // HR
      .replace(/^---$/gm, '<hr>')
      // Paragraphs
      .replace(/\n\n/g, '</p><p>')
      .replace(/\n/g, '<br>');
    return '<p>' + h + '</p>';
  }

  function handleKeydown(e) {
    if (e.key === 'Tab') {
      e.preventDefault();
      const ta = e.target;
      const start = ta.selectionStart;
      const end = ta.selectionEnd;
      text = text.substring(0, start) + '  ' + text.substring(end);
      // Cursor nach Tab setzen
      requestAnimationFrame(() => {
        ta.selectionStart = ta.selectionEnd = start + 2;
      });
    }
    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
      e.preventDefault();
      autoSave();
    }
  }
</script>

<div class="notes-editor">
  <div class="ne-toolbar">
    <div class="ne-modes">
      <button class:active={mode === 'edit'} onclick={() => mode = 'edit'} title="Nur Editor">
        <i class="fa-solid fa-code"></i>
      </button>
      <button class:active={mode === 'live'} onclick={() => mode = 'live'} title="Live-Vorschau">
        <i class="fa-solid fa-columns"></i>
      </button>
      <button class:active={mode === 'preview'} onclick={() => mode = 'preview'} title="Nur Vorschau">
        <i class="fa-solid fa-eye"></i>
      </button>
    </div>
    <span class="ne-status">
      {#if saving}
        <i class="fa-solid fa-spinner fa-spin"></i>
      {:else if dirty}
        <i class="fa-solid fa-circle" style="color:var(--status-warning);font-size:0.4rem"></i>
      {:else if lastSaved}
        <i class="fa-solid fa-check" style="color:var(--status-success)"></i>
      {/if}
    </span>
  </div>

  <div class="ne-body" class:split={mode === 'live'}>
    {#if mode !== 'preview'}
      <textarea
        class="ne-textarea"
        bind:value={text}
        oninput={onInput}
        onkeydown={handleKeydown}
        placeholder="Notizen… (Markdown: **fett**, *kursiv*, # Überschrift, - Liste, [Link](url))"
        spellcheck="true"
      ></textarea>
    {/if}
    {#if mode !== 'edit'}
      <div class="ne-preview md-content">
        {@html renderMd(text)}
      </div>
    {/if}
  </div>

  <div class="ne-footer">
    <span class="ne-count">{text.length} Zeichen</span>
    <span class="ne-hint">Ctrl+S speichern · Tab einrücken</span>
  </div>
</div>

<style>
  .notes-editor {
    display: flex; flex-direction: column; height: 100%; overflow: hidden;
  }
  .ne-toolbar {
    display: flex; align-items: center; justify-content: space-between;
    padding: 4px 8px; border-bottom: 1px solid var(--border-secondary);
    flex-shrink: 0;
  }
  .ne-modes { display: flex; gap: 2px; }
  .ne-modes button {
    background: none; border: 1px solid transparent; color: var(--text-tertiary);
    cursor: pointer; padding: 3px 7px; border-radius: 4px; font-size: 0.72rem;
  }
  .ne-modes button:hover { color: var(--text-primary); background: var(--bg-tertiary); }
  .ne-modes button.active { color: var(--accent-primary); border-color: var(--accent-primary); background: rgba(var(--accent-rgb, 59,130,246), 0.08); }
  .ne-status { font-size: 0.7rem; display: flex; align-items: center; }

  .ne-body {
    flex: 1; display: flex; flex-direction: column; overflow: hidden; min-height: 0;
  }
  .ne-body.split {
    flex-direction: column;
  }
  .ne-textarea {
    flex: 1; min-height: 80px;
    resize: none; border: none; outline: none;
    padding: 10px; font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
    font-size: 0.78rem; line-height: 1.5;
    background: var(--bg-primary); color: var(--text-primary);
    overflow-y: auto;
  }
  .ne-body.split .ne-textarea { flex: 1; max-height: 50%; border-bottom: 1px solid var(--border-secondary); }
  .ne-body.split .ne-preview { flex: 1; }

  .ne-preview {
    flex: 1; overflow-y: auto; padding: 10px;
    font-size: 0.8rem; line-height: 1.6; color: var(--text-primary);
  }
  .ne-preview :global(h2) { font-size: 1.1rem; margin: 12px 0 6px; font-weight: 700; color: var(--text-primary); }
  .ne-preview :global(h3) { font-size: 0.95rem; margin: 10px 0 4px; font-weight: 600; color: var(--text-primary); }
  .ne-preview :global(h4) { font-size: 0.85rem; margin: 8px 0 4px; font-weight: 600; color: var(--text-secondary); }
  .ne-preview :global(strong) { font-weight: 700; }
  .ne-preview :global(code) { background: var(--bg-tertiary); padding: 1px 5px; border-radius: 3px; font-family: monospace; font-size: 0.75rem; }
  .ne-preview :global(blockquote) { border-left: 3px solid var(--accent-primary); padding-left: 10px; margin: 6px 0; color: var(--text-secondary); }
  .ne-preview :global(li) { margin-left: 16px; list-style: disc; }
  .ne-preview :global(a) { color: var(--accent-primary); text-decoration: underline; }
  .ne-preview :global(hr) { border: none; border-top: 1px solid var(--border-primary); margin: 8px 0; }
  .ne-preview :global(del) { text-decoration: line-through; color: var(--text-tertiary); }
  .ne-preview :global(.cb) { padding: 2px 0; }
  .ne-preview :global(.cb.done) { color: var(--status-success); }
  .ne-preview :global(.empty) { color: var(--text-tertiary); font-style: italic; }

  .ne-footer {
    display: flex; justify-content: space-between; padding: 3px 8px;
    border-top: 1px solid var(--border-secondary); font-size: 0.62rem;
    color: var(--text-tertiary); flex-shrink: 0;
  }
</style>
