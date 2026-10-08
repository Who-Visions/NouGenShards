import test from 'node:test';
import assert from 'node:assert/strict';
import { recoverMessages, validWidgets, buildContext } from '../ui/src/chatPersistence.ts';
test('corrupt records and unknown widgets cannot reach renderers', () => {
  assert.deepEqual(recoverMessages(null), []);
  assert.deepEqual(validWidgets([{kind:'html', title:'x', items:['x']}]), []);
  assert.deepEqual(recoverMessages([{role:'system'}]), []);
});
test('widget interaction survives recovery and records are bounded', () => {
  const m = {id:'a',role:'user',text:'hello',timestamp:'now',widgets:[{kind:'checklist',title:'Plan',items:['A']}],widgetChecks:{'0-0':true,bad:'yes'}};
  const [saved] = recoverMessages([m]);
  assert.equal(saved.widgetChecks['0-0'], true);
  assert.equal(saved.widgetChecks.bad, undefined);
  assert.equal(saved.widgets.length, 1);
  assert.equal(recoverMessages(Array(600).fill(m)).length, 500);
});

test('context keeps the latest turn within backend limits and omits errors', () => {
  const rows = Array.from({length:50}, () => ({role:'assistant', text:'x'.repeat(24000)}));
  rows.push({role:'assistant',text:'connection failed',isError:true}, {role:'user',text:'latest'});
  const result = buildContext(rows);
  assert.equal(result.at(-1).content, 'latest');
  assert.ok(result.reduce((n,m) => n+m.content.length,0) <= 100000);
  assert.ok(!result.some(m => m.content === 'connection failed'));
});
