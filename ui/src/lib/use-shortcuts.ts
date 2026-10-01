import { useEffect, useRef } from 'react';

export interface Shortcuts {
  refresh: () => void;
  focusSearch: () => void;
  quit: () => void;
}

// One window listener for F5, Ctrl/Cmd+F and Ctrl/Cmd+Q. Handlers live in a ref so
// the listener is registered once and never sees stale closures.
export function useShortcuts(handlers: Shortcuts): void {
  const latest = useRef(handlers);
  useEffect(() => { latest.current = handlers; });
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.repeat) return;
      const mod = (e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey;
      const key = e.key.toLowerCase();
      if (e.key === 'F5') { e.preventDefault(); latest.current.refresh(); }
      else if (mod && key === 'f') { e.preventDefault(); latest.current.focusSearch(); }
      else if (mod && key === 'q') { e.preventDefault(); latest.current.quit(); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);
}
