// Pure gating rules for the aiwithdav3 reviewer. No I/O here, so the rules are unit-testable.
// Follow-ups to the #1079 review (2026-11-15): private repos never leave the machine, a truncated
// diff can never be APPROVEd, and no verdict is posted when no primary lane answered.

export const CLOUD_LANES = ["huggingface", "openrouter", "ollama-cloud", "agy"] as const;

// Private repos: only lanes that keep the diff on this machine. agy and the cloud routes send it to a third party.
export function allowedLanes<L extends string>(lanes: readonly L[], repoIsPrivate: boolean): L[] {
  return repoIsPrivate ? lanes.filter((l) => !(CLOUD_LANES as readonly string[]).includes(l)) : [...lanes];
}

export type Verdict = "APPROVE" | "REQUEST_CHANGES" | "COMMENT";

// Returns the verdict that may be posted, or null when nothing may be posted.
export function finalVerdict(args: {
  primaryOk: boolean;
  verdict: Verdict;
  sup: { agree: boolean; verdict: string } | null;
  findings: { severity?: string }[];
  truncated: boolean;
}): Verdict | null {
  if (!args.primaryOk) return null;
  let v = args.verdict;
  const sup = args.sup;
  // no supervisor = no binding verdict: only COMMENT goes out unchecked
  if (!sup && v !== "COMMENT") v = "COMMENT";
  if (v === "APPROVE" && (!sup || !sup.agree || sup.verdict !== "APPROVE")) v = "COMMENT";
  // a partial diff can show a problem but cannot prove a whole PR is fine
  if (v === "APPROVE" && args.truncated) v = "COMMENT";
  if (v === "REQUEST_CHANGES" && !args.findings.some((f) => f.severity === "P1")) v = "COMMENT";
  if (v === "REQUEST_CHANGES" && sup && !sup.agree && sup.verdict !== "REQUEST_CHANGES") v = "COMMENT";
  return v;
}
