"use client"

import {
  CheckIcon,
  CircleDashedIcon,
  DatabaseIcon,
  FileCodeIcon,
  FlaskConicalIcon,
  GaugeIcon,
  LoaderCircleIcon,
  ShieldCheckIcon,
  TerminalIcon,
  XIcon,
} from "lucide-react"

import type { GateRun, GateTest } from "@/lib/gates"
import { CodeBlock, CodeBlockContent } from "@/components/ui/code-block"
import {
  Trace,
  TraceCollapsible,
  TraceCollapsibleContent,
  TraceCollapsibleTrigger,
  TraceIcon,
  TraceLine,
  TraceTitle,
} from "@/components/ui/trace"
import type { ToolCall } from "@/components/console/types"

const ICONS: Record<string, React.ComponentType> = {
  verify: ShieldCheckIcon,
  bench: GaugeIcon,
  gates: FlaskConicalIcon,
  scan: DatabaseIcon,
  get: DatabaseIcon,
  remember: DatabaseIcon,
  recall: DatabaseIcon,
  stats: TerminalIcon,
}

function ms(n?: number) {
  if (n === undefined) return ""
  return n >= 1000 ? `${(n / 1000).toFixed(1)} s` : `${n} ms`
}

// Tool pattern: one Trace line per engine call. Running shows the shimmer,
// a finished call opens to the raw JSON the engine returned.
export function ToolRow({ call }: { call: ToolCall }) {
  const Icon = ICONS[call.tool] ?? TerminalIcon

  if (call.state !== "done") {
    return (
      <TraceLine status={call.state === "running" ? "running" : "pending"}>
        <TraceIcon>{call.state === "running" ? <LoaderCircleIcon className="animate-spin" /> : <Icon />}</TraceIcon>
        <TraceTitle>{call.label}</TraceTitle>
      </TraceLine>
    )
  }

  const out = call.output ?? {}
  // M1 has no recall: that MISUSE is expected, so it reads as a skipped step.
  const expectedMiss = call.tool === "recall" && out.rc === 11 // NGS_MISUSE
  const failed = out.ok === false && !expectedMiss
  const mocked = out.mocked === true

  if (call.tool === "gates" && Array.isArray(out.suites)) {
    return <GateResults run={out as unknown as GateRun} ms={call.ms} />
  }

  return (
    <TraceCollapsible>
      <TraceCollapsibleTrigger>
        <TraceLine status={failed ? "error" : undefined}>
          <TraceIcon>{failed ? <XIcon /> : expectedMiss ? <CircleDashedIcon /> : <Icon />}</TraceIcon>
          <TraceTitle>
            {call.label}
            <span className="ms-2 text-xs text-muted-foreground tabular-nums">
              {ms(call.ms)}
              {mocked ? " · recorded" : ""}
            </span>
          </TraceTitle>
        </TraceLine>
      </TraceCollapsibleTrigger>
      <TraceCollapsibleContent className="flex flex-col gap-2">
        <CodeBlock size="sm">
          <CodeBlockContent className="max-h-24 text-xs">{"$ " + call.display}</CodeBlockContent>
        </CodeBlock>
        <CodeBlock size="sm" variant={failed ? "destructive" : "default"}>
          <CodeBlockContent wrap className="max-h-72 text-xs">
            {JSON.stringify(out, null, 2)}
          </CodeBlockContent>
        </CodeBlock>
      </TraceCollapsibleContent>
    </TraceCollapsible>
  )
}

function TestRow({ test }: { test: GateTest }) {
  if (test.status === "failed") {
    return (
      <TraceCollapsible>
        <TraceCollapsibleTrigger>
          <TraceLine status="error">
            <TraceIcon>
              <XIcon />
            </TraceIcon>
            <TraceTitle>{test.name}</TraceTitle>
          </TraceLine>
        </TraceCollapsibleTrigger>
        <TraceCollapsibleContent>
          <CodeBlock size="sm">
            <CodeBlockContent wrap className="max-h-64">
              {test.error}
            </CodeBlockContent>
          </CodeBlock>
        </TraceCollapsibleContent>
      </TraceCollapsible>
    )
  }
  return (
    <TraceLine>
      <TraceIcon>{test.status === "skipped" ? <CircleDashedIcon /> : <CheckIcon />}</TraceIcon>
      <TraceTitle>{test.name}</TraceTitle>
    </TraceLine>
  )
}

// Test Results pattern: the judge gates as suites, failures open first.
export function GateResults({ run, ms: took }: { run: GateRun; ms?: number }) {
  const failed = run.totals.failed > 0 || !run.ok
  return (
    <TraceCollapsible defaultOpen>
      <TraceCollapsibleTrigger>
        <TraceLine status={failed ? "error" : undefined}>
          <TraceIcon>
            <FlaskConicalIcon />
          </TraceIcon>
          <TraceTitle>
            Ran the judge gates: {run.totals.passed.toLocaleString("en-US")} passed
            {run.totals.failed ? `, ${run.totals.failed} failed` : ""}
            <span className="ms-2 text-xs text-muted-foreground tabular-nums">
              {ms(took ?? run.ms)}
              {run.mocked ? " · recorded" : ""}
            </span>
          </TraceTitle>
        </TraceLine>
      </TraceCollapsibleTrigger>
      <TraceCollapsibleContent>
        <Trace>
          {run.suites.map((suite) => {
            const bad = suite.tests.some((t) => t.status === "failed")
            return (
              <TraceCollapsible key={suite.name} defaultOpen={bad}>
                <TraceCollapsibleTrigger>
                  <TraceLine status={bad ? "error" : undefined}>
                    <TraceIcon>
                      <FileCodeIcon />
                    </TraceIcon>
                    <TraceTitle>{suite.name}</TraceTitle>
                  </TraceLine>
                </TraceCollapsibleTrigger>
                <TraceCollapsibleContent>
                  <Trace>
                    {suite.tests.map((t, i) => (
                      <TestRow key={i} test={t} />
                    ))}
                  </Trace>
                </TraceCollapsibleContent>
              </TraceCollapsible>
            )
          })}
        </Trace>
      </TraceCollapsibleContent>
    </TraceCollapsible>
  )
}
