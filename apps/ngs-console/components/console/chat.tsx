"use client"

import * as React from "react"
import { ArrowUpIcon, CpuIcon, RotateCwIcon } from "lucide-react"

import { Bubble, BubbleContent } from "@/components/ui/bubble"
import { Button } from "@/components/ui/button"
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupTextarea } from "@/components/ui/input-group"
import { Message, MessageContent } from "@/components/ui/message"
import {
  MessageScroller,
  MessageScrollerButton,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerProvider,
  MessageScrollerViewport,
} from "@/components/ui/message-scroller"
import { Trace } from "@/components/ui/trace"
import { Markdown } from "@/components/console/markdown"
import { ToolRow } from "@/components/console/tool-row"
import type { ToolCall, Turn } from "@/components/console/types"

const SUGGESTIONS = [
  "Run the judge gates",
  "Remember that the Blade 502 stopgap comes out after PR 1200",
  "Verify the chain",
  "Show the last 10 facts",
  "Bench 5,000 facts",
  "Recall Blade",
]

let n = 0
const uid = () => `t${Date.now().toString(36)}${(n++).toString(36)}`

export function Chat({ onActivity }: { onActivity?: () => void }) {
  const [turns, setTurns] = React.useState<Turn[]>([])
  const [text, setText] = React.useState("")
  const [busy, setBusy] = React.useState(false)
  const formRef = React.useRef<HTMLFormElement>(null)

  const patchAgent = React.useCallback((id: string, fn: (t: Extract<Turn, { role: "agent" }>) => Extract<Turn, { role: "agent" }>) => {
    setTurns((all) => all.map((t) => (t.id === id && t.role === "agent" ? fn(t) : t)))
  }, [])

  async function send(input: string) {
    const msg = input.trim()
    if (!msg || busy) return
    const agentId = uid()
    setTurns((all) => [...all, { id: uid(), role: "user", text: msg }, { id: agentId, role: "agent", calls: [] }])
    setText("")
    setBusy(true)
    try {
      const res = await fetch("/api/agent", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ text: msg }),
      })
      if (!res.body) throw new Error("no response body")
      const reader = res.body.getReader()
      const dec = new TextDecoder()
      let buf = ""
      for (;;) {
        const { value, done } = await reader.read()
        if (done) break
        buf += dec.decode(value, { stream: true })
        let nl: number
        while ((nl = buf.indexOf("\n")) >= 0) {
          const line = buf.slice(0, nl).trim()
          buf = buf.slice(nl + 1)
          if (!line) continue
          const ev = JSON.parse(line)
          if (ev.type === "plan") {
            patchAgent(agentId, (t) => ({
              ...t,
              intent: ev.intent,
              calls: (ev.calls as Omit<ToolCall, "state">[]).map((c) => ({ ...c, state: "pending" })),
            }))
          } else if (ev.type === "start") {
            patchAgent(agentId, (t) => ({ ...t, calls: t.calls.map((c) => (c.id === ev.id ? { ...c, state: "running" } : c)) }))
          } else if (ev.type === "result") {
            patchAgent(agentId, (t) => ({
              ...t,
              calls: t.calls.map((c) => (c.id === ev.id ? { ...c, state: "done", ms: ev.ms, output: ev.output } : c)),
            }))
          } else if (ev.type === "reply") {
            patchAgent(agentId, (t) => ({ ...t, text: ev.text }))
          }
        }
      }
    } catch (e) {
      patchAgent(agentId, (t) => ({ ...t, text: `The console could not reach its API: ${e instanceof Error ? e.message : String(e)}` }))
    } finally {
      setBusy(false)
      onActivity?.()
    }
  }

  return (
    <MessageScrollerProvider>
      <div className="flex h-full min-h-0 flex-col">
        <div className="flex items-start justify-between gap-4 px-6 pt-5 pb-3">
          <div className="flex flex-col gap-0.5">
            <div className="font-medium">Engine agent</div>
            <div className="text-sm text-muted-foreground">Ask in plain words. Every step is a real call into ngs.h.</div>
          </div>
          <Button variant="outline" size="icon-sm" aria-label="Clear conversation" disabled={busy || turns.length === 0} onClick={() => setTurns([])}>
            <RotateCwIcon />
          </Button>
        </div>

        <div className="min-h-0 flex-1">
          {turns.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-5 px-6 text-center">
              <div className="flex size-10 items-center justify-center rounded-lg bg-muted text-ngs">
                <CpuIcon className="size-5" />
              </div>
              <div className="flex max-w-sm flex-col gap-1">
                <div className="font-medium">What should the engine do?</div>
                <div className="text-sm text-muted-foreground">
                  Store a signed fact, read the log, verify the chain, run the judge gates or a bench.
                </div>
              </div>
              <div className="flex max-w-lg flex-wrap justify-center gap-2">
                {SUGGESTIONS.map((s) => (
                  <Button key={s} variant="outline" size="sm" onClick={() => send(s)}>
                    {s}
                  </Button>
                ))}
              </div>
            </div>
          ) : (
            <MessageScroller>
              <MessageScrollerViewport>
                <MessageScrollerContent aria-busy={busy} className="gap-6 px-6 pb-4">
                  {turns.map((turn) =>
                    turn.role === "user" ? (
                      <MessageScrollerItem key={turn.id} messageId={turn.id} scrollAnchor>
                        <Message align="end">
                          <MessageContent>
                            <Bubble align="end" variant="muted">
                              <BubbleContent>{turn.text}</BubbleContent>
                            </Bubble>
                          </MessageContent>
                        </Message>
                      </MessageScrollerItem>
                    ) : (
                      <MessageScrollerItem key={turn.id} messageId={turn.id}>
                        <Message>
                          <MessageContent className="gap-3">
                            {turn.calls.length > 0 && (
                              <Trace>
                                {turn.calls.map((c) => (
                                  <ToolRow key={c.id} call={c} />
                                ))}
                              </Trace>
                            )}
                            {turn.text && <Markdown>{turn.text}</Markdown>}
                          </MessageContent>
                        </Message>
                      </MessageScrollerItem>
                    )
                  )}
                </MessageScrollerContent>
              </MessageScrollerViewport>
              <MessageScrollerButton />
            </MessageScroller>
          )}
        </div>

        <div className="px-6 pt-2 pb-5">
          <form
            ref={formRef}
            onSubmit={(e) => {
              e.preventDefault()
              void send(text)
            }}
          >
            <InputGroup>
              <InputGroupTextarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Remember, verify, run the gates, bench..."
                aria-label="Message"
                className="min-h-14"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault()
                    formRef.current?.requestSubmit()
                  }
                }}
              />
              <InputGroupAddon align="block-end" className="pt-1">
                <span className="text-xs text-muted-foreground">Enter to send, Shift Enter for a new line</span>
                <InputGroupButton type="submit" variant="default" size="icon-sm" disabled={busy || !text.trim()} className="ml-auto">
                  <ArrowUpIcon />
                  <span className="sr-only">Send</span>
                </InputGroupButton>
              </InputGroupAddon>
            </InputGroup>
          </form>
        </div>
      </div>
    </MessageScrollerProvider>
  )
}
