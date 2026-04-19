<!--
  TubeVault – HoverActionBtn v1.0.0
  Zentrale Komponente für alle runden Hover-Overlay-Buttons.
  Wird in Feed, VideoCard, Playlists, QuickPlaylistBtn verwendet.
  © HalloWelt42 – Private Nutzung
-->
<script>
  let {
    variant = null,     // 'accent' | 'success' | 'warn' | 'danger' | 'flash' | 'later' | 'restore' | 'pinned'
    disabled = false,
    title = '',
    onclick,
    children,
  } = $props();
</script>

<button
  class="hover-action-btn"
  class:accent={variant === 'accent'}
  class:success={variant === 'success'}
  class:warn={variant === 'warn'}
  class:danger={variant === 'danger'}
  class:flash={variant === 'flash'}
  class:later={variant === 'later'}
  class:restore={variant === 'restore'}
  class:pinned={variant === 'pinned'}
  {disabled}
  {title}
  onclick={(e) => { e.stopPropagation(); onclick?.(e); }}
>
  {@render children?.()}
</button>
