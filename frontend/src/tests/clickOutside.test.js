/**
 * Lag ein Klick innerhalb (lib/utils/clickOutside).
 *
 * Kontrakt: Ein Klick zählt als innerhalb, wenn er dort begann - auch wenn
 * die Oberfläche das geklickte Element währenddessen entfernt.
 */
import { describe, it, expect, afterEach } from 'vitest';
import { clickedInside } from '../lib/utils/clickOutside.js';

describe('clickedInside', () => {
  afterEach(() => { document.body.innerHTML = ''; });

  function clickRecording(target, check) {
    let result = null;
    const listener = (e) => { result = check(e); };
    document.addEventListener('click', listener);
    target.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    document.removeEventListener('click', listener);
    return result;
  }

  it('erkennt Bereiche per Element und per Auswahl', () => {
    document.body.innerHTML = '<section class="karte"><button>Los</button></section><p>daneben</p>';
    const card = document.querySelector('.karte');
    const button = document.querySelector('button');
    expect(clickRecording(button, (e) => clickedInside(e, card))).toBe(true);
    expect(clickRecording(button, (e) => clickedInside(e, '.liste', '.karte'))).toBe(true);
    expect(clickRecording(document.querySelector('p'), (e) => clickedInside(e, card, '.karte'))).toBe(false);
    expect(clickRecording(button, (e) => clickedInside(e, null))).toBe(false);
  });

  it('bleibt innerhalb, wenn der Knopf beim Klick verschwindet', () => {
    document.body.innerHTML = '<section class="karte"><button>Abspielen</button></section>';
    const button = document.querySelector('button');
    // Die Karte ersetzt den Knopf, bevor der Lauscher am Dokument dran ist
    button.addEventListener('click', () => button.replaceWith(document.createElement('video')));
    expect(clickRecording(button, (e) => [!!e.target.closest('.karte'), clickedInside(e, '.karte')]))
      .toEqual([false, true]);
  });
});
