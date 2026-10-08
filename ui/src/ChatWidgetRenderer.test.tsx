import React from 'react';
import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import ChatWidgetRenderer from './ChatWidgetRenderer';
import type { Widget } from './chatWidgetIR';

describe('deterministic chat widget IR renderer', () => {
  it('renders calculator inputs and a live, computed result', () => {
    const widget: Widget = {contractVersion:1,kind:'calculator',title:'Double a value',inputs:[{key:'n',label:'Value',value:3,min:0,max:10,step:1}],formula:{op:'mul',left:{op:'input',key:'n'},right:{op:'const',value:2}},resultLabel:'Total',unit:'items',precision:0};
    const html=renderToStaticMarkup(<ChatWidgetRenderer widget={widget} messageId="m1" index={0} onCheck={()=>{}} onValue={()=>{}}/>);
    expect(html).toContain('aria-labelledby="m1-widget-0"');
    expect(html).toContain('aria-live="polite"');
    expect(html).toContain('6 items');
    expect(html).toContain('type="number"');
  });

  it('renders chart axes, legend, and accessible source-data table', () => {
    const widget: Widget = {contractVersion:1,kind:'chart',title:'Annual totals',chartType:'line',xLabel:'Year',yLabel:'Count',series:[{label:'Observed',points:[{x:'2024',y:2},{x:'2025',y:5}]}]};
    const html=renderToStaticMarkup(<ChatWidgetRenderer widget={widget} messageId="m2" index={0} onCheck={()=>{}} onValue={()=>{}}/>);
    expect(html).toContain('role="img"');
    expect(html).toContain('Year');
    expect(html).toContain('Observed · Count');
    expect(html).toContain('View data table');
    expect(html).toContain('<caption>Annual totals: Count by Year</caption>');
  });
});
