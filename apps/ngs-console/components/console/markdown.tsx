import * as React from "react"

// Just enough markdown for the agent's replies: paragraphs, "- " lists and
// **bold**. The replies are written by lib/agent.ts, never by a model.
function inline(text: string) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? (
      <strong key={i} className="font-medium text-foreground">
        {part.slice(2, -2)}
      </strong>
    ) : (
      <React.Fragment key={i}>{part}</React.Fragment>
    )
  )
}

export function Markdown({ children }: { children: string }) {
  const blocks = children.trim().split(/\n{2,}/)
  return (
    <div className="flex flex-col gap-2 text-sm leading-relaxed">
      {blocks.map((block, i) => {
        const lines = block.split("\n")
        if (lines.every((l) => l.startsWith("- "))) {
          return (
            <ul key={i} className="flex list-disc flex-col gap-1 ps-5 marker:text-muted-foreground">
              {lines.map((l, j) => (
                <li key={j}>{inline(l.slice(2))}</li>
              ))}
            </ul>
          )
        }
        return <p key={i}>{inline(block)}</p>
      })}
    </div>
  )
}
