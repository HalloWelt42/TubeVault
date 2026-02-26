/**
 * TubeVault Frontend v1.5.52
 * © HalloWelt42 -  Private Nutzung
 */

import '@fortawesome/fontawesome-free/css/all.min.css';
import App from './App.svelte';
import { mount } from 'svelte';
import { initKeyboard } from './lib/stores/keyboard.js';

const app = mount(App, { target: document.getElementById('app') });
initKeyboard();

export default app;
