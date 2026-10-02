/**
 * TubeVault – Mobil-Ansicht (Einstieg)
 *
 * Eigenständige, reduzierte Oberfläche für das Telefon. Sie teilt mit der
 * grossen Ansicht nur Daten und Endpunkte (lib/api, lib/utils) - Aufbau,
 * Bedienung und Gestaltung sind eigene. Erreichbar unter /m.
 */
import { mount } from 'svelte';
import '@fontsource/barlow/400.css';
import '@fontsource/barlow/600.css';
import '@fortawesome/fontawesome-free/css/all.min.css';
import './mobile.css';
import MobileApp from './MobileApp.svelte';

mount(MobileApp, { target: document.getElementById('app') });
