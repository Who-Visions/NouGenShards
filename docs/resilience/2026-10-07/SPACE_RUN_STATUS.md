# Internal Hugging Face Space execution

2026-10-07: Dave authorized using internal Space AIs and obtaining credentials through Keymaker.

- Keymaker resolved a Hugging Face credential in process memory. Authenticated identity: WhoVisions. No credential is stored in these artifacts.
- WhoVisions/nga_hgf_Space is RUNNING on cpu-basic. The public rhea_chat API requires an explicit empty history for direct calls. Its inference backend returns HTTP 402: inference credits exhausted. No review output was produced.
- WhoVisions/qwen-aggressive-chat is RUNNING on cpu-basic. /health returned 200; /v1/models identified Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf.
- Three authenticated requests were submitted through /v1/chat/completions using run_qwen_tasks.py. Server /slots confirmed active task IDs 1348, 1349 and 1350, with 59 decoded tokens each at the last observation. This is execution evidence, not completion evidence.
- Work packets: external-effect journal and crash reconciliation; concurrent immutable budget ledger; evidence promotion and critical-refutation handling.
- Each response is capped at 900 tokens; the reported per-slot context is 2048 tokens. The runner saves qwen_journal.json, qwen_budget.json and qwen_evidence.json when responses arrive, or sanitized error records if requests fail. Its request timeout is 1200 seconds. Slow CPU inference may exceed this timeout.
- No paid hardware, subscriptions, deployments or Space source changes were made. No AI output has yet been accepted or executed.
- Local baseline verification: python -m unittest -q test_resilience_core: 21 tests passed.

Follow-up: all three direct Qwen requests reached the client timeout without returning usable responses. The sanitized qwen_journal.json, qwen_budget.json and qwen_evidence.json records preserve TimeoutError outcomes. Active inference slots demonstrated execution, but no successful completed review or generated implementation is claimed.

Before applying generated code, review actual responses, check truncation/finish_reason, and add meaningful regression tests. Model responses are proposals, never formal proof or production certification. Continue all inspection and verification through NouGen Context Mode.
