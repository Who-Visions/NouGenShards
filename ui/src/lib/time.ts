// Eastern-time display helpers. The zone label (EDT/EST) is computed by Intl, never hardcoded.
const ZONE = 'America/New_York';
const TZ_SUFFIX = /(?:Z|[+-]\d{2}(?::?\d{2})?)$/i;

// Strings without a timezone designator (e.g. SQLite "2026-09-30 15:00:00") are UTC.
// Only the time portion is inspected: the "-" inside the date must not count as an offset.
function parseTimestamp(input: string): Date {
  let s = input.trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) s += 'T00:00:00Z';
  else {
    s = s.replace(' ', 'T');
    if (!TZ_SUFFIX.test(s.slice(s.indexOf('T') + 1))) s += 'Z';
  }
  return new Date(s);
}

const stamp = new Intl.DateTimeFormat('en-US', {
  timeZone: ZONE, month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', second: '2-digit', hour12: true, timeZoneName: 'short',
});
const clock = new Intl.DateTimeFormat('en-US', {
  timeZone: ZONE, hour: 'numeric', minute: '2-digit', second: '2-digit', hour12: true, timeZoneName: 'short',
});

export function formatEasternTime(dateInput?: string): string {
  if (!dateInput || !dateInput.trim()) return 'Recently';
  const d = parseTimestamp(dateInput);
  return isNaN(d.getTime()) ? dateInput : stamp.format(d);
}

export function getLiveEasternClock(now: Date = new Date()): string {
  return clock.format(now);
}
