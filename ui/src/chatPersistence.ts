export type Widget = { kind: 'checklist' | 'comparison' | 'steps' | 'metric_grid'; title: string; items: string[] };
export function validWidgets(value: unknown): Widget[] {
  if (!Array.isArray(value)) return [];
  return value.slice(0, 12).filter((w): w is Widget => w && ['checklist', 'comparison', 'steps', 'metric_grid'].includes(w.kind) && typeof w.title === 'string' && w.title.length <= 160 && Array.isArray(w.items) && w.items.length <= 12 && w.items.every((i: unknown) => typeof i === 'string' && i.length <= 500));
}
export function recoverMessages(value: unknown): any[] {
  if (!Array.isArray(value)) return [];
  return value.slice(-500).filter(m => m && typeof m.id === 'string' && ['user', 'assistant'].includes(m.role) && typeof m.text === 'string' && m.text.length <= 24000 && typeof m.timestamp === 'string').map(m => ({
    id: m.id, role: m.role, text: m.text, timestamp: m.timestamp, isError: m.isError === true,
    widgets: validWidgets(m.widgets), widgetChecks: m.widgetChecks && typeof m.widgetChecks === 'object' ? Object.fromEntries(Object.entries(m.widgetChecks).filter(([k, v]) => /^\d+-\d+$/.test(k) && typeof v === 'boolean').slice(0, 144)) : {},
  }));
}

export function buildContext(messages: Array<{role: string; text: string; isError?: boolean}>): Array<{role: string; content: string}> {
  const result: Array<{role: string; content: string}> = [];
  let chars = 0;
  for (const m of messages.filter(m => !m.isError).slice(-40).reverse()) {
    const content = m.text.slice(0, 24000);
    if (chars + content.length > 100000) break;
    chars += content.length;
    result.unshift({role: m.role, content});
  }
  return result;
}
