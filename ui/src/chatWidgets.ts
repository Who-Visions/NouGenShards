import type { Formula } from './chatWidgetIR.ts';

export function evaluateFormula(node: Formula, values: Record<string, number | null>, depth = 0): number {
  if (depth > 12) throw new Error('Formula is too deep.');
  if (node.op === 'input') {
    const value = values[node.key];
    if (typeof value !== 'number' || !Number.isFinite(value)) throw new Error('Enter a valid value for every input.');
    return value;
  }
  if (node.op === 'const') return node.value;
  if (node.op === 'neg') return -evaluateFormula(node.value, values, depth + 1);
  const left = evaluateFormula(node.left, values, depth + 1), right = evaluateFormula(node.right, values, depth + 1);
  let result: number;
  switch (node.op) {
    case 'add': result = left + right; break;
    case 'sub': result = left - right; break;
    case 'mul': result = left * right; break;
    case 'div': if (right === 0) throw new Error('Cannot divide by zero.'); result = left / right; break;
    case 'pow': if (Math.abs(right) > 12) throw new Error('Exponent is outside the supported range.'); result = left ** right; break;
  }
  if (!Number.isFinite(result) || Math.abs(result) > 1e100) throw new Error('Result is outside the supported range.');
  return result;
}
