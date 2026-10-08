import React from 'react';
import type { CSSProperties } from 'react';
import type { Widget } from './chatWidgetIR.ts';
import { evaluateFormula } from './chatWidgets';

type Props = {
  widget: Widget;
  messageId: string;
  index: number;
  checks?: Record<string, boolean>;
  values?: Record<string, number | null>;
  onCheck: (key: string, value: boolean) => void;
  onValue: (key: string, value: number | null) => void;
};

const ICON: Record<Widget['kind'], string> = { checklist:'☑', comparison:'↔', steps:'1–2', metric_grid:'#', calculator:'∑', chart:'▥' };
const COLORS = ['var(--accent)','var(--accent-green)','var(--accent-purple)','var(--danger)'];

function Calculator({widget, values={}, onValue}: {widget:Extract<Widget,{kind:'calculator'}>;values?:Props['values'];onValue:Props['onValue']}) {
  const inputValues=Object.fromEntries(widget.inputs.map(field=>[field.key,values[field.key] ?? field.value])) as Record<string,number|null>;
  let result: number | undefined, error='';
  try {
    for (const field of widget.inputs) { const value=inputValues[field.key]; if (typeof value!=='number' || value<field.min || value>field.max) throw new Error(`Enter ${field.label} between ${field.min} and ${field.max}.`); }
    result=evaluateFormula(widget.formula,inputValues);
  } catch (reason) { error=reason instanceof Error ? reason.message : 'Unable to calculate.'; }
  return <div className="chat-calculator">
    <div className="calculator-fields">{widget.inputs.map(field=><label key={field.key} className="calculator-field"><span>{field.label}{field.unit?` (${field.unit})`:''}</span>
      <input type="number" aria-label={`${field.label}${field.unit?` (${field.unit})`:''}`} min={field.min} max={field.max} step={field.step} value={inputValues[field.key] ?? ''} onChange={e=>{const raw=e.currentTarget.value;onValue(field.key,raw===''?null:Number(raw));}}/>
    </label>)}</div>
    <div className="calculator-result" aria-live="polite"><span>{widget.resultLabel}</span><output>{error || (result===undefined?'':`${result.toLocaleString(undefined,{maximumFractionDigits:widget.precision})}${widget.unit?` ${widget.unit}`:''}`)}</output></div>
  </div>;
}

function Chart({widget}: {widget:Extract<Widget,{kind:'chart'}>}) {
  const points=widget.series[0].points, values=widget.series.flatMap(s=>s.points.map(p=>p.y));
  const min=Math.min(0,...values), max=Math.max(0,...values), range=max-min||1;
  const left=58,right=620,top=18,bottom=210;
  const x=(i:number)=>widget.chartType==='bar'?left+(i+.5)*(right-left)/points.length:left+(points.length===1?0:i*(right-left)/(points.length-1));
  const y=(v:number)=>bottom-(v-min)/range*(bottom-top);
  return <div className="chat-chart">
    <svg viewBox="0 0 640 270" role="img" aria-label={`${widget.title}. ${widget.yLabel} by ${widget.xLabel}.`}>
      {[0,.5,1].map((t,i)=>{const value=min+range*t,yy=y(value);return <g key={i}><line className="chart-gridline" x1={left} x2={right} y1={yy} y2={yy}/><text className="chart-tick" x={left-8} y={yy+4} textAnchor="end">{Number(value.toPrecision(3)).toLocaleString()}</text></g>;})}
      <line className="chart-axis" x1={left} x2={left} y1={top} y2={bottom}/><line className="chart-axis" x1={left} x2={right} y1={y(0)} y2={y(0)}/>
      {widget.chartType==='line'?widget.series.map((series,si)=><g key={series.label}><polyline className={`chart-series series-${si}`} points={series.points.map((point,i)=>`${x(i)},${y(point.y)}`).join(' ')} stroke={COLORS[si]}/>{series.points.map((point,i)=><circle key={i} cx={x(i)} cy={y(point.y)} r="3.5" fill={COLORS[si]}/>)}</g>):widget.series.map((series,si)=>{const group=(right-left)/points.length,bw=Math.min(24,group/widget.series.length*.72);return <g key={series.label} fill={COLORS[si]}>{series.points.map((point,i)=>{const yy=y(point.y),zero=y(0);return <rect key={i} x={x(i)-group/2+si*bw} y={Math.min(yy,zero)} width={bw} height={Math.max(1,Math.abs(yy-zero))}/>})}</g>;})}
      {points.map((point,i)=><text key={`${point.x}-${i}`} className="chart-tick" x={x(i)} y={bottom+18} textAnchor="middle">{point.x.length>12?`${point.x.slice(0,11)}…`:point.x}</text>)}
      <text className="chart-axis-label" x={(left+right)/2} y="257" textAnchor="middle">{widget.xLabel}</text><text className="chart-axis-label" transform={`translate(14 ${(top+bottom)/2}) rotate(-90)`} textAnchor="middle">{widget.yLabel}</text>
    </svg>
    <div className="chart-legend">{widget.series.map((series,i)=><span key={series.label}><i style={{'--series-color':COLORS[i]} as CSSProperties}/>{series.label}</span>)}</div>
    <details className="chart-data"><summary>View data table</summary><div className="chart-table-scroll"><table><caption>{widget.title}: {widget.yLabel} by {widget.xLabel}</caption><thead><tr><th scope="col">{widget.xLabel}</th>{widget.series.map(series=><th scope="col" key={series.label}>{series.label} · {widget.yLabel}</th>)}</tr></thead><tbody>{points.map((point,i)=><tr key={`${point.x}-${i}`}><th scope="row">{point.x}</th>{widget.series.map(series=><td key={series.label}>{series.points[i].y.toLocaleString()}</td>)}</tr>)}</tbody></table></div></details>
  </div>;
}

export default function ChatWidgetRenderer({widget,messageId,index,checks={},values={},onCheck,onValue}:Props) {
  const headingId=`${messageId}-widget-${index}`;
  return <section className={`chat-model-widget ${widget.kind}`} aria-labelledby={headingId}>
    <div className="widget-header-title"><span className="widget-icon" aria-hidden="true">{ICON[widget.kind]}</span><h3 id={headingId}>{widget.title}</h3></div>
    {widget.kind==='checklist'&&<div className="widget-checklist-group">{widget.items.map((item,j)=><label key={j} className="widget-check-label"><input type="checkbox" aria-label={item} checked={Boolean(checks[`${index}-${j}`])} onChange={e=>onCheck(`${index}-${j}`,e.target.checked)}/><span>{item}</span></label>)}</div>}
    {widget.kind==='metric_grid'&&<div className="widget-metric-grid">{widget.items.map((item,j)=><div key={j} className="metric-chip-card"><span className="metric-text">{item}</span></div>)}</div>}
    {widget.kind==='comparison'&&<div className="widget-comparison-grid">{widget.items.map((item,j)=><div key={j} className="comparison-column-card"><p>{item}</p></div>)}</div>}
    {widget.kind==='steps'&&<ol className="widget-steps-list">{widget.items.map((item,j)=><li key={j}>{item}</li>)}</ol>}
    {widget.kind==='calculator'&&<Calculator widget={widget} values={values} onValue={(key,value)=>onValue(`${index}-${key}`,value)}/>}
    {widget.kind==='chart'&&<Chart widget={widget}/>}
  </section>;
}
