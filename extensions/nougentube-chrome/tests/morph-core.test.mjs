// Tests for morph-core.js: the 21 Valerion steps and the checks on a written Morph plan.
// Run: node --test extensions/nougentube-chrome/tests/morph-core.test.mjs
// Expected values are written out by hand from NouGen docs/architecture.md and from worked examples, not recomputed from the code.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const core = createRequire(import.meta.url)('../morph-core.js');
const refOf = h => `${h.id}@db${h.db}`;

const STEPS = [
  'Metamers', 'Activate Orchestration', 'Deep Grep Latent Structure', 'Surface Leverage', 'Extract Invariants', 'Copy Successful Topology',
  'Transpose Patterns', 'Combine Compatible Systems', 'Synthesize Coherent Signal', 'Integrate Constraints', 'Transform Architecture',
  'Refactor Complexity', 'Compress Noise', 'Expand Solution Space', 'Remix Viable Patterns', 'Invert Assumptions', 'Reverse-Engineer Intent',
  'Reconstruct Coherence', 'Stabilize Reasoning', 'Iterate Recursively', 'Orchestrate Convergence',
];
const list = fmt => STEPS.map((n, i) => `${i + 1}${fmt(n)}`).join('\n');
const SECTIONS = '### Intent of the video\nBuild a loop [2:13]\n### What the vault already has\n- [12@db3] notes\n### Morph plan\nA design.\n### First build steps\n1. do it\n### Gaps\nNo test harness exists yet in the vault.\n';
const plan = (extra = '') => SECTIONS + '### Valerion pass\n' + list(n => `. **${n}**: one sentence [2:13].`) + extra;
const M = (over = {}) => ({ v21: true, shards: [{ id: 12, db: 3 }], web: [], text: plan(), ...over });

test('the 21 steps are exactly the documented names, in order', () => {
  assert.deepEqual(core.V21, STEPS);
  assert.equal(core.V21.length, 21);
});

test('citations are read singly, grouped and mixed; timestamps and prose brackets are not citations', () => {
  const c = core.citations('a [12@db3] b [14@db3, 15@db4] c [w1, w2; w3] d [2:13] e [see above] f [12@db3]');
  assert.deepEqual(c.shards, ['12@db3', '14@db3', '15@db4']);
  assert.deepEqual(c.web, ['w1', 'w2', 'w3']);
});

test('a numbered list in any common format counts as all 21 steps', () => {
  for (const fmt of [n => `. **${n}**: x`, n => `. ${n}: x`, n => `) ${n} - x`, n => `. ${n.replace('-', ' ')}: x`]) {
    assert.equal(core.v21Found(list(fmt)).size, 21);
  }
});

test('steps only count when numbered in order; prose mentions and shifted names do not', () => {
  assert.equal(core.v21Found('Metamers and Activate Orchestration are mentioned in a sentence.').size, 0);
  const shifted = STEPS.map((_, i) => `${i + 1}. ${STEPS[(i + 1) % 21]}: x`).join('\n');
  assert.equal(core.v21Found(shifted).size, 0);
});

test('a complete plan passes every check', () => {
  const k = core.checkPlan(M(), refOf);
  assert.deepEqual([k.bad, k.badWeb, k.missing, k.v21Missing, k.cutOff], [[], [], [], [], false]);
});

test('an invented shard inside a grouped citation is flagged', () => {
  const k = core.checkPlan(M({ text: plan('\nSee [12@db3, 99@db9].') }), refOf);
  assert.deepEqual(k.bad, ['99@db9']);
});

test('web tags must be among the sources found, and the read count only counts sources with page text', () => {
  const web = [{ ref: 'w1', text: 'page text' }, { ref: 'w2', text: '' }];
  const k = core.checkPlan(M({ web, text: SECTIONS.replace('### Morph plan', '### Latest on the web\n- [w1, w2, w7]\n### Morph plan') + '### Valerion pass\n' + list(n => `. ${n}: x`) }), refOf);
  assert.deepEqual(k.badWeb, ['w7']);
  assert.equal(k.webRead, 1);
});

test('a missing step is reported by name', () => {
  const text = M().text.replace(/^20\. .*\n/m, '');
  assert.deepEqual(core.checkPlan(M({ text }), refOf).v21Missing, ['Iterate Recursively']);
});

test('missing sections and an empty last section mark the plan as cut off', () => {
  const k = core.checkPlan(M({ text: '### Intent of the video\nA [2:13]\n### Gaps\nab' }), refOf);
  assert.equal(k.cutOff, true);
  assert.ok(k.missing.includes('Morph plan') && k.missing.includes('Valerion pass'));
});

test('the route stamp appended after the plan is not plan content', () => {
  const stamp = '\n\n— nvidia/some-model, 10 tokens, 3s, NouGenOpen free fleet';
  assert.equal(core.checkPlan(M({ text: plan() + stamp }), refOf).cutOff, false);
  assert.equal(core.body('text\n\n— model, 5 tokens'), 'text');
});

test('the report says so when no timestamps are cited, and states all-clear in plain words otherwise', () => {
  const k = core.checkPlan(M(), refOf);
  const none = core.report(M(), k, { ts: 0, bad: [] });
  assert.ok(none.some(r => !r.ok && r.text === 'The plan cites no timestamps from the video'));
  const ok = core.report(M(), k, { ts: 17, bad: [] });
  assert.ok(ok.every(r => r.ok));
  assert.ok(ok.some(r => r.text === 'The Valerion pass has all 21 steps, numbered in order'));
});

test('an unreadable vault is the first line of the report', () => {
  const m = M({ vaultOff: 'the bridge did not answer' });
  const r = core.report(m, core.checkPlan(m, refOf), { ts: 3, bad: [] });
  assert.equal(r[0].ok, false);
  assert.match(r[0].text, /built from the video alone/);
});

test('only http and https links are used as links', () => {
  assert.equal(core.safeUrl('https://example.com/a'), 'https://example.com/a');
  assert.equal(core.safeUrl('http://example.com'), 'http://example.com');
  assert.equal(core.safeUrl('javascript:alert(1)'), '#');
  assert.equal(core.safeUrl('data:text/html,x'), '#');
});

test('all 21 steps written in reverse order are not "numbered in order"', () => {
  const reversed = STEPS.map((n, i) => `${i + 1}. ${n}: x`).reverse().join('\n');
  const k = core.checkPlan(M({ text: SECTIONS + '### Valerion pass\n' + reversed }), refOf);
  assert.ok(k.v21Missing.length > 0, 'a reversed list must not pass');
  assert.equal(core.report(M(), { ...k, bad: [], cited: ['12@db3'], badWeb: [], web: [], webRead: 0, missing: [], cutOff: false }, { ts: 3, bad: [] }).some(r => r.text === 'The Valerion pass has all 21 steps, numbered in order'), false);
});

test('two swapped lines name the displaced step', () => {
  const lines = STEPS.map((n, i) => `${i + 1}. ${n}: x`);
  [lines[4], lines[5]] = [lines[5], lines[4]];          // step 6 now comes before step 5
  const k = core.checkPlan(M({ text: SECTIONS + '### Valerion pass\n' + lines.join('\n') }), refOf);
  assert.deepEqual(k.v21Missing, ['Extract Invariants']);
});
