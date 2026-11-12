import React from 'react';
import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import BatteryReader from './BatteryReader';

describe('Cortex Hub battery reader', () => {
  it('outside the desktop app: says telemetry needs the desktop app and disables refresh', () => {
    const html = renderToStaticMarkup(<BatteryReader readBattery={async () => ({})} isDesktop={false} />);
    expect(html).toContain('aria-labelledby="battery-reader-title"');
    expect(html).toContain('available inside the Cortex Hub desktop app');
    expect(html).toMatch(/<button[^>]*class="battery-refresh"[^>]*disabled/);
  });

  it('inside the desktop app: starts its first reading and shows no web-only notice', () => {
    const html = renderToStaticMarkup(<BatteryReader readBattery={async () => ({ present: false })} isDesktop={true} />);
    expect(html).not.toContain('available inside the Cortex Hub desktop app');
    expect(html).toContain('Reading…');
  });
});
