// Tests for theme-core.js: which Mono Violet scheme "Auto" picks.
// Lesson from Electron's nativeTheme: the app's own theme (YouTube's, here) is the truth when it has one, the system
// setting is the fallback, and both can change while the page is open.
// Run: node --test extensions/nougentube-chrome/tests/theme-core.test.mjs
// Expected values are worked by hand from the colours involved (#0f0f0f is YouTube's dark page, #ffffff its light page).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const core = createRequire(import.meta.url)('../theme-core.js');

test('colours are read in the forms YouTube and browsers give them', () => {
  assert.deepEqual({ ...core.parseColor('#0f0f0f') }, { r: 15, g: 15, b: 15 });
  assert.deepEqual({ ...core.parseColor(' #FFF ') }, { r: 255, g: 255, b: 255 });
  assert.deepEqual({ ...core.parseColor('rgb(15, 15, 15)') }, { r: 15, g: 15, b: 15 });
  assert.deepEqual({ ...core.parseColor('rgba(255,255,255,0.5)') }, { r: 255, g: 255, b: 255 });
});

test('anything that is not a colour is null, so the caller can fall back', () => {
  for (const bad of ['', '   ', 'transparent', 'var(--x)', '#12', '#gggggg', null, undefined]) assert.equal(core.parseColor(bad), null, String(bad));
});

test("YouTube's own page colour decides: its dark page is dark, its light page is light", () => {
  assert.equal(core.resolveAuto({ ytBackground: '#0f0f0f', ytDarkAttr: true, osDark: true }), 'dark');
  assert.equal(core.resolveAuto({ ytBackground: '#ffffff', ytDarkAttr: false, osDark: false }), 'light');
});

test('YouTube light on a dark system shows light: Auto matches YouTube, not the system', () => {
  assert.equal(core.resolveAuto({ ytBackground: '#ffffff', ytDarkAttr: false, osDark: true }), 'light');
});

test('YouTube dark on a light system shows dark', () => {
  assert.equal(core.resolveAuto({ ytBackground: 'rgb(15, 15, 15)', ytDarkAttr: true, osDark: false }), 'dark');
});

test("when the page has no colour yet, YouTube's dark flag is used", () => {
  assert.equal(core.resolveAuto({ ytBackground: '', ytDarkAttr: true, osDark: false }), 'dark');
});

test('with nothing from YouTube at all, the system setting decides', () => {
  assert.equal(core.resolveAuto({ ytBackground: '', ytDarkAttr: false, osDark: true }), 'dark');
  assert.equal(core.resolveAuto({ ytBackground: '', ytDarkAttr: false, osDark: false }), 'light');
});

test('missing inputs never throw', () => {
  assert.equal(core.resolveAuto({}), 'light');
  assert.equal(core.resolveAuto(), 'light');
});
