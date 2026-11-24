"use client"

import * as React from "react"

import { Chat } from "@/components/console/chat"
import { SidePanel } from "@/components/console/side-panel"

export function Console() {
  const [refresh, setRefresh] = React.useState(0)
  return (
    <div className="flex h-svh flex-col">
      <header className="flex items-center gap-3 border-b px-6 py-3">
        <div className="size-2 rounded-full bg-ngs" />
        <div className="font-medium">NGS console</div>
        <div className="text-sm text-muted-foreground">NouGenShards native engine</div>
        <div className="ms-auto rounded-md border px-2 py-0.5 text-xs text-muted-foreground">Draft</div>
      </header>
      <main className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[minmax(0,1fr)_480px]">
        <section className="min-h-0 border-b lg:border-r lg:border-b-0">
          <Chat onActivity={() => setRefresh((r) => r + 1)} />
        </section>
        <aside className="min-h-0">
          <SidePanel refresh={refresh} />
        </aside>
      </main>
    </div>
  )
}
