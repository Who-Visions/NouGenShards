// In-memory stand-in for the JoinCoordinator Durable Object namespace: it runs the
// real class against a Map, so tests exercise the same serialized logic as production.
import { JoinCoordinator } from "../../workers/join/worker.js";

export function fakeCoord() {
  const m = new Map();
  const storage = {
    get: async (k) => m.get(k),
    put: async (k, v) => {
      if (typeof k === "object") { for (const [kk, vv] of Object.entries(k)) m.set(kk, vv); }
      else m.set(k, v);
    },
  };
  const obj = new JoinCoordinator({ storage });
  return {
    store: m,
    idFromName: (n) => n,
    get: () => ({ fetch: (_u, init) => obj.fetch(new Request("https://coord/op", init)) }),
  };
}
