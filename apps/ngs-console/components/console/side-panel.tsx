"use client"

import * as React from "react"
import { GaugeIcon } from "lucide-react"

import { BENCH_50K, ENTRIES, SCORECARD_AS_OF } from "@/lib/scorecard"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Spinner } from "@/components/ui/spinner"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

type Json = Record<string, unknown>
type Fact = { id: string; ns: string; kind: string; seq: number; title: string; body: string; tags?: string[]; t_record_us?: number }

function fmt(x: unknown, d = 0) {
  return typeof x === "number" ? x.toLocaleString("en-US", { maximumFractionDigits: d }) : "n/a"
}

// Event times are microseconds since the Unix epoch; shown in 12-hour Eastern.
function eastern(us?: number) {
  if (!us) return ""
  return new Date(us / 1000).toLocaleString("en-US", {
    timeZone: "America/New_York",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }) + " ET"
}

export function SidePanel({ refresh }: { refresh: number }) {
  const [engine, setEngine] = React.useState<{ live: boolean; stats: Json } | null>(null)
  const [facts, setFacts] = React.useState<{ total?: number; facts?: Fact[]; mocked?: boolean } | null>(null)
  const [bench, setBench] = React.useState<Json | null>(null)
  const [benching, setBenching] = React.useState(false)

  React.useEffect(() => {
    fetch("/api/engine").then((r) => r.json()).then(setEngine).catch(() => setEngine(null))
    fetch("/api/facts?limit=25").then((r) => r.json()).then(setFacts).catch(() => setFacts(null))
  }, [refresh])

  async function runBench() {
    setBenching(true)
    try {
      const res = await fetch("/api/agent", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ text: "bench 5000" }) })
      const lines = (await res.text()).trim().split("\n").map((l) => JSON.parse(l))
      setBench((lines.find((l) => l.type === "result")?.output as Json) ?? null)
    } finally {
      setBenching(false)
    }
  }

  const stats = engine?.stats ?? {}

  return (
    <Tabs defaultValue="scorecard" className="flex h-full min-h-0 flex-col gap-3">
      <div className="flex items-center justify-between gap-3 px-5 pt-5">
        <TabsList>
          <TabsTrigger value="scorecard">Scorecard</TabsTrigger>
          <TabsTrigger value="facts">Facts</TabsTrigger>
          <TabsTrigger value="engine">Engine</TabsTrigger>
        </TabsList>
        {engine && (
          <Badge variant={engine.live ? "default" : "secondary"} className={engine.live ? "bg-ngs text-background" : ""}>
            {engine.live ? "Live engine" : "Recorded data"}
          </Badge>
        )}
      </div>

      <TabsContent value="scorecard" className="min-h-0 flex-1 overflow-y-auto px-5 pb-5">
        <div className="flex flex-col gap-4">
          <Card size="sm">
            <CardHeader>
              <CardTitle>Bake-off judge results</CardTitle>
              <CardDescription>Snapshot from fleet shards, {SCORECARD_AS_OF}. The judge repo is private, so this is not live.</CardDescription>
            </CardHeader>
            <CardContent>
              <Table className="text-xs">
                <TableHeader>
                  <TableRow>
                    <TableHead>Lane</TableHead>
                    <TableHead>Judge</TableHead>
                    <TableHead>Behav.</TableHead>
                    <TableHead>Crash</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {ENTRIES.map((e) => (
                    <TableRow key={e.lane} title={`${e.commit}\n${e.language}\n${e.note}\n${e.source}`}>
                      <TableCell className="font-medium whitespace-normal">
                        {e.lane}
                        <div className="text-xs font-normal text-muted-foreground">{e.language}</div>
                      </TableCell>
                      <TableCell>{e.judge === "flagged" ? <Badge variant="destructive">flagged</Badge> : e.judge}</TableCell>
                      <TableCell className="tabular-nums">{e.behaviour}</TableCell>
                      <TableCell className="tabular-nums">{e.crash}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <Card size="sm">
            <CardHeader>
              <CardTitle>Phoebus 50K benchmark</CardTitle>
              <CardDescription>bench_50k.c, from shard 32832@db7.</CardDescription>
            </CardHeader>
            <CardContent className="grid grid-cols-3 gap-3">
              {BENCH_50K.map((b) => (
                <div key={b.label} className="flex flex-col gap-0.5 rounded-md bg-muted/50 p-2.5">
                  <div className="text-xs text-muted-foreground">{b.label}</div>
                  <div className="text-sm font-medium tabular-nums">{b.value}</div>
                  {b.detail && <div className="text-[11px] text-muted-foreground">{b.detail}</div>}
                </div>
              ))}
            </CardContent>
          </Card>

          <Card size="sm">
            <CardHeader>
              <CardTitle>Bench this engine</CardTitle>
              <CardDescription>5,000 signed facts on a scratch log, through ngs_cli.</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <Button variant="outline" size="sm" className="w-fit" onClick={runBench} disabled={benching}>
                {benching ? <Spinner /> : <GaugeIcon />}
                {benching ? "Running" : "Run bench"}
              </Button>
              {bench && (
                <div className="grid grid-cols-3 gap-3">
                  <Stat label="Ingest" value={`${fmt(bench.write_per_sec)}/s`} />
                  <Stat label="Scan" value={`${fmt(bench.scan_per_sec)}/s`} />
                  <Stat label="Verify" value={`${fmt(bench.verify_per_sec)}/s`} />
                  {bench.mocked === true && <div className="col-span-3 text-xs text-muted-foreground">Recorded run, the engine binary is not built here.</div>}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </TabsContent>

      <TabsContent value="facts" className="min-h-0 flex-1 overflow-y-auto px-5 pb-5">
        <div className="flex flex-col gap-2">
          <div className="text-sm text-muted-foreground">
            {fmt(facts?.total)} facts in the console log{facts?.mocked ? ", recorded data" : ""}. Newest first.
          </div>
          {(facts?.facts ?? []).slice().reverse().map((f) => (
            <Card key={f.id} size="sm">
              <CardHeader>
                <CardTitle className="text-sm">{f.title}</CardTitle>
                <CardDescription className="flex flex-wrap items-center gap-1.5">
                  <Badge variant="outline">{f.kind}</Badge>
                  <Badge variant="outline">{f.ns}</Badge>
                  <span>seq {f.seq}</span>
                  <span>{eastern(f.t_record_us)}</span>
                </CardDescription>
              </CardHeader>
              {f.body !== f.title && <CardContent className="text-sm text-muted-foreground">{f.body}</CardContent>}
            </Card>
          ))}
        </div>
      </TabsContent>

      <TabsContent value="engine" className="min-h-0 flex-1 overflow-y-auto px-5 pb-5">
        <Card size="sm">
          <CardHeader>
            <CardTitle>engine/ngs</CardTitle>
            <CardDescription>Signed, hash chained, append only log. BLAKE3, Ed25519, CRC32C.</CardDescription>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-3">
            <Stat label="Version" value={String(stats.version ?? "n/a")} />
            <Stat label="Facts" value={fmt(stats.facts)} />
            <Stat label="Text bytes" value={fmt(stats.text_bytes)} />
            <Stat label="Scan" value={`${fmt(stats.scan_ms, 3)} ms`} />
            <div className="col-span-2 flex flex-col gap-0.5 rounded-md bg-muted/50 p-2.5">
              <div className="text-xs text-muted-foreground">Node public key</div>
              <div className="font-mono text-xs break-all">{String(stats.node_pubkey ?? "n/a")}</div>
            </div>
            <div className="col-span-2 text-xs text-muted-foreground">
              Recall returns MISUSE in M1 (fused recall lands in M4), so the agent falls back to a keyword scan and says so.
            </div>
          </CardContent>
        </Card>
      </TabsContent>
    </Tabs>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5 rounded-md bg-muted/50 p-2.5">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-sm font-medium tabular-nums">{value}</div>
    </div>
  )
}
