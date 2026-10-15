/**
 * TubeVault Frontend v1.5.52
 * © HalloWelt42 – Private Nutzung
 */

import '@fontsource/barlow/400.css';
import '@fontsource/barlow/500.css';
import '@fontsource/barlow/600.css';
import '@fontsource/barlow/700.css';
import '@fontsource/chakra-petch/400.css';
import '@fontsource/chakra-petch/500.css';
import '@fontsource/chakra-petch/600.css';
import '@fortawesome/fontawesome-free/css/all.min.css';
import './lib/styles/marken.css';
import './lib/styles/uebergang.css';
import './lib/styles/bausteine.css';
import App from './App.svelte';
import { startFrontendLog } from './lib/utils/frontendLog.js';
import { mount } from 'svelte';
import { initKeyboard } from './lib/stores/keyboard.js';

startFrontendLog();   // Warnungen und Fehler des Browsers ins Live-Log
const app = mount(App, { target: document.getElementById('app') });
initKeyboard();

export default app;
