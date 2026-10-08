// GENERATED from contracts/chat-widgets.v1.json; do not edit.
export const CHAT_WIDGET_IR_VERSION = 1 as const;
export const CHAT_WIDGET_KINDS = ["checklist", "comparison", "steps", "metric_grid", "calculator", "chart"] as const;
export const CHAT_WIDGET_LIMITS = {"calculatorInputs": 8, "chartSeries": 4, "formulaDepth": 12, "itemLength": 500, "listItems": 12, "numericMagnitude": 1e+100, "pointsPerSeries": 24, "titleLength": 160, "widgetsPerReply": 12} as const;

export type Formula = ({
  op: "input";
  key: string;
}) | ({
  op: "const";
  value: number;
}) | ({
  op: "neg";
  value: Formula;
}) | ({
  op: "add" | "sub" | "mul" | "div" | "pow";
  left: Formula;
  right: Formula;
});
export type CalculatorInput = {
  key: string;
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  unit?: string;
};
export type ChartPoint = {
  x: string;
  y: number;
};
export type ChartSeries = {
  label: string;
  points: Array<ChartPoint>;
};

export type Widget = {
  contractVersion: 1;
  kind: "checklist";
  title: string;
  items: Array<string>;
}
  | {
  contractVersion: 1;
  kind: "comparison";
  title: string;
  items: Array<string>;
}
  | {
  contractVersion: 1;
  kind: "steps";
  title: string;
  items: Array<string>;
}
  | {
  contractVersion: 1;
  kind: "metric_grid";
  title: string;
  items: Array<string>;
}
  | {
  contractVersion: 1;
  kind: "calculator";
  title: string;
  inputs: Array<CalculatorInput>;
  formula: Formula;
  resultLabel: string;
  unit: string;
  precision: number;
}
  | {
  contractVersion: 1;
  kind: "chart";
  title: string;
  chartType: "line" | "bar";
  xLabel: string;
  yLabel: string;
  series: Array<ChartSeries>;
};

export const CHAT_WIDGET_VARIANTS = [{"kind":"checklist","fields":{"items":{"type":"array","minItems":1,"maxItems":12,"items":{"type":"string","minLength":1,"maxLength":500}}}},{"kind":"comparison","fields":{"items":{"type":"array","minItems":1,"maxItems":12,"items":{"type":"string","minLength":1,"maxLength":500}}}},{"kind":"steps","fields":{"items":{"type":"array","minItems":1,"maxItems":12,"items":{"type":"string","minLength":1,"maxLength":500}}}},{"kind":"metric_grid","fields":{"items":{"type":"array","minItems":1,"maxItems":12,"items":{"type":"string","minLength":1,"maxLength":500}}}},{"kind":"calculator","fields":{"inputs":{"type":"array","minItems":1,"maxItems":8,"items":{"$ref":"#/definitions/CalculatorInput"}},"formula":{"$ref":"#/definitions/Formula"},"resultLabel":{"type":"string","minLength":1,"maxLength":80},"unit":{"type":"string","maxLength":16},"precision":{"type":"integer","minimum":0,"maximum":6}}},{"kind":"chart","fields":{"chartType":{"enum":["line","bar"]},"xLabel":{"type":"string","minLength":1,"maxLength":80},"yLabel":{"type":"string","minLength":1,"maxLength":80},"series":{"type":"array","minItems":1,"maxItems":4,"items":{"$ref":"#/definitions/ChartSeries"}}}}] as const;