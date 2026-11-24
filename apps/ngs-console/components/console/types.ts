export type ToolCall = {
  id: string
  tool: string
  label: string
  display: string
  state: "pending" | "running" | "done"
  ms?: number
  output?: Record<string, unknown>
}

export type Turn =
  | { id: string; role: "user"; text: string }
  | { id: string; role: "agent"; calls: ToolCall[]; text?: string; intent?: string }
