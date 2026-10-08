import { CHAT_WIDGET_IR_VERSION, CHAT_WIDGET_KINDS, CHAT_WIDGET_LIMITS, type Formula, type Widget } from './chatWidgetIR.ts';
export type { Widget } from './chatWidgetIR.ts';
const finite = (n:unknown): n is number => typeof n === 'number' && Number.isFinite(n);
function validFormula(node: any, keys: Set<string>, depth=0): node is Formula {
  if (!node || typeof node !== 'object' || depth > CHAT_WIDGET_LIMITS.formulaDepth) return false;
  if (node.op === 'input') return keys.has(node.key);
  if (node.op === 'const') return finite(node.value) && Math.abs(node.value) <= CHAT_WIDGET_LIMITS.numericMagnitude;
  if (node.op === 'neg') return validFormula(node.value, keys, depth + 1);
  return ['add','sub','mul','div','pow'].includes(node.op) && validFormula(node.left, keys, depth + 1) && validFormula(node.right, keys, depth + 1);
}
export function validWidgets(value: unknown): Widget[] {
  if (!Array.isArray(value)) return [];
  return value.slice(0, CHAT_WIDGET_LIMITS.widgetsPerReply).filter((w: any): w is Widget => {
    if (!w || typeof w !== 'object' || (w.contractVersion !== undefined && w.contractVersion !== CHAT_WIDGET_IR_VERSION) || !CHAT_WIDGET_KINDS.includes(w.kind) || typeof w.title !== 'string' || w.title.length < 1 || w.title.length > CHAT_WIDGET_LIMITS.titleLength) return false;
    if (['checklist','comparison','steps','metric_grid'].includes(w.kind)) return Array.isArray(w.items) && w.items.length >= 1 && w.items.length <= CHAT_WIDGET_LIMITS.listItems && w.items.every((i: unknown) => typeof i === 'string' && i.length >= 1 && i.length <= CHAT_WIDGET_LIMITS.itemLength);
    if (w.kind === 'calculator') {
      if (!Array.isArray(w.inputs) || w.inputs.length < 1 || w.inputs.length > CHAT_WIDGET_LIMITS.calculatorInputs || !Number.isInteger(w.precision) || w.precision < 0 || w.precision > 6 || typeof w.resultLabel !== 'string' || w.resultLabel.length < 1 || w.resultLabel.length > 80 || typeof w.unit !== 'string' || w.unit.length > 16) return false;
      const keys = new Set<string>();
      for (const f of w.inputs) {
        if (!f || typeof f.key !== 'string' || !/^[\w-]{1,32}$/.test(f.key) || keys.has(f.key) || typeof f.label !== 'string' || !f.label.length || f.label.length > 80 || ![f.value,f.min,f.max,f.step].every(finite) || Math.abs(f.min)>CHAT_WIDGET_LIMITS.numericMagnitude || Math.abs(f.max)>CHAT_WIDGET_LIMITS.numericMagnitude || f.min >= f.max || f.value < f.min || f.value > f.max || f.step <= 0 || (f.unit !== undefined && (typeof f.unit !== 'string' || f.unit.length > 16))) return false;
        keys.add(f.key);
      }
      return validFormula(w.formula, keys);
    }
    if (w.kind === 'chart') {
      if (!['line','bar'].includes(w.chartType) || ![w.xLabel,w.yLabel].every((s:unknown) => typeof s === 'string' && s.length > 0 && s.length <= 80) || !Array.isArray(w.series) || w.series.length < 1 || w.series.length > CHAT_WIDGET_LIMITS.chartSeries) return false;
      let categories: string[] | undefined;
      return w.series.every((s:any) => {
        if (!s || typeof s.label !== 'string' || !s.label.length || s.label.length > 80 || !Array.isArray(s.points) || s.points.length < 2 || s.points.length > CHAT_WIDGET_LIMITS.pointsPerSeries) return false;
        if (!s.points.every((p:any) => p && typeof p.x === 'string' && p.x.length > 0 && p.x.length <= 64 && finite(p.y) && Math.abs(p.y) <= CHAT_WIDGET_LIMITS.numericMagnitude)) return false;
        const labels = s.points.map((p:any) => p.x);
        if (categories && labels.some((label:string, i:number) => label !== categories![i])) return false;
        categories = labels;
        return true;
      });
    }
    return false;
  }).map(w => ({...w, contractVersion: CHAT_WIDGET_IR_VERSION} as Widget));
}
export function recoverMessages(value: unknown): any[] {
  if (!Array.isArray(value)) return [];
  return value.slice(-500).filter((m:any) => m && typeof m.id === 'string' && ['user','assistant'].includes(m.role) && typeof m.text === 'string' && m.text.length <= 24000 && typeof m.timestamp === 'string').map((m:any) => {
    const widgets = validWidgets(m.widgets);
    const widgetValues = m.widgetValues && typeof m.widgetValues === 'object' ? Object.fromEntries(Object.entries(m.widgetValues).filter(([k,v]) => /^\d+-[\w-]{1,32}$/.test(k) && (v === null || finite(v))).slice(0,96)) : {};
    return {id:m.id,role:m.role,text:m.text,timestamp:m.timestamp,isError:m.isError === true,widgets,widgetValues,widgetChecks:m.widgetChecks && typeof m.widgetChecks === 'object' ? Object.fromEntries(Object.entries(m.widgetChecks).filter(([k,v]) => /^\d+-\d+$/.test(k) && typeof v === 'boolean').slice(0,144)) : {}};
  });
}
export function buildContext(messages: Array<{role:string;text:string;isError?:boolean}>): Array<{role:string;content:string}> {
  const result: Array<{role:string;content:string}> = []; let chars=0;
  for (const m of messages.filter(m => !m.isError).slice(-40).reverse()) { const content=m.text.slice(0,24000); if (chars+content.length>100000) break; chars+=content.length; result.unshift({role:m.role,content}); }
  return result;
}
