<!--
  TubeVault -  DonateOverlay v1.0.0
  Glasmorphism Spenden-Overlay
  Ko-fi + Crypto (BTC, DOGE, ETH)
  © HalloWelt42 – Nicht-kommerzielle Nutzung / Non-commercial use only
  SPDX-License-Identifier: LicenseRef-TubeVault-NC-2.0
-->
<script>
  // Sichtbarkeit des Overlays
  let { visible = $bindable(false) } = $props();

  // Aktiver Crypto-Tab
  let activeCrypto = $state('btc');

  // Kopier-Feedback pro Coin
  let copyFeedback = $state({});

  const CRYPTO = {
    btc: { label: 'Bitcoin (BTC)', symbol: '₿', color: '#f7931a', address: 'bc1qnd599khdkv3v3npmj9ufxzf6h4fzanny2acwqr' },
    doge: { label: 'Dogecoin (DOGE)', symbol: 'Ð', color: '#c2a633', address: 'DL7tuiYCqm3xQjMDXChdxeQxqUGMACn1ZV' },
    eth: { label: 'Ethereum (ETH)', symbol: 'Ξ', color: '#627eea', address: '0x8A28fc47bFFFA03C8f685fa0836E2dBe1CA14F27' }
  };

  // Adresse kopieren
  async function copyAddress(coin) {
    try {
      await navigator.clipboard.writeText(CRYPTO[coin].address);
      copyFeedback[coin] = true;
      setTimeout(() => { copyFeedback[coin] = false; }, 2000);
    } catch { /* Fallback */ }
  }

  // Schließen via ESC
  function onKeydown(e) {
    if (e.key === 'Escape') visible = false;
  }

  // Backdrop-Klick schließt
  function onBackdrop(e) {
    if (e.target === e.currentTarget) visible = false;
  }
</script>

<svelte:window onkeydown={onKeydown} />

{#if visible}
<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="donate-backdrop" onclick={onBackdrop}>
  <div class="donate-panel">

    <!-- Schließen-Button -->
    <button class="donate-close" onclick={() => visible = false} aria-label="Schließen">✕</button>

    <!-- Header -->
    <div class="donate-header">
      <span class="donate-icon">☕</span>
      <h2>Made with ❤️ in Sachsen-Anhalt</h2>
      <p>Open Source aus Sachsen-Anhalt.<br>Kein Tracking, keine Werbung, keine Kompromisse.</p>
    </div>

    <!-- Ko-fi Button -->
    <a href="https://ko-fi.com/HalloWelt42" target="_blank" rel="noopener" class="kofi-btn">
      <span class="kofi-icon">☕</span>
      <span>Ko-fi -  Kaffee spendieren</span>
    </a>

    <!-- Crypto Label -->
    <p class="crypto-label">Oder per Kryptowährung:</p>

    <!-- Crypto Tabs -->
    <div class="crypto-tabs">
      {#each Object.entries(CRYPTO) as [key, coin]}
        <button
          class="crypto-tab"
          class:active={activeCrypto === key}
          onclick={() => activeCrypto = key}
          style="--coin-color: {coin.color}"
        >
          <span class="coin-symbol">{coin.symbol}</span>
          <span>{coin.label.split(' ')[0]}</span>
        </button>
      {/each}
    </div>

    <!-- Crypto Content -->
    {#each Object.entries(CRYPTO) as [key, coin]}
      {#if activeCrypto === key}
        <div class="crypto-content">
          <div class="crypto-box">
            <div class="qr-wrapper">
              {#if key === 'btc'}
                {@html `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" version="1.1" width="160px" height="160px" viewBox="0 0 160 160"><defs><rect id="btc-b" width="5" height="5" fill="#4f6587" fill-opacity="1"/></defs><rect x="0" y="0" width="160" height="160" fill="#ffffff" fill-opacity="1"/><use x="7" y="7" xlink:href="#btc-b"/><use x="12" y="7" xlink:href="#btc-b"/><use x="17" y="7" xlink:href="#btc-b"/><use x="22" y="7" xlink:href="#btc-b"/><use x="27" y="7" xlink:href="#btc-b"/><use x="32" y="7" xlink:href="#btc-b"/><use x="37" y="7" xlink:href="#btc-b"/><use x="52" y="7" xlink:href="#btc-b"/><use x="67" y="7" xlink:href="#btc-b"/><use x="77" y="7" xlink:href="#btc-b"/><use x="82" y="7" xlink:href="#btc-b"/><use x="97" y="7" xlink:href="#btc-b"/><use x="102" y="7" xlink:href="#btc-b"/><use x="107" y="7" xlink:href="#btc-b"/><use x="117" y="7" xlink:href="#btc-b"/><use x="122" y="7" xlink:href="#btc-b"/><use x="127" y="7" xlink:href="#btc-b"/><use x="132" y="7" xlink:href="#btc-b"/><use x="137" y="7" xlink:href="#btc-b"/><use x="142" y="7" xlink:href="#btc-b"/><use x="147" y="7" xlink:href="#btc-b"/><use x="7" y="12" xlink:href="#btc-b"/><use x="37" y="12" xlink:href="#btc-b"/><use x="47" y="12" xlink:href="#btc-b"/><use x="62" y="12" xlink:href="#btc-b"/><use x="67" y="12" xlink:href="#btc-b"/><use x="72" y="12" xlink:href="#btc-b"/><use x="77" y="12" xlink:href="#btc-b"/><use x="87" y="12" xlink:href="#btc-b"/><use x="102" y="12" xlink:href="#btc-b"/><use x="117" y="12" xlink:href="#btc-b"/><use x="147" y="12" xlink:href="#btc-b"/><use x="7" y="17" xlink:href="#btc-b"/><use x="17" y="17" xlink:href="#btc-b"/><use x="22" y="17" xlink:href="#btc-b"/><use x="27" y="17" xlink:href="#btc-b"/><use x="37" y="17" xlink:href="#btc-b"/><use x="47" y="17" xlink:href="#btc-b"/><use x="52" y="17" xlink:href="#btc-b"/><use x="57" y="17" xlink:href="#btc-b"/><use x="62" y="17" xlink:href="#btc-b"/><use x="67" y="17" xlink:href="#btc-b"/><use x="72" y="17" xlink:href="#btc-b"/><use x="77" y="17" xlink:href="#btc-b"/><use x="82" y="17" xlink:href="#btc-b"/><use x="102" y="17" xlink:href="#btc-b"/><use x="107" y="17" xlink:href="#btc-b"/><use x="117" y="17" xlink:href="#btc-b"/><use x="127" y="17" xlink:href="#btc-b"/><use x="132" y="17" xlink:href="#btc-b"/><use x="137" y="17" xlink:href="#btc-b"/><use x="147" y="17" xlink:href="#btc-b"/><use x="7" y="22" xlink:href="#btc-b"/><use x="17" y="22" xlink:href="#btc-b"/><use x="22" y="22" xlink:href="#btc-b"/><use x="27" y="22" xlink:href="#btc-b"/><use x="37" y="22" xlink:href="#btc-b"/><use x="52" y="22" xlink:href="#btc-b"/><use x="57" y="22" xlink:href="#btc-b"/><use x="62" y="22" xlink:href="#btc-b"/><use x="72" y="22" xlink:href="#btc-b"/><use x="82" y="22" xlink:href="#btc-b"/><use x="92" y="22" xlink:href="#btc-b"/><use x="102" y="22" xlink:href="#btc-b"/><use x="107" y="22" xlink:href="#btc-b"/><use x="117" y="22" xlink:href="#btc-b"/><use x="127" y="22" xlink:href="#btc-b"/><use x="132" y="22" xlink:href="#btc-b"/><use x="137" y="22" xlink:href="#btc-b"/><use x="147" y="22" xlink:href="#btc-b"/><use x="7" y="27" xlink:href="#btc-b"/><use x="17" y="27" xlink:href="#btc-b"/><use x="22" y="27" xlink:href="#btc-b"/><use x="27" y="27" xlink:href="#btc-b"/><use x="37" y="27" xlink:href="#btc-b"/><use x="47" y="27" xlink:href="#btc-b"/><use x="72" y="27" xlink:href="#btc-b"/><use x="82" y="27" xlink:href="#btc-b"/><use x="87" y="27" xlink:href="#btc-b"/><use x="102" y="27" xlink:href="#btc-b"/><use x="117" y="27" xlink:href="#btc-b"/><use x="127" y="27" xlink:href="#btc-b"/><use x="132" y="27" xlink:href="#btc-b"/><use x="137" y="27" xlink:href="#btc-b"/><use x="147" y="27" xlink:href="#btc-b"/><use x="7" y="32" xlink:href="#btc-b"/><use x="37" y="32" xlink:href="#btc-b"/><use x="47" y="32" xlink:href="#btc-b"/><use x="52" y="32" xlink:href="#btc-b"/><use x="62" y="32" xlink:href="#btc-b"/><use x="77" y="32" xlink:href="#btc-b"/><use x="92" y="32" xlink:href="#btc-b"/><use x="97" y="32" xlink:href="#btc-b"/><use x="107" y="32" xlink:href="#btc-b"/><use x="117" y="32" xlink:href="#btc-b"/><use x="147" y="32" xlink:href="#btc-b"/><use x="7" y="37" xlink:href="#btc-b"/><use x="12" y="37" xlink:href="#btc-b"/><use x="17" y="37" xlink:href="#btc-b"/><use x="22" y="37" xlink:href="#btc-b"/><use x="27" y="37" xlink:href="#btc-b"/><use x="32" y="37" xlink:href="#btc-b"/><use x="37" y="37" xlink:href="#btc-b"/><use x="47" y="37" xlink:href="#btc-b"/><use x="57" y="37" xlink:href="#btc-b"/><use x="67" y="37" xlink:href="#btc-b"/><use x="77" y="37" xlink:href="#btc-b"/><use x="87" y="37" xlink:href="#btc-b"/><use x="97" y="37" xlink:href="#btc-b"/><use x="107" y="37" xlink:href="#btc-b"/><use x="117" y="37" xlink:href="#btc-b"/><use x="122" y="37" xlink:href="#btc-b"/><use x="127" y="37" xlink:href="#btc-b"/><use x="132" y="37" xlink:href="#btc-b"/><use x="137" y="37" xlink:href="#btc-b"/><use x="142" y="37" xlink:href="#btc-b"/><use x="147" y="37" xlink:href="#btc-b"/><use x="47" y="42" xlink:href="#btc-b"/><use x="52" y="42" xlink:href="#btc-b"/><use x="67" y="42" xlink:href="#btc-b"/><use x="77" y="42" xlink:href="#btc-b"/><use x="92" y="42" xlink:href="#btc-b"/><use x="97" y="42" xlink:href="#btc-b"/><use x="102" y="42" xlink:href="#btc-b"/><use x="107" y="42" xlink:href="#btc-b"/><use x="7" y="47" xlink:href="#btc-b"/><use x="12" y="47" xlink:href="#btc-b"/><use x="22" y="47" xlink:href="#btc-b"/><use x="37" y="47" xlink:href="#btc-b"/><use x="42" y="47" xlink:href="#btc-b"/><use x="57" y="47" xlink:href="#btc-b"/><use x="72" y="47" xlink:href="#btc-b"/><use x="92" y="47" xlink:href="#btc-b"/><use x="117" y="47" xlink:href="#btc-b"/><use x="122" y="47" xlink:href="#btc-b"/><use x="127" y="47" xlink:href="#btc-b"/><use x="137" y="47" xlink:href="#btc-b"/><use x="142" y="47" xlink:href="#btc-b"/><use x="12" y="52" xlink:href="#btc-b"/><use x="22" y="52" xlink:href="#btc-b"/><use x="27" y="52" xlink:href="#btc-b"/><use x="42" y="52" xlink:href="#btc-b"/><use x="57" y="52" xlink:href="#btc-b"/><use x="62" y="52" xlink:href="#btc-b"/><use x="72" y="52" xlink:href="#btc-b"/><use x="82" y="52" xlink:href="#btc-b"/><use x="92" y="52" xlink:href="#btc-b"/><use x="97" y="52" xlink:href="#btc-b"/><use x="102" y="52" xlink:href="#btc-b"/><use x="112" y="52" xlink:href="#btc-b"/><use x="122" y="52" xlink:href="#btc-b"/><use x="127" y="52" xlink:href="#btc-b"/><use x="132" y="52" xlink:href="#btc-b"/><use x="147" y="52" xlink:href="#btc-b"/><use x="12" y="57" xlink:href="#btc-b"/><use x="22" y="57" xlink:href="#btc-b"/><use x="37" y="57" xlink:href="#btc-b"/><use x="52" y="57" xlink:href="#btc-b"/><use x="57" y="57" xlink:href="#btc-b"/><use x="92" y="57" xlink:href="#btc-b"/><use x="102" y="57" xlink:href="#btc-b"/><use x="112" y="57" xlink:href="#btc-b"/><use x="17" y="62" xlink:href="#btc-b"/><use x="22" y="62" xlink:href="#btc-b"/><use x="27" y="62" xlink:href="#btc-b"/><use x="32" y="62" xlink:href="#btc-b"/><use x="42" y="62" xlink:href="#btc-b"/><use x="47" y="62" xlink:href="#btc-b"/><use x="72" y="62" xlink:href="#btc-b"/><use x="77" y="62" xlink:href="#btc-b"/><use x="87" y="62" xlink:href="#btc-b"/><use x="112" y="62" xlink:href="#btc-b"/><use x="117" y="62" xlink:href="#btc-b"/><use x="122" y="62" xlink:href="#btc-b"/><use x="132" y="62" xlink:href="#btc-b"/><use x="137" y="62" xlink:href="#btc-b"/><use x="142" y="62" xlink:href="#btc-b"/><use x="147" y="62" xlink:href="#btc-b"/><use x="7" y="67" xlink:href="#btc-b"/><use x="12" y="67" xlink:href="#btc-b"/><use x="17" y="67" xlink:href="#btc-b"/><use x="22" y="67" xlink:href="#btc-b"/><use x="32" y="67" xlink:href="#btc-b"/><use x="37" y="67" xlink:href="#btc-b"/><use x="67" y="67" xlink:href="#btc-b"/><use x="77" y="67" xlink:href="#btc-b"/><use x="87" y="67" xlink:href="#btc-b"/><use x="92" y="67" xlink:href="#btc-b"/><use x="107" y="67" xlink:href="#btc-b"/><use x="112" y="67" xlink:href="#btc-b"/><use x="117" y="67" xlink:href="#btc-b"/><use x="122" y="67" xlink:href="#btc-b"/><use x="132" y="67" xlink:href="#btc-b"/><use x="137" y="67" xlink:href="#btc-b"/><use x="142" y="67" xlink:href="#btc-b"/><use x="147" y="67" xlink:href="#btc-b"/><use x="27" y="72" xlink:href="#btc-b"/><use x="32" y="72" xlink:href="#btc-b"/><use x="47" y="72" xlink:href="#btc-b"/><use x="52" y="72" xlink:href="#btc-b"/><use x="57" y="72" xlink:href="#btc-b"/><use x="62" y="72" xlink:href="#btc-b"/><use x="67" y="72" xlink:href="#btc-b"/><use x="77" y="72" xlink:href="#btc-b"/><use x="87" y="72" xlink:href="#btc-b"/><use x="92" y="72" xlink:href="#btc-b"/><use x="102" y="72" xlink:href="#btc-b"/><use x="107" y="72" xlink:href="#btc-b"/><use x="112" y="72" xlink:href="#btc-b"/><use x="117" y="72" xlink:href="#btc-b"/><use x="122" y="72" xlink:href="#btc-b"/><use x="127" y="72" xlink:href="#btc-b"/><use x="132" y="72" xlink:href="#btc-b"/><use x="142" y="72" xlink:href="#btc-b"/><use x="12" y="77" xlink:href="#btc-b"/><use x="22" y="77" xlink:href="#btc-b"/><use x="32" y="77" xlink:href="#btc-b"/><use x="37" y="77" xlink:href="#btc-b"/><use x="52" y="77" xlink:href="#btc-b"/><use x="67" y="77" xlink:href="#btc-b"/><use x="72" y="77" xlink:href="#btc-b"/><use x="77" y="77" xlink:href="#btc-b"/><use x="82" y="77" xlink:href="#btc-b"/><use x="102" y="77" xlink:href="#btc-b"/><use x="112" y="77" xlink:href="#btc-b"/><use x="117" y="77" xlink:href="#btc-b"/><use x="122" y="77" xlink:href="#btc-b"/><use x="132" y="77" xlink:href="#btc-b"/><use x="137" y="77" xlink:href="#btc-b"/><use x="147" y="77" xlink:href="#btc-b"/><use x="17" y="82" xlink:href="#btc-b"/><use x="32" y="82" xlink:href="#btc-b"/><use x="42" y="82" xlink:href="#btc-b"/><use x="52" y="82" xlink:href="#btc-b"/><use x="57" y="82" xlink:href="#btc-b"/><use x="67" y="82" xlink:href="#btc-b"/><use x="72" y="82" xlink:href="#btc-b"/><use x="87" y="82" xlink:href="#btc-b"/><use x="97" y="82" xlink:href="#btc-b"/><use x="107" y="82" xlink:href="#btc-b"/><use x="112" y="82" xlink:href="#btc-b"/><use x="117" y="82" xlink:href="#btc-b"/><use x="132" y="82" xlink:href="#btc-b"/><use x="142" y="82" xlink:href="#btc-b"/><use x="147" y="82" xlink:href="#btc-b"/><use x="12" y="87" xlink:href="#btc-b"/><use x="22" y="87" xlink:href="#btc-b"/><use x="27" y="87" xlink:href="#btc-b"/><use x="32" y="87" xlink:href="#btc-b"/><use x="37" y="87" xlink:href="#btc-b"/><use x="62" y="87" xlink:href="#btc-b"/><use x="77" y="87" xlink:href="#btc-b"/><use x="97" y="87" xlink:href="#btc-b"/><use x="102" y="87" xlink:href="#btc-b"/><use x="117" y="87" xlink:href="#btc-b"/><use x="122" y="87" xlink:href="#btc-b"/><use x="127" y="87" xlink:href="#btc-b"/><use x="137" y="87" xlink:href="#btc-b"/><use x="142" y="87" xlink:href="#btc-b"/><use x="12" y="92" xlink:href="#btc-b"/><use x="17" y="92" xlink:href="#btc-b"/><use x="42" y="92" xlink:href="#btc-b"/><use x="52" y="92" xlink:href="#btc-b"/><use x="57" y="92" xlink:href="#btc-b"/><use x="72" y="92" xlink:href="#btc-b"/><use x="87" y="92" xlink:href="#btc-b"/><use x="107" y="92" xlink:href="#btc-b"/><use x="117" y="92" xlink:href="#btc-b"/><use x="127" y="92" xlink:href="#btc-b"/><use x="137" y="92" xlink:href="#btc-b"/><use x="142" y="92" xlink:href="#btc-b"/><use x="147" y="92" xlink:href="#btc-b"/><use x="7" y="97" xlink:href="#btc-b"/><use x="17" y="97" xlink:href="#btc-b"/><use x="22" y="97" xlink:href="#btc-b"/><use x="37" y="97" xlink:href="#btc-b"/><use x="47" y="97" xlink:href="#btc-b"/><use x="52" y="97" xlink:href="#btc-b"/><use x="57" y="97" xlink:href="#btc-b"/><use x="72" y="97" xlink:href="#btc-b"/><use x="87" y="97" xlink:href="#btc-b"/><use x="92" y="97" xlink:href="#btc-b"/><use x="112" y="97" xlink:href="#btc-b"/><use x="117" y="97" xlink:href="#btc-b"/><use x="122" y="97" xlink:href="#btc-b"/><use x="22" y="102" xlink:href="#btc-b"/><use x="42" y="102" xlink:href="#btc-b"/><use x="47" y="102" xlink:href="#btc-b"/><use x="57" y="102" xlink:href="#btc-b"/><use x="62" y="102" xlink:href="#btc-b"/><use x="77" y="102" xlink:href="#btc-b"/><use x="97" y="102" xlink:href="#btc-b"/><use x="102" y="102" xlink:href="#btc-b"/><use x="122" y="102" xlink:href="#btc-b"/><use x="132" y="102" xlink:href="#btc-b"/><use x="137" y="102" xlink:href="#btc-b"/><use x="142" y="102" xlink:href="#btc-b"/><use x="7" y="107" xlink:href="#btc-b"/><use x="27" y="107" xlink:href="#btc-b"/><use x="32" y="107" xlink:href="#btc-b"/><use x="37" y="107" xlink:href="#btc-b"/><use x="42" y="107" xlink:href="#btc-b"/><use x="52" y="107" xlink:href="#btc-b"/><use x="62" y="107" xlink:href="#btc-b"/><use x="67" y="107" xlink:href="#btc-b"/><use x="72" y="107" xlink:href="#btc-b"/><use x="77" y="107" xlink:href="#btc-b"/><use x="87" y="107" xlink:href="#btc-b"/><use x="97" y="107" xlink:href="#btc-b"/><use x="107" y="107" xlink:href="#btc-b"/><use x="112" y="107" xlink:href="#btc-b"/><use x="117" y="107" xlink:href="#btc-b"/><use x="122" y="107" xlink:href="#btc-b"/><use x="127" y="107" xlink:href="#btc-b"/><use x="137" y="107" xlink:href="#btc-b"/><use x="147" y="107" xlink:href="#btc-b"/><use x="47" y="112" xlink:href="#btc-b"/><use x="52" y="112" xlink:href="#btc-b"/><use x="62" y="112" xlink:href="#btc-b"/><use x="67" y="112" xlink:href="#btc-b"/><use x="72" y="112" xlink:href="#btc-b"/><use x="77" y="112" xlink:href="#btc-b"/><use x="82" y="112" xlink:href="#btc-b"/><use x="87" y="112" xlink:href="#btc-b"/><use x="92" y="112" xlink:href="#btc-b"/><use x="102" y="112" xlink:href="#btc-b"/><use x="107" y="112" xlink:href="#btc-b"/><use x="127" y="112" xlink:href="#btc-b"/><use x="142" y="112" xlink:href="#btc-b"/><use x="7" y="117" xlink:href="#btc-b"/><use x="12" y="117" xlink:href="#btc-b"/><use x="17" y="117" xlink:href="#btc-b"/><use x="22" y="117" xlink:href="#btc-b"/><use x="27" y="117" xlink:href="#btc-b"/><use x="32" y="117" xlink:href="#btc-b"/><use x="37" y="117" xlink:href="#btc-b"/><use x="47" y="117" xlink:href="#btc-b"/><use x="62" y="117" xlink:href="#btc-b"/><use x="67" y="117" xlink:href="#btc-b"/><use x="87" y="117" xlink:href="#btc-b"/><use x="92" y="117" xlink:href="#btc-b"/><use x="107" y="117" xlink:href="#btc-b"/><use x="117" y="117" xlink:href="#btc-b"/><use x="127" y="117" xlink:href="#btc-b"/><use x="132" y="117" xlink:href="#btc-b"/><use x="142" y="117" xlink:href="#btc-b"/><use x="7" y="122" xlink:href="#btc-b"/><use x="37" y="122" xlink:href="#btc-b"/><use x="52" y="122" xlink:href="#btc-b"/><use x="57" y="122" xlink:href="#btc-b"/><use x="62" y="122" xlink:href="#btc-b"/><use x="67" y="122" xlink:href="#btc-b"/><use x="72" y="122" xlink:href="#btc-b"/><use x="107" y="122" xlink:href="#btc-b"/><use x="127" y="122" xlink:href="#btc-b"/><use x="137" y="122" xlink:href="#btc-b"/><use x="142" y="122" xlink:href="#btc-b"/><use x="147" y="122" xlink:href="#btc-b"/><use x="7" y="127" xlink:href="#btc-b"/><use x="17" y="127" xlink:href="#btc-b"/><use x="22" y="127" xlink:href="#btc-b"/><use x="27" y="127" xlink:href="#btc-b"/><use x="37" y="127" xlink:href="#btc-b"/><use x="57" y="127" xlink:href="#btc-b"/><use x="62" y="127" xlink:href="#btc-b"/><use x="67" y="127" xlink:href="#btc-b"/><use x="77" y="127" xlink:href="#btc-b"/><use x="87" y="127" xlink:href="#btc-b"/><use x="92" y="127" xlink:href="#btc-b"/><use x="107" y="127" xlink:href="#btc-b"/><use x="112" y="127" xlink:href="#btc-b"/><use x="117" y="127" xlink:href="#btc-b"/><use x="122" y="127" xlink:href="#btc-b"/><use x="127" y="127" xlink:href="#btc-b"/><use x="137" y="127" xlink:href="#btc-b"/><use x="7" y="132" xlink:href="#btc-b"/><use x="17" y="132" xlink:href="#btc-b"/><use x="22" y="132" xlink:href="#btc-b"/><use x="27" y="132" xlink:href="#btc-b"/><use x="37" y="132" xlink:href="#btc-b"/><use x="47" y="132" xlink:href="#btc-b"/><use x="52" y="132" xlink:href="#btc-b"/><use x="57" y="132" xlink:href="#btc-b"/><use x="62" y="132" xlink:href="#btc-b"/><use x="77" y="132" xlink:href="#btc-b"/><use x="82" y="132" xlink:href="#btc-b"/><use x="87" y="132" xlink:href="#btc-b"/><use x="92" y="132" xlink:href="#btc-b"/><use x="102" y="132" xlink:href="#btc-b"/><use x="107" y="132" xlink:href="#btc-b"/><use x="117" y="132" xlink:href="#btc-b"/><use x="147" y="132" xlink:href="#btc-b"/><use x="7" y="137" xlink:href="#btc-b"/><use x="17" y="137" xlink:href="#btc-b"/><use x="22" y="137" xlink:href="#btc-b"/><use x="27" y="137" xlink:href="#btc-b"/><use x="37" y="137" xlink:href="#btc-b"/><use x="57" y="137" xlink:href="#btc-b"/><use x="62" y="137" xlink:href="#btc-b"/><use x="67" y="137" xlink:href="#btc-b"/><use x="72" y="137" xlink:href="#btc-b"/><use x="77" y="137" xlink:href="#btc-b"/><use x="82" y="137" xlink:href="#btc-b"/><use x="87" y="137" xlink:href="#btc-b"/><use x="97" y="137" xlink:href="#btc-b"/><use x="102" y="137" xlink:href="#btc-b"/><use x="122" y="137" xlink:href="#btc-b"/><use x="132" y="137" xlink:href="#btc-b"/><use x="137" y="137" xlink:href="#btc-b"/><use x="147" y="137" xlink:href="#btc-b"/><use x="7" y="142" xlink:href="#btc-b"/><use x="37" y="142" xlink:href="#btc-b"/><use x="47" y="142" xlink:href="#btc-b"/><use x="52" y="142" xlink:href="#btc-b"/><use x="57" y="142" xlink:href="#btc-b"/><use x="62" y="142" xlink:href="#btc-b"/><use x="72" y="142" xlink:href="#btc-b"/><use x="77" y="142" xlink:href="#btc-b"/><use x="87" y="142" xlink:href="#btc-b"/><use x="92" y="142" xlink:href="#btc-b"/><use x="97" y="142" xlink:href="#btc-b"/><use x="107" y="142" xlink:href="#btc-b"/><use x="112" y="142" xlink:href="#btc-b"/><use x="127" y="142" xlink:href="#btc-b"/><use x="147" y="142" xlink:href="#btc-b"/><use x="7" y="147" xlink:href="#btc-b"/><use x="12" y="147" xlink:href="#btc-b"/><use x="17" y="147" xlink:href="#btc-b"/><use x="22" y="147" xlink:href="#btc-b"/><use x="27" y="147" xlink:href="#btc-b"/><use x="32" y="147" xlink:href="#btc-b"/><use x="37" y="147" xlink:href="#btc-b"/><use x="47" y="147" xlink:href="#btc-b"/><use x="57" y="147" xlink:href="#btc-b"/><use x="67" y="147" xlink:href="#btc-b"/><use x="77" y="147" xlink:href="#btc-b"/><use x="92" y="147" xlink:href="#btc-b"/><use x="102" y="147" xlink:href="#btc-b"/><use x="107" y="147" xlink:href="#btc-b"/><use x="112" y="147" xlink:href="#btc-b"/><use x="117" y="147" xlink:href="#btc-b"/><use x="127" y="147" xlink:href="#btc-b"/><use x="137" y="147" xlink:href="#btc-b"/><use x="142" y="147" xlink:href="#btc-b"/></svg>`}
              {:else if key === 'doge'}
                {@html `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" version="1.1" width="160px" height="160px" viewBox="0 0 160 160"><defs><rect id="doge-b" width="5" height="5" fill="#4f6587" fill-opacity="1"/></defs><rect x="0" y="0" width="160" height="160" fill="#ffffff" fill-opacity="1"/><use x="7" y="7" xlink:href="#doge-b"/><use x="12" y="7" xlink:href="#doge-b"/><use x="17" y="7" xlink:href="#doge-b"/><use x="22" y="7" xlink:href="#doge-b"/><use x="27" y="7" xlink:href="#doge-b"/><use x="32" y="7" xlink:href="#doge-b"/><use x="37" y="7" xlink:href="#doge-b"/><use x="47" y="7" xlink:href="#doge-b"/><use x="52" y="7" xlink:href="#doge-b"/><use x="57" y="7" xlink:href="#doge-b"/><use x="67" y="7" xlink:href="#doge-b"/><use x="77" y="7" xlink:href="#doge-b"/><use x="97" y="7" xlink:href="#doge-b"/><use x="102" y="7" xlink:href="#doge-b"/><use x="107" y="7" xlink:href="#doge-b"/><use x="117" y="7" xlink:href="#doge-b"/><use x="122" y="7" xlink:href="#doge-b"/><use x="127" y="7" xlink:href="#doge-b"/><use x="132" y="7" xlink:href="#doge-b"/><use x="137" y="7" xlink:href="#doge-b"/><use x="142" y="7" xlink:href="#doge-b"/><use x="147" y="7" xlink:href="#doge-b"/><use x="7" y="12" xlink:href="#doge-b"/><use x="37" y="12" xlink:href="#doge-b"/><use x="47" y="12" xlink:href="#doge-b"/><use x="52" y="12" xlink:href="#doge-b"/><use x="57" y="12" xlink:href="#doge-b"/><use x="92" y="12" xlink:href="#doge-b"/><use x="117" y="12" xlink:href="#doge-b"/><use x="147" y="12" xlink:href="#doge-b"/><use x="7" y="17" xlink:href="#doge-b"/><use x="17" y="17" xlink:href="#doge-b"/><use x="22" y="17" xlink:href="#doge-b"/><use x="27" y="17" xlink:href="#doge-b"/><use x="37" y="17" xlink:href="#doge-b"/><use x="47" y="17" xlink:href="#doge-b"/><use x="57" y="17" xlink:href="#doge-b"/><use x="62" y="17" xlink:href="#doge-b"/><use x="72" y="17" xlink:href="#doge-b"/><use x="82" y="17" xlink:href="#doge-b"/><use x="87" y="17" xlink:href="#doge-b"/><use x="92" y="17" xlink:href="#doge-b"/><use x="102" y="17" xlink:href="#doge-b"/><use x="107" y="17" xlink:href="#doge-b"/><use x="117" y="17" xlink:href="#doge-b"/><use x="127" y="17" xlink:href="#doge-b"/><use x="132" y="17" xlink:href="#doge-b"/><use x="137" y="17" xlink:href="#doge-b"/><use x="147" y="17" xlink:href="#doge-b"/><use x="7" y="22" xlink:href="#doge-b"/><use x="17" y="22" xlink:href="#doge-b"/><use x="22" y="22" xlink:href="#doge-b"/><use x="27" y="22" xlink:href="#doge-b"/><use x="37" y="22" xlink:href="#doge-b"/><use x="47" y="22" xlink:href="#doge-b"/><use x="52" y="22" xlink:href="#doge-b"/><use x="62" y="22" xlink:href="#doge-b"/><use x="77" y="22" xlink:href="#doge-b"/><use x="82" y="22" xlink:href="#doge-b"/><use x="87" y="22" xlink:href="#doge-b"/><use x="92" y="22" xlink:href="#doge-b"/><use x="97" y="22" xlink:href="#doge-b"/><use x="117" y="22" xlink:href="#doge-b"/><use x="127" y="22" xlink:href="#doge-b"/><use x="132" y="22" xlink:href="#doge-b"/><use x="137" y="22" xlink:href="#doge-b"/><use x="147" y="22" xlink:href="#doge-b"/><use x="7" y="27" xlink:href="#doge-b"/><use x="17" y="27" xlink:href="#doge-b"/><use x="22" y="27" xlink:href="#doge-b"/><use x="27" y="27" xlink:href="#doge-b"/><use x="37" y="27" xlink:href="#doge-b"/><use x="72" y="27" xlink:href="#doge-b"/><use x="77" y="27" xlink:href="#doge-b"/><use x="82" y="27" xlink:href="#doge-b"/><use x="87" y="27" xlink:href="#doge-b"/><use x="102" y="27" xlink:href="#doge-b"/><use x="117" y="27" xlink:href="#doge-b"/><use x="127" y="27" xlink:href="#doge-b"/><use x="132" y="27" xlink:href="#doge-b"/><use x="137" y="27" xlink:href="#doge-b"/><use x="147" y="27" xlink:href="#doge-b"/><use x="7" y="32" xlink:href="#doge-b"/><use x="37" y="32" xlink:href="#doge-b"/><use x="47" y="32" xlink:href="#doge-b"/><use x="62" y="32" xlink:href="#doge-b"/><use x="67" y="32" xlink:href="#doge-b"/><use x="72" y="32" xlink:href="#doge-b"/><use x="77" y="32" xlink:href="#doge-b"/><use x="87" y="32" xlink:href="#doge-b"/><use x="102" y="32" xlink:href="#doge-b"/><use x="107" y="32" xlink:href="#doge-b"/><use x="117" y="32" xlink:href="#doge-b"/><use x="147" y="32" xlink:href="#doge-b"/><use x="7" y="37" xlink:href="#doge-b"/><use x="12" y="37" xlink:href="#doge-b"/><use x="17" y="37" xlink:href="#doge-b"/><use x="22" y="37" xlink:href="#doge-b"/><use x="27" y="37" xlink:href="#doge-b"/><use x="32" y="37" xlink:href="#doge-b"/><use x="37" y="37" xlink:href="#doge-b"/><use x="47" y="37" xlink:href="#doge-b"/><use x="57" y="37" xlink:href="#doge-b"/><use x="67" y="37" xlink:href="#doge-b"/><use x="77" y="37" xlink:href="#doge-b"/><use x="87" y="37" xlink:href="#doge-b"/><use x="97" y="37" xlink:href="#doge-b"/><use x="107" y="37" xlink:href="#doge-b"/><use x="117" y="37" xlink:href="#doge-b"/><use x="122" y="37" xlink:href="#doge-b"/><use x="127" y="37" xlink:href="#doge-b"/><use x="132" y="37" xlink:href="#doge-b"/><use x="137" y="37" xlink:href="#doge-b"/><use x="142" y="37" xlink:href="#doge-b"/><use x="147" y="37" xlink:href="#doge-b"/><use x="52" y="42" xlink:href="#doge-b"/><use x="67" y="42" xlink:href="#doge-b"/><use x="77" y="42" xlink:href="#doge-b"/><use x="82" y="42" xlink:href="#doge-b"/><use x="92" y="42" xlink:href="#doge-b"/><use x="97" y="42" xlink:href="#doge-b"/><use x="102" y="42" xlink:href="#doge-b"/><use x="107" y="42" xlink:href="#doge-b"/><use x="7" y="47" xlink:href="#doge-b"/><use x="12" y="47" xlink:href="#doge-b"/><use x="27" y="47" xlink:href="#doge-b"/><use x="32" y="47" xlink:href="#doge-b"/><use x="37" y="47" xlink:href="#doge-b"/><use x="62" y="47" xlink:href="#doge-b"/><use x="72" y="47" xlink:href="#doge-b"/><use x="77" y="47" xlink:href="#doge-b"/><use x="97" y="47" xlink:href="#doge-b"/><use x="102" y="47" xlink:href="#doge-b"/><use x="107" y="47" xlink:href="#doge-b"/><use x="122" y="47" xlink:href="#doge-b"/><use x="132" y="47" xlink:href="#doge-b"/><use x="137" y="47" xlink:href="#doge-b"/><use x="142" y="47" xlink:href="#doge-b"/><use x="147" y="47" xlink:href="#doge-b"/><use x="12" y="52" xlink:href="#doge-b"/><use x="22" y="52" xlink:href="#doge-b"/><use x="42" y="52" xlink:href="#doge-b"/><use x="47" y="52" xlink:href="#doge-b"/><use x="52" y="52" xlink:href="#doge-b"/><use x="57" y="52" xlink:href="#doge-b"/><use x="67" y="52" xlink:href="#doge-b"/><use x="82" y="52" xlink:href="#doge-b"/><use x="102" y="52" xlink:href="#doge-b"/><use x="107" y="52" xlink:href="#doge-b"/><use x="112" y="52" xlink:href="#doge-b"/><use x="117" y="52" xlink:href="#doge-b"/><use x="127" y="52" xlink:href="#doge-b"/><use x="132" y="52" xlink:href="#doge-b"/><use x="137" y="52" xlink:href="#doge-b"/><use x="7" y="57" xlink:href="#doge-b"/><use x="22" y="57" xlink:href="#doge-b"/><use x="37" y="57" xlink:href="#doge-b"/><use x="62" y="57" xlink:href="#doge-b"/><use x="67" y="57" xlink:href="#doge-b"/><use x="72" y="57" xlink:href="#doge-b"/><use x="77" y="57" xlink:href="#doge-b"/><use x="97" y="57" xlink:href="#doge-b"/><use x="102" y="57" xlink:href="#doge-b"/><use x="117" y="57" xlink:href="#doge-b"/><use x="127" y="57" xlink:href="#doge-b"/><use x="132" y="57" xlink:href="#doge-b"/><use x="137" y="57" xlink:href="#doge-b"/><use x="7" y="62" xlink:href="#doge-b"/><use x="17" y="62" xlink:href="#doge-b"/><use x="27" y="62" xlink:href="#doge-b"/><use x="32" y="62" xlink:href="#doge-b"/><use x="57" y="62" xlink:href="#doge-b"/><use x="62" y="62" xlink:href="#doge-b"/><use x="72" y="62" xlink:href="#doge-b"/><use x="82" y="62" xlink:href="#doge-b"/><use x="97" y="62" xlink:href="#doge-b"/><use x="102" y="62" xlink:href="#doge-b"/><use x="107" y="62" xlink:href="#doge-b"/><use x="122" y="62" xlink:href="#doge-b"/><use x="132" y="62" xlink:href="#doge-b"/><use x="142" y="62" xlink:href="#doge-b"/><use x="147" y="62" xlink:href="#doge-b"/><use x="7" y="67" xlink:href="#doge-b"/><use x="12" y="67" xlink:href="#doge-b"/><use x="17" y="67" xlink:href="#doge-b"/><use x="22" y="67" xlink:href="#doge-b"/><use x="27" y="67" xlink:href="#doge-b"/><use x="32" y="67" xlink:href="#doge-b"/><use x="37" y="67" xlink:href="#doge-b"/><use x="57" y="67" xlink:href="#doge-b"/><use x="67" y="67" xlink:href="#doge-b"/><use x="72" y="67" xlink:href="#doge-b"/><use x="87" y="67" xlink:href="#doge-b"/><use x="97" y="67" xlink:href="#doge-b"/><use x="102" y="67" xlink:href="#doge-b"/><use x="117" y="67" xlink:href="#doge-b"/><use x="122" y="67" xlink:href="#doge-b"/><use x="127" y="67" xlink:href="#doge-b"/><use x="142" y="67" xlink:href="#doge-b"/><use x="7" y="72" xlink:href="#doge-b"/><use x="12" y="72" xlink:href="#doge-b"/><use x="17" y="72" xlink:href="#doge-b"/><use x="27" y="72" xlink:href="#doge-b"/><use x="32" y="72" xlink:href="#doge-b"/><use x="52" y="72" xlink:href="#doge-b"/><use x="72" y="72" xlink:href="#doge-b"/><use x="77" y="72" xlink:href="#doge-b"/><use x="97" y="72" xlink:href="#doge-b"/><use x="107" y="72" xlink:href="#doge-b"/><use x="122" y="72" xlink:href="#doge-b"/><use x="137" y="72" xlink:href="#doge-b"/><use x="7" y="77" xlink:href="#doge-b"/><use x="12" y="77" xlink:href="#doge-b"/><use x="22" y="77" xlink:href="#doge-b"/><use x="37" y="77" xlink:href="#doge-b"/><use x="42" y="77" xlink:href="#doge-b"/><use x="47" y="77" xlink:href="#doge-b"/><use x="82" y="77" xlink:href="#doge-b"/><use x="97" y="77" xlink:href="#doge-b"/><use x="117" y="77" xlink:href="#doge-b"/><use x="122" y="77" xlink:href="#doge-b"/><use x="127" y="77" xlink:href="#doge-b"/><use x="132" y="77" xlink:href="#doge-b"/><use x="137" y="77" xlink:href="#doge-b"/><use x="147" y="77" xlink:href="#doge-b"/><use x="7" y="82" xlink:href="#doge-b"/><use x="17" y="82" xlink:href="#doge-b"/><use x="22" y="82" xlink:href="#doge-b"/><use x="27" y="82" xlink:href="#doge-b"/><use x="42" y="82" xlink:href="#doge-b"/><use x="47" y="82" xlink:href="#doge-b"/><use x="67" y="82" xlink:href="#doge-b"/><use x="77" y="82" xlink:href="#doge-b"/><use x="87" y="82" xlink:href="#doge-b"/><use x="92" y="82" xlink:href="#doge-b"/><use x="97" y="82" xlink:href="#doge-b"/><use x="107" y="82" xlink:href="#doge-b"/><use x="117" y="82" xlink:href="#doge-b"/><use x="132" y="82" xlink:href="#doge-b"/><use x="142" y="82" xlink:href="#doge-b"/><use x="147" y="82" xlink:href="#doge-b"/><use x="7" y="87" xlink:href="#doge-b"/><use x="32" y="87" xlink:href="#doge-b"/><use x="37" y="87" xlink:href="#doge-b"/><use x="42" y="87" xlink:href="#doge-b"/><use x="62" y="87" xlink:href="#doge-b"/><use x="72" y="87" xlink:href="#doge-b"/><use x="77" y="87" xlink:href="#doge-b"/><use x="97" y="87" xlink:href="#doge-b"/><use x="102" y="87" xlink:href="#doge-b"/><use x="107" y="87" xlink:href="#doge-b"/><use x="122" y="87" xlink:href="#doge-b"/><use x="127" y="87" xlink:href="#doge-b"/><use x="132" y="87" xlink:href="#doge-b"/><use x="137" y="87" xlink:href="#doge-b"/><use x="142" y="87" xlink:href="#doge-b"/><use x="7" y="92" xlink:href="#doge-b"/><use x="12" y="92" xlink:href="#doge-b"/><use x="22" y="92" xlink:href="#doge-b"/><use x="52" y="92" xlink:href="#doge-b"/><use x="57" y="92" xlink:href="#doge-b"/><use x="67" y="92" xlink:href="#doge-b"/><use x="82" y="92" xlink:href="#doge-b"/><use x="87" y="92" xlink:href="#doge-b"/><use x="102" y="92" xlink:href="#doge-b"/><use x="107" y="92" xlink:href="#doge-b"/><use x="112" y="92" xlink:href="#doge-b"/><use x="127" y="92" xlink:href="#doge-b"/><use x="137" y="92" xlink:href="#doge-b"/><use x="147" y="92" xlink:href="#doge-b"/><use x="17" y="97" xlink:href="#doge-b"/><use x="27" y="97" xlink:href="#doge-b"/><use x="37" y="97" xlink:href="#doge-b"/><use x="42" y="97" xlink:href="#doge-b"/><use x="47" y="97" xlink:href="#doge-b"/><use x="52" y="97" xlink:href="#doge-b"/><use x="57" y="97" xlink:href="#doge-b"/><use x="62" y="97" xlink:href="#doge-b"/><use x="67" y="97" xlink:href="#doge-b"/><use x="72" y="97" xlink:href="#doge-b"/><use x="77" y="97" xlink:href="#doge-b"/><use x="87" y="97" xlink:href="#doge-b"/><use x="92" y="97" xlink:href="#doge-b"/><use x="97" y="97" xlink:href="#doge-b"/><use x="102" y="97" xlink:href="#doge-b"/><use x="107" y="97" xlink:href="#doge-b"/><use x="117" y="97" xlink:href="#doge-b"/><use x="127" y="97" xlink:href="#doge-b"/><use x="132" y="97" xlink:href="#doge-b"/><use x="137" y="97" xlink:href="#doge-b"/><use x="142" y="97" xlink:href="#doge-b"/><use x="147" y="97" xlink:href="#doge-b"/><use x="27" y="102" xlink:href="#doge-b"/><use x="32" y="102" xlink:href="#doge-b"/><use x="42" y="102" xlink:href="#doge-b"/><use x="62" y="102" xlink:href="#doge-b"/><use x="72" y="102" xlink:href="#doge-b"/><use x="92" y="102" xlink:href="#doge-b"/><use x="97" y="102" xlink:href="#doge-b"/><use x="107" y="102" xlink:href="#doge-b"/><use x="112" y="102" xlink:href="#doge-b"/><use x="132" y="102" xlink:href="#doge-b"/><use x="142" y="102" xlink:href="#doge-b"/><use x="7" y="107" xlink:href="#doge-b"/><use x="12" y="107" xlink:href="#doge-b"/><use x="22" y="107" xlink:href="#doge-b"/><use x="37" y="107" xlink:href="#doge-b"/><use x="42" y="107" xlink:href="#doge-b"/><use x="57" y="107" xlink:href="#doge-b"/><use x="67" y="107" xlink:href="#doge-b"/><use x="72" y="107" xlink:href="#doge-b"/><use x="87" y="107" xlink:href="#doge-b"/><use x="102" y="107" xlink:href="#doge-b"/><use x="107" y="107" xlink:href="#doge-b"/><use x="112" y="107" xlink:href="#doge-b"/><use x="117" y="107" xlink:href="#doge-b"/><use x="122" y="107" xlink:href="#doge-b"/><use x="127" y="107" xlink:href="#doge-b"/><use x="137" y="107" xlink:href="#doge-b"/><use x="47" y="112" xlink:href="#doge-b"/><use x="57" y="112" xlink:href="#doge-b"/><use x="72" y="112" xlink:href="#doge-b"/><use x="77" y="112" xlink:href="#doge-b"/><use x="82" y="112" xlink:href="#doge-b"/><use x="102" y="112" xlink:href="#doge-b"/><use x="107" y="112" xlink:href="#doge-b"/><use x="127" y="112" xlink:href="#doge-b"/><use x="137" y="112" xlink:href="#doge-b"/><use x="7" y="117" xlink:href="#doge-b"/><use x="12" y="117" xlink:href="#doge-b"/><use x="17" y="117" xlink:href="#doge-b"/><use x="22" y="117" xlink:href="#doge-b"/><use x="27" y="117" xlink:href="#doge-b"/><use x="32" y="117" xlink:href="#doge-b"/><use x="37" y="117" xlink:href="#doge-b"/><use x="82" y="117" xlink:href="#doge-b"/><use x="87" y="117" xlink:href="#doge-b"/><use x="92" y="117" xlink:href="#doge-b"/><use x="97" y="117" xlink:href="#doge-b"/><use x="107" y="117" xlink:href="#doge-b"/><use x="117" y="117" xlink:href="#doge-b"/><use x="127" y="117" xlink:href="#doge-b"/><use x="137" y="117" xlink:href="#doge-b"/><use x="147" y="117" xlink:href="#doge-b"/><use x="7" y="122" xlink:href="#doge-b"/><use x="37" y="122" xlink:href="#doge-b"/><use x="47" y="122" xlink:href="#doge-b"/><use x="52" y="122" xlink:href="#doge-b"/><use x="57" y="122" xlink:href="#doge-b"/><use x="67" y="122" xlink:href="#doge-b"/><use x="77" y="122" xlink:href="#doge-b"/><use x="82" y="122" xlink:href="#doge-b"/><use x="92" y="122" xlink:href="#doge-b"/><use x="102" y="122" xlink:href="#doge-b"/><use x="107" y="122" xlink:href="#doge-b"/><use x="127" y="122" xlink:href="#doge-b"/><use x="137" y="122" xlink:href="#doge-b"/><use x="142" y="122" xlink:href="#doge-b"/><use x="7" y="127" xlink:href="#doge-b"/><use x="17" y="127" xlink:href="#doge-b"/><use x="22" y="127" xlink:href="#doge-b"/><use x="27" y="127" xlink:href="#doge-b"/><use x="37" y="127" xlink:href="#doge-b"/><use x="47" y="127" xlink:href="#doge-b"/><use x="52" y="127" xlink:href="#doge-b"/><use x="57" y="127" xlink:href="#doge-b"/><use x="62" y="127" xlink:href="#doge-b"/><use x="72" y="127" xlink:href="#doge-b"/><use x="77" y="127" xlink:href="#doge-b"/><use x="87" y="127" xlink:href="#doge-b"/><use x="92" y="127" xlink:href="#doge-b"/><use x="102" y="127" xlink:href="#doge-b"/><use x="107" y="127" xlink:href="#doge-b"/><use x="112" y="127" xlink:href="#doge-b"/><use x="117" y="127" xlink:href="#doge-b"/><use x="122" y="127" xlink:href="#doge-b"/><use x="127" y="127" xlink:href="#doge-b"/><use x="137" y="127" xlink:href="#doge-b"/><use x="147" y="127" xlink:href="#doge-b"/><use x="7" y="132" xlink:href="#doge-b"/><use x="17" y="132" xlink:href="#doge-b"/><use x="22" y="132" xlink:href="#doge-b"/><use x="27" y="132" xlink:href="#doge-b"/><use x="37" y="132" xlink:href="#doge-b"/><use x="52" y="132" xlink:href="#doge-b"/><use x="57" y="132" xlink:href="#doge-b"/><use x="67" y="132" xlink:href="#doge-b"/><use x="102" y="132" xlink:href="#doge-b"/><use x="107" y="132" xlink:href="#doge-b"/><use x="117" y="132" xlink:href="#doge-b"/><use x="122" y="132" xlink:href="#doge-b"/><use x="137" y="132" xlink:href="#doge-b"/><use x="142" y="132" xlink:href="#doge-b"/><use x="7" y="137" xlink:href="#doge-b"/><use x="17" y="137" xlink:href="#doge-b"/><use x="22" y="137" xlink:href="#doge-b"/><use x="27" y="137" xlink:href="#doge-b"/><use x="37" y="137" xlink:href="#doge-b"/><use x="57" y="137" xlink:href="#doge-b"/><use x="62" y="137" xlink:href="#doge-b"/><use x="67" y="137" xlink:href="#doge-b"/><use x="72" y="137" xlink:href="#doge-b"/><use x="77" y="137" xlink:href="#doge-b"/><use x="82" y="137" xlink:href="#doge-b"/><use x="87" y="137" xlink:href="#doge-b"/><use x="92" y="137" xlink:href="#doge-b"/><use x="97" y="137" xlink:href="#doge-b"/><use x="102" y="137" xlink:href="#doge-b"/><use x="112" y="137" xlink:href="#doge-b"/><use x="122" y="137" xlink:href="#doge-b"/><use x="132" y="137" xlink:href="#doge-b"/><use x="142" y="137" xlink:href="#doge-b"/><use x="147" y="137" xlink:href="#doge-b"/><use x="7" y="142" xlink:href="#doge-b"/><use x="37" y="142" xlink:href="#doge-b"/><use x="47" y="142" xlink:href="#doge-b"/><use x="52" y="142" xlink:href="#doge-b"/><use x="57" y="142" xlink:href="#doge-b"/><use x="62" y="142" xlink:href="#doge-b"/><use x="72" y="142" xlink:href="#doge-b"/><use x="82" y="142" xlink:href="#doge-b"/><use x="102" y="142" xlink:href="#doge-b"/><use x="117" y="142" xlink:href="#doge-b"/><use x="122" y="142" xlink:href="#doge-b"/><use x="137" y="142" xlink:href="#doge-b"/><use x="7" y="147" xlink:href="#doge-b"/><use x="12" y="147" xlink:href="#doge-b"/><use x="17" y="147" xlink:href="#doge-b"/><use x="22" y="147" xlink:href="#doge-b"/><use x="27" y="147" xlink:href="#doge-b"/><use x="32" y="147" xlink:href="#doge-b"/><use x="37" y="147" xlink:href="#doge-b"/><use x="47" y="147" xlink:href="#doge-b"/><use x="52" y="147" xlink:href="#doge-b"/><use x="67" y="147" xlink:href="#doge-b"/><use x="72" y="147" xlink:href="#doge-b"/><use x="87" y="147" xlink:href="#doge-b"/><use x="122" y="147" xlink:href="#doge-b"/><use x="127" y="147" xlink:href="#doge-b"/><use x="137" y="147" xlink:href="#doge-b"/><use x="142" y="147" xlink:href="#doge-b"/></svg>`}
              {:else}
                {@html `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" version="1.1" width="160px" height="160px" viewBox="0 0 160 160"><defs><rect id="eth-b" width="5" height="5" fill="#4f6587" fill-opacity="1"/></defs><rect x="0" y="0" width="160" height="160" fill="#ffffff" fill-opacity="1"/><use x="7" y="7" xlink:href="#eth-b"/><use x="12" y="7" xlink:href="#eth-b"/><use x="17" y="7" xlink:href="#eth-b"/><use x="22" y="7" xlink:href="#eth-b"/><use x="27" y="7" xlink:href="#eth-b"/><use x="32" y="7" xlink:href="#eth-b"/><use x="37" y="7" xlink:href="#eth-b"/><use x="57" y="7" xlink:href="#eth-b"/><use x="67" y="7" xlink:href="#eth-b"/><use x="77" y="7" xlink:href="#eth-b"/><use x="82" y="7" xlink:href="#eth-b"/><use x="97" y="7" xlink:href="#eth-b"/><use x="102" y="7" xlink:href="#eth-b"/><use x="107" y="7" xlink:href="#eth-b"/><use x="117" y="7" xlink:href="#eth-b"/><use x="122" y="7" xlink:href="#eth-b"/><use x="127" y="7" xlink:href="#eth-b"/><use x="132" y="7" xlink:href="#eth-b"/><use x="137" y="7" xlink:href="#eth-b"/><use x="142" y="7" xlink:href="#eth-b"/><use x="147" y="7" xlink:href="#eth-b"/><use x="7" y="12" xlink:href="#eth-b"/><use x="37" y="12" xlink:href="#eth-b"/><use x="47" y="12" xlink:href="#eth-b"/><use x="57" y="12" xlink:href="#eth-b"/><use x="77" y="12" xlink:href="#eth-b"/><use x="82" y="12" xlink:href="#eth-b"/><use x="87" y="12" xlink:href="#eth-b"/><use x="92" y="12" xlink:href="#eth-b"/><use x="97" y="12" xlink:href="#eth-b"/><use x="107" y="12" xlink:href="#eth-b"/><use x="117" y="12" xlink:href="#eth-b"/><use x="147" y="12" xlink:href="#eth-b"/><use x="7" y="17" xlink:href="#eth-b"/><use x="17" y="17" xlink:href="#eth-b"/><use x="22" y="17" xlink:href="#eth-b"/><use x="27" y="17" xlink:href="#eth-b"/><use x="37" y="17" xlink:href="#eth-b"/><use x="67" y="17" xlink:href="#eth-b"/><use x="92" y="17" xlink:href="#eth-b"/><use x="102" y="17" xlink:href="#eth-b"/><use x="117" y="17" xlink:href="#eth-b"/><use x="127" y="17" xlink:href="#eth-b"/><use x="132" y="17" xlink:href="#eth-b"/><use x="137" y="17" xlink:href="#eth-b"/><use x="147" y="17" xlink:href="#eth-b"/><use x="7" y="22" xlink:href="#eth-b"/><use x="17" y="22" xlink:href="#eth-b"/><use x="22" y="22" xlink:href="#eth-b"/><use x="27" y="22" xlink:href="#eth-b"/><use x="37" y="22" xlink:href="#eth-b"/><use x="47" y="22" xlink:href="#eth-b"/><use x="52" y="22" xlink:href="#eth-b"/><use x="57" y="22" xlink:href="#eth-b"/><use x="67" y="22" xlink:href="#eth-b"/><use x="72" y="22" xlink:href="#eth-b"/><use x="82" y="22" xlink:href="#eth-b"/><use x="87" y="22" xlink:href="#eth-b"/><use x="97" y="22" xlink:href="#eth-b"/><use x="117" y="22" xlink:href="#eth-b"/><use x="127" y="22" xlink:href="#eth-b"/><use x="132" y="22" xlink:href="#eth-b"/><use x="137" y="22" xlink:href="#eth-b"/><use x="147" y="22" xlink:href="#eth-b"/><use x="7" y="27" xlink:href="#eth-b"/><use x="17" y="27" xlink:href="#eth-b"/><use x="22" y="27" xlink:href="#eth-b"/><use x="27" y="27" xlink:href="#eth-b"/><use x="37" y="27" xlink:href="#eth-b"/><use x="52" y="27" xlink:href="#eth-b"/><use x="77" y="27" xlink:href="#eth-b"/><use x="82" y="27" xlink:href="#eth-b"/><use x="87" y="27" xlink:href="#eth-b"/><use x="97" y="27" xlink:href="#eth-b"/><use x="102" y="27" xlink:href="#eth-b"/><use x="107" y="27" xlink:href="#eth-b"/><use x="117" y="27" xlink:href="#eth-b"/><use x="127" y="27" xlink:href="#eth-b"/><use x="132" y="27" xlink:href="#eth-b"/><use x="137" y="27" xlink:href="#eth-b"/><use x="147" y="27" xlink:href="#eth-b"/><use x="7" y="32" xlink:href="#eth-b"/><use x="37" y="32" xlink:href="#eth-b"/><use x="47" y="32" xlink:href="#eth-b"/><use x="52" y="32" xlink:href="#eth-b"/><use x="62" y="32" xlink:href="#eth-b"/><use x="67" y="32" xlink:href="#eth-b"/><use x="77" y="32" xlink:href="#eth-b"/><use x="82" y="32" xlink:href="#eth-b"/><use x="92" y="32" xlink:href="#eth-b"/><use x="97" y="32" xlink:href="#eth-b"/><use x="117" y="32" xlink:href="#eth-b"/><use x="147" y="32" xlink:href="#eth-b"/><use x="7" y="37" xlink:href="#eth-b"/><use x="12" y="37" xlink:href="#eth-b"/><use x="17" y="37" xlink:href="#eth-b"/><use x="22" y="37" xlink:href="#eth-b"/><use x="27" y="37" xlink:href="#eth-b"/><use x="32" y="37" xlink:href="#eth-b"/><use x="37" y="37" xlink:href="#eth-b"/><use x="47" y="37" xlink:href="#eth-b"/><use x="57" y="37" xlink:href="#eth-b"/><use x="67" y="37" xlink:href="#eth-b"/><use x="77" y="37" xlink:href="#eth-b"/><use x="87" y="37" xlink:href="#eth-b"/><use x="97" y="37" xlink:href="#eth-b"/><use x="107" y="37" xlink:href="#eth-b"/><use x="117" y="37" xlink:href="#eth-b"/><use x="122" y="37" xlink:href="#eth-b"/><use x="127" y="37" xlink:href="#eth-b"/><use x="132" y="37" xlink:href="#eth-b"/><use x="137" y="37" xlink:href="#eth-b"/><use x="142" y="37" xlink:href="#eth-b"/><use x="147" y="37" xlink:href="#eth-b"/><use x="52" y="42" xlink:href="#eth-b"/><use x="57" y="42" xlink:href="#eth-b"/><use x="62" y="42" xlink:href="#eth-b"/><use x="87" y="42" xlink:href="#eth-b"/><use x="102" y="42" xlink:href="#eth-b"/><use x="107" y="42" xlink:href="#eth-b"/><use x="7" y="47" xlink:href="#eth-b"/><use x="12" y="47" xlink:href="#eth-b"/><use x="17" y="47" xlink:href="#eth-b"/><use x="22" y="47" xlink:href="#eth-b"/><use x="27" y="47" xlink:href="#eth-b"/><use x="37" y="47" xlink:href="#eth-b"/><use x="42" y="47" xlink:href="#eth-b"/><use x="47" y="47" xlink:href="#eth-b"/><use x="52" y="47" xlink:href="#eth-b"/><use x="62" y="47" xlink:href="#eth-b"/><use x="82" y="47" xlink:href="#eth-b"/><use x="112" y="47" xlink:href="#eth-b"/><use x="122" y="47" xlink:href="#eth-b"/><use x="132" y="47" xlink:href="#eth-b"/><use x="142" y="47" xlink:href="#eth-b"/><use x="7" y="52" xlink:href="#eth-b"/><use x="12" y="52" xlink:href="#eth-b"/><use x="17" y="52" xlink:href="#eth-b"/><use x="27" y="52" xlink:href="#eth-b"/><use x="42" y="52" xlink:href="#eth-b"/><use x="57" y="52" xlink:href="#eth-b"/><use x="67" y="52" xlink:href="#eth-b"/><use x="77" y="52" xlink:href="#eth-b"/><use x="112" y="52" xlink:href="#eth-b"/><use x="117" y="52" xlink:href="#eth-b"/><use x="127" y="52" xlink:href="#eth-b"/><use x="142" y="52" xlink:href="#eth-b"/><use x="7" y="57" xlink:href="#eth-b"/><use x="17" y="57" xlink:href="#eth-b"/><use x="27" y="57" xlink:href="#eth-b"/><use x="37" y="57" xlink:href="#eth-b"/><use x="42" y="57" xlink:href="#eth-b"/><use x="47" y="57" xlink:href="#eth-b"/><use x="57" y="57" xlink:href="#eth-b"/><use x="72" y="57" xlink:href="#eth-b"/><use x="82" y="57" xlink:href="#eth-b"/><use x="92" y="57" xlink:href="#eth-b"/><use x="102" y="57" xlink:href="#eth-b"/><use x="107" y="57" xlink:href="#eth-b"/><use x="132" y="57" xlink:href="#eth-b"/><use x="137" y="57" xlink:href="#eth-b"/><use x="142" y="57" xlink:href="#eth-b"/><use x="147" y="57" xlink:href="#eth-b"/><use x="7" y="62" xlink:href="#eth-b"/><use x="12" y="62" xlink:href="#eth-b"/><use x="17" y="62" xlink:href="#eth-b"/><use x="27" y="62" xlink:href="#eth-b"/><use x="42" y="62" xlink:href="#eth-b"/><use x="47" y="62" xlink:href="#eth-b"/><use x="67" y="62" xlink:href="#eth-b"/><use x="77" y="62" xlink:href="#eth-b"/><use x="82" y="62" xlink:href="#eth-b"/><use x="87" y="62" xlink:href="#eth-b"/><use x="97" y="62" xlink:href="#eth-b"/><use x="102" y="62" xlink:href="#eth-b"/><use x="112" y="62" xlink:href="#eth-b"/><use x="122" y="62" xlink:href="#eth-b"/><use x="127" y="62" xlink:href="#eth-b"/><use x="137" y="62" xlink:href="#eth-b"/><use x="147" y="62" xlink:href="#eth-b"/><use x="12" y="67" xlink:href="#eth-b"/><use x="22" y="67" xlink:href="#eth-b"/><use x="32" y="67" xlink:href="#eth-b"/><use x="37" y="67" xlink:href="#eth-b"/><use x="47" y="67" xlink:href="#eth-b"/><use x="52" y="67" xlink:href="#eth-b"/><use x="57" y="67" xlink:href="#eth-b"/><use x="67" y="67" xlink:href="#eth-b"/><use x="82" y="67" xlink:href="#eth-b"/><use x="92" y="67" xlink:href="#eth-b"/><use x="107" y="67" xlink:href="#eth-b"/><use x="122" y="67" xlink:href="#eth-b"/><use x="17" y="72" xlink:href="#eth-b"/><use x="52" y="72" xlink:href="#eth-b"/><use x="77" y="72" xlink:href="#eth-b"/><use x="82" y="72" xlink:href="#eth-b"/><use x="87" y="72" xlink:href="#eth-b"/><use x="97" y="72" xlink:href="#eth-b"/><use x="102" y="72" xlink:href="#eth-b"/><use x="112" y="72" xlink:href="#eth-b"/><use x="117" y="72" xlink:href="#eth-b"/><use x="122" y="72" xlink:href="#eth-b"/><use x="127" y="72" xlink:href="#eth-b"/><use x="132" y="72" xlink:href="#eth-b"/><use x="142" y="72" xlink:href="#eth-b"/><use x="22" y="77" xlink:href="#eth-b"/><use x="32" y="77" xlink:href="#eth-b"/><use x="37" y="77" xlink:href="#eth-b"/><use x="42" y="77" xlink:href="#eth-b"/><use x="47" y="77" xlink:href="#eth-b"/><use x="52" y="77" xlink:href="#eth-b"/><use x="57" y="77" xlink:href="#eth-b"/><use x="62" y="77" xlink:href="#eth-b"/><use x="67" y="77" xlink:href="#eth-b"/><use x="72" y="77" xlink:href="#eth-b"/><use x="82" y="77" xlink:href="#eth-b"/><use x="92" y="77" xlink:href="#eth-b"/><use x="122" y="77" xlink:href="#eth-b"/><use x="142" y="77" xlink:href="#eth-b"/><use x="7" y="82" xlink:href="#eth-b"/><use x="17" y="82" xlink:href="#eth-b"/><use x="32" y="82" xlink:href="#eth-b"/><use x="47" y="82" xlink:href="#eth-b"/><use x="57" y="82" xlink:href="#eth-b"/><use x="62" y="82" xlink:href="#eth-b"/><use x="77" y="82" xlink:href="#eth-b"/><use x="87" y="82" xlink:href="#eth-b"/><use x="97" y="82" xlink:href="#eth-b"/><use x="107" y="82" xlink:href="#eth-b"/><use x="112" y="82" xlink:href="#eth-b"/><use x="127" y="82" xlink:href="#eth-b"/><use x="147" y="82" xlink:href="#eth-b"/><use x="7" y="87" xlink:href="#eth-b"/><use x="12" y="87" xlink:href="#eth-b"/><use x="17" y="87" xlink:href="#eth-b"/><use x="27" y="87" xlink:href="#eth-b"/><use x="37" y="87" xlink:href="#eth-b"/><use x="47" y="87" xlink:href="#eth-b"/><use x="57" y="87" xlink:href="#eth-b"/><use x="62" y="87" xlink:href="#eth-b"/><use x="77" y="87" xlink:href="#eth-b"/><use x="82" y="87" xlink:href="#eth-b"/><use x="97" y="87" xlink:href="#eth-b"/><use x="107" y="87" xlink:href="#eth-b"/><use x="127" y="87" xlink:href="#eth-b"/><use x="132" y="87" xlink:href="#eth-b"/><use x="142" y="87" xlink:href="#eth-b"/><use x="7" y="92" xlink:href="#eth-b"/><use x="12" y="92" xlink:href="#eth-b"/><use x="22" y="92" xlink:href="#eth-b"/><use x="27" y="92" xlink:href="#eth-b"/><use x="42" y="92" xlink:href="#eth-b"/><use x="57" y="92" xlink:href="#eth-b"/><use x="67" y="92" xlink:href="#eth-b"/><use x="102" y="92" xlink:href="#eth-b"/><use x="112" y="92" xlink:href="#eth-b"/><use x="117" y="92" xlink:href="#eth-b"/><use x="122" y="92" xlink:href="#eth-b"/><use x="127" y="92" xlink:href="#eth-b"/><use x="142" y="92" xlink:href="#eth-b"/><use x="147" y="92" xlink:href="#eth-b"/><use x="7" y="97" xlink:href="#eth-b"/><use x="17" y="97" xlink:href="#eth-b"/><use x="22" y="97" xlink:href="#eth-b"/><use x="27" y="97" xlink:href="#eth-b"/><use x="37" y="97" xlink:href="#eth-b"/><use x="42" y="97" xlink:href="#eth-b"/><use x="77" y="97" xlink:href="#eth-b"/><use x="82" y="97" xlink:href="#eth-b"/><use x="87" y="97" xlink:href="#eth-b"/><use x="92" y="97" xlink:href="#eth-b"/><use x="97" y="97" xlink:href="#eth-b"/><use x="107" y="97" xlink:href="#eth-b"/><use x="122" y="97" xlink:href="#eth-b"/><use x="132" y="97" xlink:href="#eth-b"/><use x="137" y="97" xlink:href="#eth-b"/><use x="142" y="97" xlink:href="#eth-b"/><use x="147" y="97" xlink:href="#eth-b"/><use x="7" y="102" xlink:href="#eth-b"/><use x="22" y="102" xlink:href="#eth-b"/><use x="32" y="102" xlink:href="#eth-b"/><use x="42" y="102" xlink:href="#eth-b"/><use x="47" y="102" xlink:href="#eth-b"/><use x="52" y="102" xlink:href="#eth-b"/><use x="67" y="102" xlink:href="#eth-b"/><use x="102" y="102" xlink:href="#eth-b"/><use x="112" y="102" xlink:href="#eth-b"/><use x="127" y="102" xlink:href="#eth-b"/><use x="142" y="102" xlink:href="#eth-b"/><use x="147" y="102" xlink:href="#eth-b"/><use x="7" y="107" xlink:href="#eth-b"/><use x="22" y="107" xlink:href="#eth-b"/><use x="32" y="107" xlink:href="#eth-b"/><use x="37" y="107" xlink:href="#eth-b"/><use x="42" y="107" xlink:href="#eth-b"/><use x="52" y="107" xlink:href="#eth-b"/><use x="67" y="107" xlink:href="#eth-b"/><use x="72" y="107" xlink:href="#eth-b"/><use x="77" y="107" xlink:href="#eth-b"/><use x="82" y="107" xlink:href="#eth-b"/><use x="87" y="107" xlink:href="#eth-b"/><use x="97" y="107" xlink:href="#eth-b"/><use x="107" y="107" xlink:href="#eth-b"/><use x="112" y="107" xlink:href="#eth-b"/><use x="117" y="107" xlink:href="#eth-b"/><use x="122" y="107" xlink:href="#eth-b"/><use x="127" y="107" xlink:href="#eth-b"/><use x="137" y="107" xlink:href="#eth-b"/><use x="142" y="107" xlink:href="#eth-b"/><use x="47" y="112" xlink:href="#eth-b"/><use x="57" y="112" xlink:href="#eth-b"/><use x="82" y="112" xlink:href="#eth-b"/><use x="87" y="112" xlink:href="#eth-b"/><use x="97" y="112" xlink:href="#eth-b"/><use x="107" y="112" xlink:href="#eth-b"/><use x="127" y="112" xlink:href="#eth-b"/><use x="142" y="112" xlink:href="#eth-b"/><use x="7" y="117" xlink:href="#eth-b"/><use x="12" y="117" xlink:href="#eth-b"/><use x="17" y="117" xlink:href="#eth-b"/><use x="22" y="117" xlink:href="#eth-b"/><use x="27" y="117" xlink:href="#eth-b"/><use x="32" y="117" xlink:href="#eth-b"/><use x="37" y="117" xlink:href="#eth-b"/><use x="47" y="117" xlink:href="#eth-b"/><use x="57" y="117" xlink:href="#eth-b"/><use x="62" y="117" xlink:href="#eth-b"/><use x="67" y="117" xlink:href="#eth-b"/><use x="72" y="117" xlink:href="#eth-b"/><use x="82" y="117" xlink:href="#eth-b"/><use x="92" y="117" xlink:href="#eth-b"/><use x="97" y="117" xlink:href="#eth-b"/><use x="107" y="117" xlink:href="#eth-b"/><use x="117" y="117" xlink:href="#eth-b"/><use x="127" y="117" xlink:href="#eth-b"/><use x="132" y="117" xlink:href="#eth-b"/><use x="137" y="117" xlink:href="#eth-b"/><use x="7" y="122" xlink:href="#eth-b"/><use x="37" y="122" xlink:href="#eth-b"/><use x="57" y="122" xlink:href="#eth-b"/><use x="62" y="122" xlink:href="#eth-b"/><use x="77" y="122" xlink:href="#eth-b"/><use x="82" y="122" xlink:href="#eth-b"/><use x="87" y="122" xlink:href="#eth-b"/><use x="92" y="122" xlink:href="#eth-b"/><use x="107" y="122" xlink:href="#eth-b"/><use x="127" y="122" xlink:href="#eth-b"/><use x="137" y="122" xlink:href="#eth-b"/><use x="142" y="122" xlink:href="#eth-b"/><use x="147" y="122" xlink:href="#eth-b"/><use x="7" y="127" xlink:href="#eth-b"/><use x="17" y="127" xlink:href="#eth-b"/><use x="22" y="127" xlink:href="#eth-b"/><use x="27" y="127" xlink:href="#eth-b"/><use x="37" y="127" xlink:href="#eth-b"/><use x="47" y="127" xlink:href="#eth-b"/><use x="52" y="127" xlink:href="#eth-b"/><use x="62" y="127" xlink:href="#eth-b"/><use x="67" y="127" xlink:href="#eth-b"/><use x="72" y="127" xlink:href="#eth-b"/><use x="82" y="127" xlink:href="#eth-b"/><use x="97" y="127" xlink:href="#eth-b"/><use x="107" y="127" xlink:href="#eth-b"/><use x="112" y="127" xlink:href="#eth-b"/><use x="117" y="127" xlink:href="#eth-b"/><use x="122" y="127" xlink:href="#eth-b"/><use x="127" y="127" xlink:href="#eth-b"/><use x="142" y="127" xlink:href="#eth-b"/><use x="147" y="127" xlink:href="#eth-b"/><use x="7" y="132" xlink:href="#eth-b"/><use x="17" y="132" xlink:href="#eth-b"/><use x="22" y="132" xlink:href="#eth-b"/><use x="27" y="132" xlink:href="#eth-b"/><use x="37" y="132" xlink:href="#eth-b"/><use x="47" y="132" xlink:href="#eth-b"/><use x="67" y="132" xlink:href="#eth-b"/><use x="87" y="132" xlink:href="#eth-b"/><use x="97" y="132" xlink:href="#eth-b"/><use x="102" y="132" xlink:href="#eth-b"/><use x="107" y="132" xlink:href="#eth-b"/><use x="122" y="132" xlink:href="#eth-b"/><use x="132" y="132" xlink:href="#eth-b"/><use x="7" y="137" xlink:href="#eth-b"/><use x="17" y="137" xlink:href="#eth-b"/><use x="22" y="137" xlink:href="#eth-b"/><use x="27" y="137" xlink:href="#eth-b"/><use x="37" y="137" xlink:href="#eth-b"/><use x="47" y="137" xlink:href="#eth-b"/><use x="52" y="137" xlink:href="#eth-b"/><use x="67" y="137" xlink:href="#eth-b"/><use x="72" y="137" xlink:href="#eth-b"/><use x="82" y="137" xlink:href="#eth-b"/><use x="87" y="137" xlink:href="#eth-b"/><use x="92" y="137" xlink:href="#eth-b"/><use x="97" y="137" xlink:href="#eth-b"/><use x="112" y="137" xlink:href="#eth-b"/><use x="117" y="137" xlink:href="#eth-b"/><use x="127" y="137" xlink:href="#eth-b"/><use x="137" y="137" xlink:href="#eth-b"/><use x="142" y="137" xlink:href="#eth-b"/><use x="7" y="142" xlink:href="#eth-b"/><use x="37" y="142" xlink:href="#eth-b"/><use x="47" y="142" xlink:href="#eth-b"/><use x="52" y="142" xlink:href="#eth-b"/><use x="67" y="142" xlink:href="#eth-b"/><use x="77" y="142" xlink:href="#eth-b"/><use x="102" y="142" xlink:href="#eth-b"/><use x="132" y="142" xlink:href="#eth-b"/><use x="147" y="142" xlink:href="#eth-b"/><use x="7" y="147" xlink:href="#eth-b"/><use x="12" y="147" xlink:href="#eth-b"/><use x="17" y="147" xlink:href="#eth-b"/><use x="22" y="147" xlink:href="#eth-b"/><use x="27" y="147" xlink:href="#eth-b"/><use x="32" y="147" xlink:href="#eth-b"/><use x="37" y="147" xlink:href="#eth-b"/><use x="47" y="147" xlink:href="#eth-b"/><use x="72" y="147" xlink:href="#eth-b"/><use x="77" y="147" xlink:href="#eth-b"/><use x="82" y="147" xlink:href="#eth-b"/><use x="87" y="147" xlink:href="#eth-b"/><use x="92" y="147" xlink:href="#eth-b"/><use x="97" y="147" xlink:href="#eth-b"/><use x="112" y="147" xlink:href="#eth-b"/><use x="122" y="147" xlink:href="#eth-b"/><use x="127" y="147" xlink:href="#eth-b"/><use x="137" y="147" xlink:href="#eth-b"/></svg>`}
              {/if}
            </div>
            <div class="crypto-details">
              <p class="crypto-name">{coin.label}</p>
              <p class="crypto-address">{coin.address}</p>
              <button class="copy-btn" onclick={() => copyAddress(key)}>
                {#if copyFeedback[key]}
                  ✅ Kopiert!
                {:else}
                  📋 Adresse kopieren
                {/if}
              </button>
            </div>
          </div>
        </div>
      {/if}
    {/each}

    <!-- Footer -->
    <div class="donate-panel-footer">
      Danke für deine Unterstützung! ❤️
    </div>

  </div>
</div>
{/if}

<style>
  /* ─── Backdrop mit Blur ─── */
  .donate-backdrop {
    position: fixed;
    inset: 0;
    z-index: 9999;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(0, 0, 0, 0.55);
    -webkit-backdrop-filter: blur(8px);
    backdrop-filter: blur(8px);
    animation: fadeIn 0.2s ease-out;
  }

  @keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
  }

  /* ─── Glasmorphism Panel ─── */
  .donate-panel {
    position: relative;
    width: 92vw;
    max-width: 480px;
    max-height: 90vh;
    overflow-y: auto;
    padding: 28px 24px 20px;
    border-radius: 20px;
    /* Glasmorphism: backdrop-filter + halbtransparenter BG */
    background: rgba(30, 30, 40, 0.78);
    -webkit-backdrop-filter: blur(24px) saturate(1.6);
    backdrop-filter: blur(24px) saturate(1.6);
    border: 1px solid rgba(255, 255, 255, 0.1);
    box-shadow:
      0 8px 32px rgba(0, 0, 0, 0.4),
      inset 0 1px 0 rgba(255, 255, 255, 0.06);
    animation: panelIn 0.25s ease-out;
    color: #e0e0e0;
  }

  @keyframes panelIn {
    from { opacity: 0; transform: translateY(16px) scale(0.97); }
    to { opacity: 1; transform: translateY(0) scale(1); }
  }

  /* ─── Schließen ─── */
  .donate-close {
    position: absolute;
    top: 12px;
    right: 14px;
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 50%;
    width: 32px;
    height: 32px;
    font-size: 0.9rem;
    color: #aaa;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.15s;
  }
  .donate-close:hover {
    background: rgba(255, 255, 255, 0.15);
    color: #fff;
  }

  /* ─── Header ─── */
  .donate-header {
    text-align: center;
    margin-bottom: 20px;
  }
  .donate-icon {
    font-size: 2.2rem;
    display: block;
    margin-bottom: 8px;
  }
  .donate-header h2 {
    font-size: 1.15rem;
    font-weight: 700;
    color: #fff;
    margin: 0 0 6px;
  }
  .donate-header p {
    font-size: 0.82rem;
    color: #9ca3af;
    line-height: 1.5;
    margin: 0;
  }

  /* ─── Ko-fi Button ─── */
  .kofi-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    width: 100%;
    padding: 12px 16px;
    border-radius: 12px;
    background: linear-gradient(135deg, #ff5e5b 0%, #ff4757 100%);
    color: #fff;
    font-weight: 600;
    font-size: 0.92rem;
    text-decoration: none;
    border: none;
    cursor: pointer;
    transition: all 0.2s;
    margin-bottom: 20px;
    box-shadow: 0 4px 14px rgba(255, 94, 91, 0.3);
  }
  .kofi-btn:hover {
    transform: translateY(-1px);
    box-shadow: 0 6px 20px rgba(255, 94, 91, 0.45);
  }
  .kofi-icon { font-size: 1.2rem; }

  /* ─── Crypto Label ─── */
  .crypto-label {
    text-align: center;
    font-size: 0.78rem;
    color: #888;
    margin: 0 0 12px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  /* ─── Crypto Tabs ─── */
  .crypto-tabs {
    display: flex;
    gap: 6px;
    margin-bottom: 16px;
  }
  .crypto-tab {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    padding: 9px 8px;
    border-radius: 10px;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.08);
    color: #aaa;
    cursor: pointer;
    font-size: 0.78rem;
    font-weight: 500;
    transition: all 0.15s;
  }
  .crypto-tab:hover {
    background: rgba(255, 255, 255, 0.1);
    color: #ddd;
  }
  .crypto-tab.active {
    background: rgba(255, 255, 255, 0.12);
    border-color: var(--coin-color, #888);
    color: #fff;
    box-shadow: 0 0 12px rgba(255, 255, 255, 0.05);
  }
  .coin-symbol {
    font-size: 1rem;
    font-weight: 700;
  }
  .crypto-tab.active .coin-symbol {
    color: var(--coin-color, #fff);
  }

  /* ─── Crypto Content ─── */
  .crypto-content {
    animation: fadeIn 0.15s ease-out;
  }
  .crypto-box {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 14px;
    border-radius: 14px;
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.06);
  }

  /* ─── QR Code ─── */
  .qr-wrapper {
    flex-shrink: 0;
    width: 120px;
    height: 120px;
    border-radius: 10px;
    overflow: hidden;
    background: #fff;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 4px;
  }
  .qr-wrapper :global(svg) {
    width: 100%;
    height: 100%;
  }

  /* ─── Crypto Details ─── */
  .crypto-details {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .crypto-name {
    font-size: 0.85rem;
    font-weight: 600;
    color: #fff;
    margin: 0;
  }
  .crypto-address {
    font-size: 0.65rem;
    font-family: ui-monospace, 'SF Mono', 'Cascadia Code', monospace;
    color: #9ca3af;
    word-break: break-all;
    line-height: 1.5;
    margin: 0;
    padding: 6px 8px;
    border-radius: 6px;
    background: rgba(0, 0, 0, 0.25);
  }
  .copy-btn {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 6px 12px;
    border-radius: 8px;
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.1);
    color: #ccc;
    cursor: pointer;
    font-size: 0.75rem;
    transition: all 0.15s;
    width: fit-content;
  }
  .copy-btn:hover {
    background: rgba(255, 255, 255, 0.15);
    color: #fff;
  }

  /* ─── Footer ─── */
  .donate-panel-footer {
    text-align: center;
    margin-top: 18px;
    font-size: 0.78rem;
    color: #888;
  }

  /* ─── Mobile ─── */
  @media (max-width: 500px) {
    .donate-panel { padding: 22px 16px 16px; }
    .crypto-box { flex-direction: column; text-align: center; }
    .crypto-details { align-items: center; }
    .crypto-tab span:not(.coin-symbol) { display: none; }
  }
</style>
