// Fleet NGS scorecard. A dated SNAPSHOT copied from fleet shards, not a live
// feed: the private judge repo (nougenai/nougenshards-ngs) is not reachable
// from here. Each row names the shard it came from so it can be re-checked.

export type Entry = {
  lane: string
  commit: string
  language: string
  judge: string
  behaviour: string
  crash: string
  note: string
  source: string
}

export const SCORECARD_AS_OF = "Nov 23, 2026, 6:50 PM ET"

export const ENTRIES: Entry[] = [
  {
    lane: "Phoebus",
    commit: "059bf4cb (PR 1205) + GCC fixes e32fc007 (PR 1216)",
    language: "C11, also C17 and C++11",
    judge: "6/6",
    behaviour: "26/26",
    crash: "5/5",
    note: "GCC gate green after PR 1216: 23,466 checks, 0 failed",
    source: "shard 32832@db7",
  },
  {
    lane: "WhoArt",
    commit: "2371aa4f",
    language: "C11",
    judge: "5/5",
    behaviour: "26/26",
    crash: "5/5",
    note: "Scored on the private judge harness",
    source: "shard 39641@db7",
  },
  {
    lane: "meta-app engine/ngs",
    commit: "engine/ngs in Who-Visions/NouGenShards",
    language: "C11",
    judge: "header ok",
    behaviour: "117/117",
    crash: "29/29",
    note: "The engine this console runs live",
    source: "shard 31779@db8",
  },
  {
    lane: "Blade",
    commit: "2619f5d9",
    language: "Rust",
    judge: "flagged",
    behaviour: "n/a",
    crash: "n/a",
    note: "Ships no ngs.h, outside the C contract",
    source: "shard 40066@db1",
  },
]

// Phoebus 50K bench (bench/bench_50k.c), from shard 32832@db7.
export const BENCH_50K = [
  { label: "Bulk ingest", value: "4,146/s" },
  { label: "Batch of 100, durable", value: "4,199/s" },
  { label: "Durable singles", value: "1,937/s", detail: "p50 0.47 ms, p99 1.11 ms" },
  { label: "8 writers", value: "6,192/s" },
  { label: "Get", value: "249K/s", detail: "p50 3.7 us" },
  { label: "Scan", value: "348K/s" },
  { label: "Full verify", value: "754/s", detail: "66 s for 50K" },
  { label: "Reopen", value: "0.15 s" },
  { label: "Size", value: "455 B/fact" },
]
