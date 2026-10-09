import test from 'node:test';
import assert from 'node:assert/strict';
import { recoverMessages, validWidgets, buildContext } from '../ui/src/chatPersistence.ts';
import { evaluateFormula } from '../ui/src/chatWidgets.ts';
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

test('calculator and chart widgets validate and recover interactive values', () => {
  const calculator={kind:'calculator',title:'Estimate',inputs:[{key:'n',label:'Value',value:3,min:0,max:10,step:1}],formula:{op:'mul',left:{op:'input',key:'n'},right:{op:'const',value:2}},resultLabel:'Total',unit:'',precision:0};
  const chart={kind:'chart',title:'Trend',chartType:'line',xLabel:'Year',yLabel:'Count',series:[{label:'Observed',points:[{x:'2024',y:2},{x:'2025',y:5}]}]};
  assert.equal(validWidgets([calculator,chart]).length,2);
  const misalignedChart={...chart,series:[...chart.series,{label:'Forecast',points:[{x:'2024',y:3},{x:'2025',y:7},{x:'2026',y:9}]}]};
  assert.equal(validWidgets([misalignedChart]).length,0,'different category counts must be rejected before render');
  assert.equal(evaluateFormula(calculator.formula,{n:4}),8);
  const [recovered]=recoverMessages([{id:'m',role:'assistant',text:'Estimate',timestamp:'now',widgets:[calculator,chart],widgetValues:{'0-n':4,'bad':'x'}}]);
  assert.equal(recovered.widgetValues['0-n'],4);
  assert.equal(recovered.widgetValues.bad,undefined);
  assert.equal(recovered.widgets.length,2);
  const [cleared]=recoverMessages([{id:'m2',role:'assistant',text:'Estimate',timestamp:'now',widgets:[calculator],widgetValues:{'0-n':null}}]);
  assert.equal(cleared.widgetValues['0-n'],null,'cleared calculator state must survive recovery');
  assert.throws(()=>evaluateFormula({op:'div',left:{op:'const',value:1},right:{op:'const',value:0}},{ }));
  assert.equal(validWidgets([{...calculator,formula:{op:'exec',code:'alert(1)'}}]).length,0);
});
