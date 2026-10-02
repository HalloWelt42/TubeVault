/**
 * TubeVault – Nachvertonung: ist die Erweiterung eingeschaltet?
 * (reaktiv nutzbar über $settings)
 */
import { get } from 'svelte/store';
import { settings } from '../stores/settings.js';

export const dubbingEnabled = (current = get(settings)) => current['dub.enabled'] === 'true';
