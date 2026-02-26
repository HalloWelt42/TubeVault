/**
 * TubeVault -  Test Setup v1.5.2
 * Mocks für Browser-APIs die in jsdom fehlen
 * © HalloWelt42
 */

// localStorage Mock
const store = {};
global.localStorage = {
  getItem: (key) => store[key] ?? null,
  setItem: (key, val) => { store[key] = String(val); },
  removeItem: (key) => { delete store[key]; },
  clear: () => { Object.keys(store).forEach(k => delete store[k]); },
};

// window.location Mock (für API_BASE Berechnung)
Object.defineProperty(window, 'location', {
  value: {
    protocol: 'http:',
    hostname: 'localhost',
    host: 'localhost:8032',
    port: '8032',
    href: 'http://localhost:8032/',
    origin: 'http://localhost:8032',
  },
  writable: true,
});

// fetch Mock (wird in einzelnen Tests überschrieben)
global.fetch = vi.fn(() =>
  Promise.resolve({
    ok: true,
    json: () => Promise.resolve({}),
  })
);

// WebSocket Mock
global.WebSocket = vi.fn(() => ({
  close: vi.fn(),
  send: vi.fn(),
  onopen: null,
  onclose: null,
  onmessage: null,
  onerror: null,
  readyState: 1,
}));
WebSocket.OPEN = 1;

// CustomEvent für Keyboard Store
global.CustomEvent = class CustomEvent extends Event {
  constructor(type, params = {}) {
    super(type, params);
    this.detail = params.detail;
  }
};
