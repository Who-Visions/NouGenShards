import { plan, reply, type PlannedCall } from "@/lib/agent"
import { bench, gates, ngs } from "@/lib/engine"

export const runtime = "nodejs"
export const dynamic = "force-dynamic"

async function exec(c: PlannedCall): Promise<Record<string, unknown>> {
  if (c.tool === "gates") return (await gates()) as unknown as Record<string, unknown>
  if (c.tool === "bench") return bench(Number(c.args[0]))
  return ngs([c.tool, ...c.args])
}

// Streams NDJSON: one "plan" line, then a "start" and "result" line per tool
// call, then one "reply" line. The client renders each tool as a Trace line.
export async function POST(req: Request) {
  const { text } = (await req.json().catch(() => ({}))) as { text?: string }
  const input = String(text ?? "").slice(0, 4000)
  const p = plan(input)
  const enc = new TextEncoder()

  const stream = new ReadableStream({
    async start(controller) {
      const send = (o: unknown) => controller.enqueue(enc.encode(JSON.stringify(o) + "\n"))
      send({ type: "plan", intent: p.intent, calls: p.calls.map(({ id, tool, label, display }) => ({ id, tool, label, display })) })
      const results: Record<string, unknown>[] = []
      for (const c of p.calls) {
        send({ type: "start", id: c.id })
        const t0 = Date.now()
        let out: Record<string, unknown>
        try {
          out = await exec(c)
        } catch (e) {
          out = { ok: false, error: e instanceof Error ? e.message : String(e) }
        }
        results.push(out)
        send({ type: "result", id: c.id, ms: Date.now() - t0, output: out })
      }
      send({ type: "reply", text: reply(p, results) })
      controller.close()
    },
  })

  return new Response(stream, { headers: { "content-type": "application/x-ndjson; charset=utf-8", "cache-control": "no-store" } })
}
