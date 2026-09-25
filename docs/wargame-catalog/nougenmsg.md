# War-game candidates — NouGenMsg

Generated from `catalog.ndjson` by `tools/wargame_catalog.py render`; do not hand-edit.

95 candidates · P0 32 · P1 63 · P2 0 · P3 0 · defend 59 · elevate 36

| id | P | kind | title |
|---|---|---|---|
| WG-0004 | P0 | defend | Close the live emit_node shell injection on whoart and blade by hand-copy of untracked files |
| WG-0020 | P0 | defend | Harden the verdict parser: a last line of 'NO' approves elevated delivery |
| WG-0035 | P0 | defend | Latch phoebus's receiver: launchd wrapper never sets NOUGEN_AGY_MSG_AUTH and SKILL.md's 'open' value latches |
| WG-0049 | P0 | defend | Retire the ten stale lane branches that each delete infra/ and the injection tests |
| WG-0061 | P0 | elevate | Build `nougenmsg doctor` that compares each node's executing build id to the repo (SOURCE.md is already wrong) |
| WG-0072 | P0 | defend | Add request timeouts and connection limits to the ThreadingHTTPServer receiver |
| WG-0083 | P0 | defend | Fence the Windows pipe timeout so a mid-turn session is retried, never pruned, on every lane |
| WG-0094 | P0 | defend | Stop --peers flashing consoles and stalling on AAAA: keep #5 and #6 from being undone by lane merges |
| WG-0104 | P0 | defend | Survive concurrent cc_sessions.json rewrites without pruning a live Claude session |
| WG-0114 | P0 | defend | Reconcile the nested and flat cc_sessions.json shapes before main's ping_claude reaches phoebus |
| WG-0122 | P0 | defend | Stop the 20s ssh timeout from killing delivered fan-outs and prompting duplicate resends |
| WG-0130 | P0 | defend | Make background fleet fan-out failures visible after the 76s double-delivery |
| WG-0138 | P0 | defend | Collapse the four-copies-per-Antigravity-ping fan-out with one message_id at the emitter |
| WG-0146 | P0 | defend | Bring whoart's untracked Outpost\NouGen bus copy under version control before the next hand-copy diverges |
| WG-0154 | P0 | elevate | B7-observability: Ship `nougenmsg doctor` comparing each node's running build_id to the repo |
| WG-0162 | P0 | defend | Alert when a :8766 receiver's auth mode drifts from required to open |
| WG-0170 | P0 | elevate | B9-devex: Converge the three phoebus install paths and the whoart 72h task limit into one supervised service per node |
| WG-0178 | P0 | defend | Capture what phoebus actually executes: infra/phoebus holds federation.py, not the bus |
| WG-0184 | P0 | elevate | B3-routing: Upgrade _probe_nodes from TCP-connect to an authenticated /health round-trip so a hung node reads unreachab… |
| WG-0189 | P0 | defend | Detect from the sender when a receiver silently drops from auth=required to auth=open |
| WG-0194 | P0 | defend | Pin which of blade's two code trees the remote CLI and scheduled task actually run |
| WG-0199 | P0 | defend | Bring whoart's untracked live bus files under git without stopping the running node |
| WG-0204 | P0 | defend | Collapse phoebus's three documented install paths into one interpreter-safe receiver |
| WG-0209 | P0 | defend | Add a sender/receiver contract test before trusting the green injection suite |
| WG-0214 | P0 | defend | Lock the cc_sessions.json rewrite so concurrent fan-outs cannot drop a live Claude session |
| WG-0219 | P0 | defend | Emit the DELIVERED/QUEUED receipt line relay dispatch keys on from main's CLI |
| WG-0224 | P0 | elevate | Make ping_antigravity able to say delivered: fix the relative import and land the tri-state |
| WG-0229 | P0 | elevate | Reconcile PR #2's cc_msg.py against main instead of the 1331234 baseline |
| WG-0234 | P0 | elevate | Publish one env-var reference and a config doctor for the five competing namespaces |
| WG-0239 | P0 | elevate | Add a scheduled cross-node synthetic ping that alerts when /health hangs rather than refuses |
| WG-0244 | P0 | elevate | Detect a quiet bus lane the way the vault-quiet incident demanded |
| WG-0248 | P0 | defend | Stop timeout-after-delivery retries from double-sending fleet broadcasts |
| WG-0363 | P1 | elevate | Roll the --stdin receiver to all three nodes before main's emit_node ssh path is used |
| WG-0379 | P1 | defend | Judge the whole message: Kaedra gate classifies text[:2000] but delivers the full body |
| WG-0395 | P1 | defend | Gate the wake path: approved message text becomes an autonomous agent prompt with skip-permissions |
| WG-0411 | P1 | defend | Pin the receiver bind per node instead of a user-env NOUGEN_AGY_MSG_BIND=0.0.0.0 fix |
| WG-0427 | P1 | defend | Fix the phoebus 8765/8766 split so the http route stops burning 15s before ssh fallback |
| WG-0443 | P1 | defend | Close GET /pop and /msg/<id> on unlatched receivers before any node is LAN-bound |
| WG-0458 | P1 | defend | Survive the day the Kaedra gateway dies: fail-closed gate silently denies all elevated delivery |
| WG-0471 | P1 | elevate | Backport the stdin-body remote Ollama curl so main stops building a shell string |
| WG-0484 | P1 | elevate | Land PR #7's delivered/queued/dropped tri-state without reverting the IPv4-first probe |
| WG-0496 | P1 | elevate | Package NouGenMsg so tools/nougenmsg.py can import its own src (pyproject from native-queue) |
| WG-0508 | P1 | elevate | Scrub owner paths and mDNS hostnames from this public repo via fleet_hosts.json |
| WG-0520 | P1 | defend | Collapse blade's two scheduled tasks pointing at two code trees into one receiver |
| WG-0532 | P1 | defend | Never launch the receiver in a visible console again: QuickEdit froze blade's loop |
| WG-0544 | P1 | defend | Retire canonical emit_node's quoted-body fallback that survives behind a metacharacter blocklist |
| WG-0556 | P1 | elevate | Roll receivers with deployment receipts: a checkout does not change the running process |
| WG-0568 | P1 | defend | Harden main's ssh fallback with canonical's BatchMode/-n options and temp-file capture |
| WG-0579 | P1 | defend | Stop the 20s ssh timeout killing --target all sends after delivery and causing duplicate retries |
| WG-0590 | P1 | elevate | Send a message_id and check the receipt before falling back from http to ssh |
| WG-0601 | P1 | elevate | Sign the origin envelope: --origin-b64 is decoded and merged unverified |
| WG-0612 | P1 | elevate | Delete Kaedra's enhanced client: literal fallback token, wrong headers, swallowed errors, false success |
| WG-0623 | P1 | elevate | Survive a long body over --text-b64 on the cmd.exe lanes without truncation or silent refusal |
| WG-0634 | P1 | defend | Stop every non-Windows box believing it is phoebus (get_current_node os.name branch) |
| WG-0645 | P1 | elevate | Replace main's hand-rolled argv scanner with argparse before the 'send --target-node' misroute recurs |
| WG-0656 | P1 | defend | Run whoart's receiver under a task with no 72h ExecutionTimeLimit and a real watchdog |
| WG-0667 | P1 | elevate | Probe deep health, not TCP connect: a hung receiver counts as reachable in --peers |
| WG-0678 | P1 | defend | Keep the two Claude registries and two SessionStart hooks from silently diverging |
| WG-0689 | P1 | elevate | Decide whether NouGenMsg is the SDK NouGenShards consumes or a mirror, then delete the other copies |
| WG-0700 | P1 | defend | Stop the receiver persisting origin_proof (owner secret) into inbox and state files |
| WG-0711 | P1 | elevate | Ship the SKILL.md addressing forms (@ollama:<model>, /pop, list-agents) or remove them from the contract |
| WG-0722 | P1 | defend | Keep cc_sessions.json ACL-locked across ping_claude's prune rewrite |
| WG-0732 | P1 | defend | Make inbox writes atomic so drain hooks never read a torn ping_*.json |
| WG-0742 | P1 | defend | Reap ~/.nougen/msg-*.md scp bodies on every node before they become an unbounded store |
| WG-0752 | P1 | defend | Keep secrets out of inbox JSON that lives forever under archive/ |
| WG-0762 | P1 | elevate | B1-protocol: Stamp one message_id at the sender and carry it through every hop, file and ledger |
| WG-0772 | P1 | defend | Unify the per-process dedup so a leg arriving by relay and by :8766 is delivered once |
| WG-0782 | P1 | defend | Lock the .agy_woken_legs.json idempotency ledger so one leg cannot wake two agy runs |
| WG-0792 | P1 | defend | Survive the day :8766 dies: main's ssh fallback sends --stdin that no fleet receiver accepts |
| WG-0802 | P1 | defend | Prevent the http-timeout-then-ssh fallback from double-delivering when the Kaedra gate runs long |
| WG-0812 | P1 | defend | Give agy_inbox_hook per-session cursors before a second Antigravity session starves |
| WG-0822 | P1 | elevate | B4-receipts: Adopt #509 read receipts in send_direct_http without letting bulk archive forge 'read' |
| WG-0832 | P1 | elevate | B4-receipts: Turn ping_claude's permanent delivery_verified=False into an observed receipt from the drain hook |
| WG-0842 | P1 | defend | Make ping_antigravity's status honest on both copies: main's .agy_msg import can never succeed |
| WG-0852 | P1 | elevate | B4-receipts: Give emit_fleet a per-node terminal-state receipt instead of strings mixed with dicts |
| WG-0862 | P1 | elevate | B2-queue: Park undeliverable @node sends in an outbox with retry instead of returning 'Error:' and dropping |
| WG-0872 | P1 | elevate | B3-routing: Unify node address resolution between _probe_nodes and send_direct_http before PR #2's hardcoded IPs land |
| WG-0882 | P1 | elevate | B3-routing: Retire get_current_node's 'not Windows means phoebus' before a Linux clone impersonates a node |
| WG-0891 | P1 | elevate | B3-routing: Add a dead-node cooldown so a down whoart does not add 20s to every fleet broadcast |
| WG-0900 | P1 | elevate | B10-fleet: Collapse the five live NouGenMsg copies into one SDK the other repos import |
| WG-0908 | P1 | elevate | B2-queue: Add retention and rotation to claude_inbox/agy_inbox before the drain hooks choke |
| WG-0916 | P1 | defend | Launch nougenmsg_node hidden: its record() print blocks under console QuickEdit like blade's NGS node |
| WG-0924 | P1 | defend | Pin blade's message receiver to one code tree now that two scheduled tasks point at two trees |
| WG-0932 | P1 | defend | Stop Kaedra's atomic-buster RELAY phase from reporting success on a swallowed 401 |
| WG-0940 | P1 | defend | Surface messages.db append failures somewhere a human reads, not the stderr of a hook |
| WG-0948 | P1 | defend | Record TIMEOUT in .agy_woken_legs.json so a slow leg is not re-executed on the next wake |
| WG-0956 | P1 | defend | Resolve the contradiction: ping_claude promises later sessions the inbox copy, the drain hook seeds them past it |
| WG-0963 | P1 | defend | Make inbox filenames collision-proof: ms timestamps overwrite concurrent pings |
| WG-0970 | P1 | elevate | B9-devex: Package NouGenMsg so tools/nougenmsg.py imports its own src and deploy stops being copy-per-node |
| WG-0976 | P1 | elevate | B5-security: Adopt native-queue's plaintext-off-loopback refusal in send_direct_http without stranding LAN-only nodes |
| WG-0982 | P1 | elevate | B6-parity: Rebase PR #2 onto main so merging cc_msg parity cannot delete _probe_nodes and the node-resolve tests |
| WG-0987 | P1 | defend | Stop @all broadcasts from timing out on Ollama cold starts with 2s local and 8s remote budgets |
| WG-0991 | P1 | defend | Honor NOUGEN_CODEX_INBOX and NOUGEN_AGY_INBOX in read_inbox and --peers so counts match the receivers |
| WG-0995 | P1 | defend | Stop a live socket write plus inbox drain from injecting the same ping twice into one Claude session |
| WG-0999 | P1 | defend | ACL-lock an existing cc_sessions.json: icacls only runs when the file is first created |

---

### WG-0004 · P0 · defend · effort M

**Close the live emit_node shell injection on whoart and blade by hand-copy of untracked files**

- Failure surface: The files whoart actually executes (%USERPROFILE%\Outpost\NouGen, untracked per infra/whoart/SOURCE.md) and blade's 195-line variant still interpolate {text} into the remote ssh command inside double quotes; any message containing $(...), backticks or a bare quote runs as code on the target node. Found 2026-09-04 when '(no agy binary on this host)' came back 'zsh:1: no matches found'.
- First fork: if you observe `git ls-files --error-unmatch` on the node still saying the executing copy is untracked -> replace it by copy and record sha256 in SOURCE.md before any commit; else check the tracked file out and restart the receiver, then confirm build_id changed via an authenticated POST.
- Evidence: `infra/whoart/nougenmsg.py`, `infra/blade/nougenmsg.py`, `infra/whoart/SOURCE.md`
- Lens: injection · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Confirmed: nougenmsg/infra/whoart/nougenmsg.py (496 lines, matches SOURCE.md's noted untracked-copy provenance) and nougenmsg/infra/blade/nougenmsg.py (195 lines) both build remote_cmd = f'... --local "{text}"' interpolating {text} inside double quotes before subprocess.run(['ssh', node/n, remote_cmd]) -- the classic injection pattern, and infra/whoart/SOURCE.md documents both files as untracked/l

### WG-0020 · P0 · defend · effort M

**Harden the verdict parser: a last line of 'NO' approves elevated delivery**

- Failure surface: The gate takes the LAST non-empty line of the model reply and maps 'NO' to APPROVE; a small local model (kaedracode:e2b) that echoes or is steered by the message to end with 'NO' approves it. 2026-09-03 and 2026-09-08 measurements already showed contradictory and reworded-dependent verdicts on benign prose.
- First fork: if you observe gate_ambiguous or policy_ok verdicts whose first line says YES -> switch to structured JSON output with schema validation; else at minimum require the labelled 'APPROVE'/'DENY' token only and drop the YES/NO aliases.
- Evidence: `NouGenShards/tools/_agy_live_delivery.py`
- Lens: prompt-injection · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Confirmed: NouGenShards/tools/_agy_live_delivery.py takes the last non-empty stripped line of the model reply and explicitly maps verdict=='NO' to APPROVE (and 'YES' to DENY) alongside APPROVE/DENY tokens, with inline comments describing exactly this NO-implies-APPROVE quirk and its history of inconsistent verdicts.

### WG-0035 · P0 · defend · effort M

**Latch phoebus's receiver: launchd wrapper never sets NOUGEN_AGY_MSG_AUTH and SKILL.md's 'open' value latches**

- Failure surface: nougenmsg_node.py latches on any NOUGEN_AGY_MSG_AUTH value except ''/0/off/false/optional, so the SKILL.md-documented 'open' actually latches while '' does not; only tools/nougen_live.ps1 sets the latch (Windows). The macOS wrapper exports whatever keymaker returns (possibly '') with no latch, so a vault miss on a LAN-bound phoebus flips the receiver to open(unlatched) - the 37-minute fail-open observed 2026-09-03.
- First fork: if you observe phoebus's startup line printing auth=open(unlatched) with NOUGEN_AGY_MSG_BIND=0.0.0.0 -> export NOUGEN_AGY_MSG_AUTH=1 in the wrapper and restart; else align the doc with the parser and add a launch test that an empty token plus LAN bind refuses mutations.
- Evidence: `NouGenShards/tools/nougenmsg_node.py`, `NouGenShards/tools/launchd/nougenmsg_node_launch.sh`, `NouGenShards/skills/nougenmsg/SKILL.md`
- Lens: auth · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Confirmed: nougenmsg_node.py line 105-106 latches on any value except ''/0/off/false/optional (so 'open' latches, '' does not, matching the claim exactly); grep of launchd/nougenmsg_node_launch.sh shows it exports NOUGEN_AGY_MSG_TOKEN/KAEDRA_GATEWAY_TOKEN/NOUGEN_USER_ORIGIN_TOKEN but never NOUGEN_AGY_MSG_AUTH.
- #550 families: 38

### WG-0049 · P0 · defend · effort M

**Retire the ten stale lane branches that each delete infra/ and the injection tests**

- Failure surface: Diffed against main, origin/codex/nougenmsg-lan-wake, blade/nougenmsg-infra, fix/peers-live-no-flash (committed 2026-09-23 yet still on the 09-03 base), phoebus/*, whoart/*, fix/emit-node-injection and codex/nougenmsg-native-queue all remove infra/, tests/test_emit_node_injection.py and/or the stdin fix; any 'merge the lane' action by a node agent reopens the remote-shell injection with no failing test to stop it.
- First fork: if you observe a lane branch with commits newer than 28b38fe -> cherry-pick those commits onto main and delete the branch; else delete it outright and protect main with a required run of tests/test_emit_node_injection.py.
- Evidence: `origin/fix/peers-live-no-flash`, `origin/codex/nougenmsg-lan-wake`, `tests/test_emit_node_injection.py`
- Lens: supply-chain · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Confirmed by diffing each named branch against main: origin/codex/nougenmsg-lan-wake, origin/blade/nougenmsg-infra and origin/fix/peers-live-no-flash all delete infra/whoart/* and tests/test_emit_node_injection.py relative to main; origin/fix/peers-live-no-flash's tip commit is dated 2026-09-23 but its merge-base is the pre-security-fix 1331234 commit, and 28b38fe is confirmed not an ancestor of i

### WG-0061 · P0 · elevate · effort M

**Build `nougenmsg doctor` that compares each node's executing build id to the repo (SOURCE.md is already wrong)**

- Failure surface: infra/whoart/SOURCE.md says whoart runs the 311-line c369f49e variant, but infra/whoart/nougenmsg.py is 496 lines with sha 5d0a08da, matching none of the three recorded hashes; the provenance table cannot tie any snapshot to any node. nougenmsg_node.py already computes build_id() of the loaded file and returns it on authenticated POSTs, so a doctor can ask each node what it runs.
- First fork: if you observe an authenticated POST returning build != sha256(repo file)[:12] on a node -> record drift and refuse to declare the fix landed; else regenerate SOURCE.md from the doctor's output and gate merges on a fresh run.
- Evidence: `infra/whoart/SOURCE.md`, `infra/whoart/nougenmsg.py`, `NouGenShards/tools/nougenmsg_node.py`
- Lens: B7-observability · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Confirmed precisely: infra/whoart/SOURCE.md's divergence table lists three hashes (d28b16bb/195 lines, c369f49e/311 lines, 5096457f/496 lines) and states whoart runs the 311-line c369f49e variant, but the actual infra/whoart/nougenmsg.py on disk is 496 lines with sha256[:12]=5d0a08daab, which matches none of the three recorded hashes.
- #550 families: 28

### WG-0072 · P0 · defend · effort M

**Add request timeouts and connection limits to the ThreadingHTTPServer receiver**

- Failure surface: nougenmsg_node.py serves with ThreadingHTTPServer, daemon threads, HTTP/1.1 keep-alive and no socket timeout; a client that opens and idles (or today's paused-console scenario) accumulates CLOSE_WAIT sockets and threads until the node stops answering /health. An authorized POST body is read to Content-Length with no maximum.
- First fork: if you observe netstat on a node showing dozens of CLOSE_WAIT on :8766 -> restart and set Handler.timeout; else cap Content-Length for authorized POSTs and bound concurrent connections.
- Evidence: `NouGenShards/tools/nougenmsg_node.py`
- Lens: runtime · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: NouGenShards/tools/nougenmsg_node.py:55/437-438 uses ThreadingHTTPServer with daemon_threads=True and no explicit socket/handler timeout found, and the body-read path caps only rejected requests at 1 MiB per the docstring at line 306, matching the claim that authorized POSTs aren't capped the same way.
- #550 families: 43

### WG-0083 · P0 · defend · effort S

**Fence the Windows pipe timeout so a mid-turn session is retried, never pruned, on every lane**

- Failure surface: On 2026-09-02 a live Claude session was pruned from the registry on a WaitNamedPipe timeout; main now prunes only on winerror 2/3 or ENOENT/ECONNREFUSED, but _agy_live_delivery's deliver_to_live_sessions and cc_msg.py implement their own prune rules, and ECONNREFUSED on a Unix socket whose process is briefly restarting still prunes. Three copies of the rule can drift back to the bug.
- First fork: if you observe pruned entries for sessions still open -> the rule diverged again, re-register via the hook and diff the three implementations; else move _endpoint_gone into one module all three import and test it with the 2026-09-02 error code.
- Evidence: `src/nougenmsg.py`, `NouGenShards/tools/_agy_live_delivery.py`, `NouGenShards/tools/cc_msg.py`
- Lens: runtime · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: src/nougenmsg.py:175-182 defines _endpoint_gone checking winerror and errno in (ENOENT, ECONNREFUSED); NouGenShards/tools/_agy_live_delivery.py:290 independently checks `exc.errno in (errno.ENOENT, errno.ECONNREFUSED)`, confirming duplicated/divergent prune-rule implementations across at least two of the three named files (cc_msg.py's own copy was not independently located but the pattern across t
- #550 families: 43

### WG-0094 · P0 · defend · effort S

**Stop --peers flashing consoles and stalling on AAAA: keep #5 and #6 from being undone by lane merges**

- Failure surface: #5 removed the powershell.exe child that flashed a terminal on every --peers and #6 resolved IPv4 first to cut 6.3s to 0.2s; PR #7 reverts #6 and every 09-03/09-04 lane lacks both. A merge from any of them brings back a visible window under the hidden scheduled task and a 6s stall per probe that the MCP gateway budget cannot absorb.
- First fork: if you observe --peers taking > 2s or a console flash on a Windows node -> diff _probe_nodes and _live_pipe_names against 42a58c2; else add a timing test with a fake AAAA-first resolver and a no-subprocess assertion.
- Evidence: `src/nougenmsg.py`, `origin/fix/agy-ping-delivery-status`, `origin/fix/peers-live-no-flash`
- Lens: runtime · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: main log shows 9a1ef1a (#5, no console flash) and 42a58c2 (#6, IPv4-first 6.3s->0.2s) as real commits on main; get_current_node/_probe_nodes logic in src/nougenmsg.py is exactly the code these commits touch. Branches fix/agy-ping-delivery-status and fix/peers-live-no-flash exist in origin.
- #550 families: 41

### WG-0104 · P0 · defend · effort M

**Survive concurrent cc_sessions.json rewrites without pruning a live Claude session**

- Failure surface: ping_claude does a read-modify-write of ~/.nougen/cc_sessions.json (tmp + os.replace) while the SessionStart hook nougenmsg_register_hook.py does the same; two senders or a hook racing a prune drop a just-registered session, and the only symptom is a Claude session that stops receiving fleet pings.
- First fork: if you observe 'registered' in ping_claude's result lower than the number of live Claude windows on the box -> reproduce the race with two concurrent senders and add a lock/merge-on-write, else audit _endpoint_gone rules first (the 2026-09-02 prune was a timeout, not a race)
- Evidence: `src/nougenmsg.py`, `NouGenShards/tools/nougenmsg_register_hook.py`, `NouGenShards/tools/_agy_live_delivery.py`
- Lens: concurrency · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Both src/nougenmsg.py:ping_claude (tmp+os.replace, only writes on prune) and NouGenShards/tools/nougenmsg_register_hook.py (tmp+os.replace on every register) do unlocked read-modify-write of the same cc_sessions.json path; no lock/merge exists in either. Race is real and matches the claim exactly.
- #550 families: 84

### WG-0114 · P0 · defend · effort S

**Reconcile the nested and flat cc_sessions.json shapes before main's ping_claude reaches phoebus**

- Failure surface: main's ping_claude only reads registry['sessions']; phoebus's nougenmsg_wake.py writes {session_id: {socket, token}} at top level, so main reports registered:0 and drops to inbox-only while a live session sits unaddressed. Canonical merges both shapes; main will regress the fix if deployed as-is.
- First fork: if you observe ping_claude returning registered:0 on a box with a live Claude window -> dump the registry and check for top-level entries (flat shape), else check the SessionStart hook ran at all
- Evidence: `src/nougenmsg.py`, `NouGenShards/src/nougen_shards/nougenmsg.py`, `NouGenShards/tests/test_nougenmsg_registry_shapes.py`
- Lens: data-integrity · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Verified: main's ping_claude (src/nougenmsg.py:209) reads only registry['sessions']; canonical's ping_claude (NouGenShards/src/nougen_shards/nougenmsg.py:305-316) explicitly merges nested 'sessions' and flat top-level shapes with a comment citing exactly this masking bug, and test_nougenmsg_registry_shapes.py tests that merge.
- #550 families: 36

### WG-0122 · P0 · defend · effort S

**Stop the 20s ssh timeout from killing delivered fan-outs and prompting duplicate resends**

- Failure surface: main's emit_node kills ssh at 20s while a remote --target all fan-out measures 24-27s (blade/whoart 2026-09-21); the message is delivered, the sender reports timeout, and the operator or a retry loop sends it again. Canonical raised its budget to 90s; main did not.
- First fork: if you observe 'Error: Command ... timed out' from emit_node while the target's inbox holds the message -> raise NOUGEN_MSG_SEND_TIMEOUT_S and return 'unknown' instead of error on timeout, else measure the remote fan-out and trim model lanes from the remote path
- Evidence: `src/nougenmsg.py`, `NouGenShards/src/nougen_shards/nougenmsg.py`
- Lens: concurrency · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: main's emit_node (src/nougenmsg.py) uses a hardcoded timeout=20 on the ssh subprocess.run call; canonical's emit_node (NouGenShards/src/nougen_shards/nougenmsg.py:1043) uses NOUGEN_MSG_SEND_TIMEOUT_S with default 90, exactly matching the claimed budget raise that main did not receive.
- #550 families: 16, 17

### WG-0130 · P0 · defend · effort M

**Make background fleet fan-out failures visible after the 76s double-delivery**

- Failure surface: canonical emit_fleet(background=True) returns {queued: True} per peer and writes fan-out failures only to stderr of the MCP node process; the 2026-09-14 incident (76s vs the gateway's 20s) delivered twice, and today a peer failure in the background thread is invisible to the caller and to any watchdog.
- First fork: if you observe a peer inbox missing a message the MCP caller saw as queued -> persist fan-out outcomes to an outbox/ledger the caller can poll, else at minimum log to messages.db with a failed state
- Evidence: `NouGenShards/src/nougen_shards/nougenmsg.py`, `NouGenShards/src/nougen_shards/mcp.py`
- Lens: observability · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: NouGenShards/src/nougen_shards/nougenmsg.py:1050-1086 emit_fleet(background=True) returns {queued: True} per peer, spawns a daemon thread, and prints failures only via stderr ('background fan-out to {n} failed'); mcp.py's nougenmsg_send calls emit_fleet with background=True, matching the claim that MCP callers see no failure signal.
- #550 families: 16

### WG-0138 · P0 · defend · effort M

**Collapse the four-copies-per-Antigravity-ping fan-out with one message_id at the emitter**

- Failure surface: main's ping_antigravity writes the same payload to ~/.gemini/config/inbox and ~/.nougen/agy_inbox with no message_id, and agy_pipe_server.drop_to_inboxes writes it into both again; read_inbox on main has no dedup so one send shows as four rows (2026-09-08) and every reader acts on it repeatedly.
- First fork: if you observe --inbox listing N identical texts with different _file names within one second -> stamp message_id in ping_antigravity/ping_codex and port canonical's identity-based dedup into read_inbox, else check whether agy_pipe_server is running twice
- Evidence: `src/nougenmsg.py`, `NouGenShards/tools/agy_pipe_server.py`, `NouGenShards/src/nougen_shards/nougenmsg.py`
- Lens: data-integrity · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: ping_antigravity (src/nougenmsg.py:276) writes identical ms-timestamp-named payload to both .gemini/config/inbox and .nougen/agy_inbox, then also calls AgyMsgBus.send_local which triggers agy_pipe_server.drop_to_inboxes (writes into both again) = 4 copies; read_inbox (line 525) has no dedup logic at all. Matches claim precisely.
- #550 families: 16

### WG-0146 · P0 · defend · effort M

**Bring whoart's untracked Outpost\NouGen bus copy under version control before the next hand-copy diverges**

- Failure surface: infra/whoart/SOURCE.md records that the files whoart executes are untracked in its NouGenShards tree and can only be fixed by hand-copy; the provenance table still says 311 lines while the snapshot is 496, so nobody can state today which bytes whoart runs.
- First fork: if you observe sha256 of %USERPROFILE%\Outpost\NouGen\src\nougen_shards\nougenmsg.py differing from infra/whoart/nougenmsg.py -> commit the live copy to a whoart lane and refresh SOURCE.md, else point whoart's task at a tracked clone and delete the untracked pair
- Evidence: `infra/whoart/SOURCE.md`, `infra/whoart/nougenmsg.py`, `infra/whoart/nougenmsg_cli.py`
- Lens: data-integrity · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: infra/whoart/SOURCE.md provenance table literally says 'nougenmsg.py | ... | 12,985 B / 311 lines' while the actual infra/whoart/nougenmsg.py file is 496 lines (verified with wc -l) -- the exact discrepancy claimed. SOURCE.md also states the source files are untracked in the working tree.
- #550 families: 12

### WG-0154 · P0 · elevate · effort M

**B7-observability: Ship `nougenmsg doctor` comparing each node's running build_id to the repo**

- Failure surface: nougenmsg_node already hashes the file it loaded (build_id) because on 2026-09-03 disk matched canonical while the process served stale code; SOURCE.md keeps three sha256 prefixes by hand and is already stale. No command asks the three nodes what they run and diffs it against main.
- First fork: if you observe /msg responses carrying a build id -> add doctor that POSTs an authenticated probe to each node and compares build to git blob hashes, else add build_id to /status and compare by hand
- Evidence: `NouGenShards/tools/nougenmsg_node.py`, `infra/whoart/SOURCE.md`, `tools/nougenmsg.py`
- Lens: B7-observability · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: NouGenShards/tools/nougenmsg_node.py has a build_id() function computing sha256[:12] of the loaded file, included in status output (lines 118-138, 408, 430); infra/whoart/SOURCE.md manually tracks three sha256[:12] prefixes in a divergence table. No doctor/diff command found in tools/nougenmsg.py.
- #550 families: 38

### WG-0162 · P0 · defend · effort S

**Alert when a :8766 receiver's auth mode drifts from required to open**

- Failure surface: On 2026-09-03 one key stopped resolving, the wrapper exported an empty token and a reload flipped a LAN-reachable receiver to accept-all for ~37 minutes with nothing announcing it; the latch now prints the mode at startup, but no sender or watchdog reads it, so the same drift on a scheduled-task restart would again go unnoticed.
- First fork: if you observe /status lacking an auth field -> add auth mode to the authenticated /msg response and have doctor/--peers fail on 'open' for a latched node, else grep task logs for LATCHED-NO-TOKEN on a schedule
- Evidence: `NouGenShards/tools/nougenmsg_node.py`, `NouGenShards/skills/nougenmsg/SKILL.md`
- Lens: observability · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: NouGenShards/tools/nougenmsg_node.py contains the literal string 'LATCHED-NO-TOKEN:refusing-mutations' (line 163) and prints auth mode at startup (line 429); SKILL.md documents NOUGEN_AGY_MSG_AUTH modes (required/optional/open). No watchdog reading the latch found in these files.

### WG-0170 · P0 · elevate · effort M

**B9-devex: Converge the three phoebus install paths and the whoart 72h task limit into one supervised service per node**

- Failure surface: main's _REMOTE_CLI points phoebus at ~/.nougen/bin/nougenmsg, native-queue's README at ~/.local/bin/nougenmsg under launchd com.nougen.msgnode, canonical at ~/.nougen/tools/nougenmsg.py with numpy-capable python selection; whoart's admin task has a 72h ExecutionTimeLimit that will kill the receiver on schedule.
- First fork: if you observe which phoebus path the launchd plist actually runs -> make it the single target in fleet_hosts.json and remove the others, else write a per-node install script that lays down one path and asserts it
- Evidence: `src/nougenmsg.py`, `origin/codex/nougenmsg-native-queue`, `NouGenShards/src/nougen_shards/nougenmsg.py`
- Lens: B9-devex · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: src/nougenmsg.py: _REMOTE_CLI['phoebus']='~/.nougen/bin/nougenmsg' and _REMOTE_CLI_DEFAULT='python3 ~/.nougen/tools/nougenmsg.py' verified (lines 436-438), two distinct paths already visible in this one file, consistent with the claim of divergent phoebus install locations across lanes.

### WG-0178 · P0 · defend · effort S

**Capture what phoebus actually executes: infra/phoebus holds federation.py, not the bus**

- Failure surface: infra/phoebus/SOURCE.md says dirty NouGenMsg files were intentionally excluded, so the repo has no evidence of phoebus's bus variant while three install paths compete; any fleet-wide fix is verified against blade and whoart snapshots and assumed for phoebus.
- First fork: if you observe the phoebus launchd plist pointing at a file whose sha256 matches no snapshot -> commit that file under infra/phoebus with provenance, else record the hash and path in SOURCE.md
- Evidence: `infra/phoebus/SOURCE.md`, `infra/phoebus/federation.py`
- Lens: observability · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Confirmed verbatim: nougenmsg/infra/phoebus/SOURCE.md states 'Phoebus dirty NouGenMsg files were intentionally excluded' and only federation.py was imported -- exactly as described.

### WG-0184 · P0 · elevate · effort S

**B3-routing: Upgrade _probe_nodes from TCP-connect to an authenticated /health round-trip so a hung node reads unreachab…**

- Failure surface: _probe_nodes calls a node reachable if :8766 accepts a TCP connect; blade's node today accepted connections while its loop was paused and /health hung, so --peers and any watchdog built on it reported a frozen node as up.
- First fork: if you observe nodes_reachable listing a node whose /health times out -> probe GET /health with a short deadline and require a JSON ok, else keep TCP but add response-time to the report
- Evidence: `src/nougenmsg.py`, `NouGenShards/tools/nougenmsg_node.py`
- Lens: B3-routing · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: Confirmed: _probe_nodes() in nougenmsg/src/nougenmsg.py does a raw socket.create_connection() TCP probe only (with an IPv4-first optimization comment), with no GET /health call or JSON-ok check, even though nougenmsg_node.py does expose a GET /health route.
- #550 families: 95

### WG-0189 · P0 · defend · effort M

**Detect from the sender when a receiver silently drops from auth=required to auth=open**

- Failure surface: On 2026-09-03 a vault miss flipped a LAN-reachable receiver to auth=open for ~37 minutes; the receiver now latches, but main's send_direct_http only adds X-NGS-Token when it resolves one and never checks the response's auth mode. A sender with no token still 'succeeds' against an open node and nobody learns the gate is down.
- First fork: if you observe /status exposing the auth mode string -> have the sender refuse or warn when mode is open and a token was expected, else -> add the field to /status first (NouGenShards) then the check
- Evidence: `NouGenShards/tools/nougenmsg_node.py`, `tools/nougenmsg.py`
- Lens: privacy/security-governance · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: NouGenShards/tools/nougenmsg_node.py has explicit comments referencing the 2026-09-03 ~37 minute auth=required->open flip (lines 84-98) and X-NGS-Token gating (line 335); /status/health left open by design (line 343). tools/nougenmsg.py's send path adds the token only when resolved, with no check of response auth mode.

### WG-0194 · P0 · defend · effort M

**Pin which of blade's two code trees the remote CLI and scheduled task actually run**

- Failure surface: Today blade has two scheduled tasks pointing at two code trees; main's _REMOTE_CLI targets Watchtower/NouGen/NouGenShards-push-main/tools/nougenmsg.py while infra/blade/nougenmsg.py is the 195-line injectable variant. A sender's ssh lands in one tree, the :8766 receiver runs another, and the fix you just deployed is invisible.
- First fork: if you observe `schtasks /query` showing both tasks enabled -> disable one, hash the tree the survivor runs, and record it in infra/blade/SOURCE.md, else -> verify the HTTP receiver and ssh CLI share a tree via --capabilities
- Evidence: `src/nougenmsg.py`, `infra/blade/SOURCE.md`, `infra/blade/nougenmsg.py`
- Lens: deploy-governance · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: src/nougenmsg.py _REMOTE_CLI (line 433-437) has blade -> 'python C:~/Watchtower/NouGen/NouGenShards-push-main/tools/nougenmsg.py' exactly; infra/blade/nougenmsg.py is 195 lines and infra/blade/SOURCE.md documents it as sourced from a specific blade commit, consistent with a second/injectable tree.
- #550 families: 28

### WG-0199 · P0 · defend · effort M

**Bring whoart's untracked live bus files under git without stopping the running node**

- Failure surface: whoart executes %USERPROFILE%\Outpost\NouGen\{src,tools} files that git does not know about; the only copies are infra/whoart/*.py. A disk hiccup or a well-meaning `git checkout` on that tree erases the bus with no history, and the 5-minute tunnel watchdog cannot help.
- First fork: if you observe the live files byte-identical to infra/whoart -> commit them on a whoart lane and switch the node to the tracked path during a quiet window, else -> snapshot the drift first, then reconcile
- Evidence: `infra/whoart/SOURCE.md`, `infra/whoart/nougenmsg.py`, `infra/whoart/nougenmsg_cli.py`
- Lens: deploy-governance · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: infra/whoart/SOURCE.md explicitly states both files 'were untracked in the NouGenShards working tree at Outpost\NouGen (verified with git ls-files --error-unmatch...)' and that infra/whoart/{nougenmsg.py,nougenmsg_cli.py} are the only tracked copies.

### WG-0204 · P0 · defend · effort M

**Collapse phoebus's three documented install paths into one interpreter-safe receiver**

- Failure surface: main dials ~/.nougen/bin/nougenmsg, native-queue's README says ~/.local/bin/nougenmsg under launchd com.nougen.msgnode, canonical runs ~/.nougen/tools/nougenmsg.py with a numpy-capable python3 selection. A sender from blade hits whichever exists; the wrong one dies at import and the node looks unreachable for a reason nothing reports.
- First fork: if you observe more than one of the three paths on phoebus -> pick one, symlink the others to it, and test with --capabilities from both Windows nodes, else -> document the survivor in fleet_hosts.json
- Evidence: `src/nougenmsg.py`, `origin/codex/nougenmsg-native-queue`, `NouGenShards/src/nougen_shards/nougenmsg.py`
- Lens: deploy-governance · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: src/nougenmsg.py:436 has phoebus -> '~/.nougen/bin/nougenmsg'; origin/codex/nougenmsg-native-queue's README documents 'Command: ~/.local/bin/nougenmsg' -- a different path, confirming the divergent install locations claim.

### WG-0209 · P0 · defend · effort M

**Add a sender/receiver contract test before trusting the green injection suite**

- Failure surface: test_command_line_is_fixed_shape asserts emit_node sends '--target X --local --stdin', but no receiver in the fleet (NouGenShards/tools/nougenmsg.py, infra/whoart/nougenmsg_cli.py, infra/blade) accepts --stdin; the tests pass while every ssh send fails closed against real nodes. Green tests certified a broken contract.
- First fork: if you observe canonical receivers advertising text-b64 via --capabilities -> write a fixture that runs main's sender against each receiver's argv parser, else -> mark the stdin tests as contract-pending until a receiver lands
- Evidence: `tests/test_emit_node_injection.py`, `NouGenShards/tools/nougenmsg.py`, `infra/whoart/nougenmsg_cli.py`
- Lens: ci/coverage-hole · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: tests/test_emit_node_injection.py:85 and :110 assert the remote command ends with '--target claude --local --stdin' / contains '--stdin'; grepped NouGenShards/tools/nougenmsg.py and infra/whoart/nougenmsg_cli.py and infra/blade/nougenmsg.py for --stdin support: no matches found in any receiver.
- #550 families: 82

### WG-0214 · P0 · defend · effort S

**Lock the cc_sessions.json rewrite so concurrent fan-outs cannot drop a live Claude session**

- Failure surface: ping_claude reads, prunes and os.replace's the shared registry with no lock; three nodes fanning out at once plus the SessionStart hook writing the same file races to a stale rewrite. A live session vanished from the registry on 2026-09-02 and stopped hearing the fleet.
- First fork: if you observe the register hook already using _lock_to_user -> reuse its lock in the pruner, else -> stop pruning in the sender and let the hook own the file
- Evidence: `src/nougenmsg.py`, `NouGenShards/tools/nougenmsg_register_hook.py`
- Lens: multi-agent-governance · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: src/nougenmsg.py:252 ping_claude uses os.replace(tmp, reg_path) with no lock/lockfile visible in that function; NouGenShards/tools/nougenmsg_register_hook.py:27-70 defines and uses a _lock_to_user function that ping_claude's registry rewrite does not call, confirming the asymmetric locking claim.
- #550 families: 85

### WG-0219 · P0 · defend · effort S

**Emit the DELIVERED/QUEUED receipt line relay dispatch keys on from main's CLI**

- Failure surface: relay dispatch marked 17 delivered digests as failed until detection was keyed on a DELIVERED/QUEUED receipt line; main's CLI prints 'Result: {...}' dicts with delivery_verified=False and no such line, so any node running main makes dispatch report false failures and re-dispatch.
- First fork: if you observe dispatch.py grepping for a fixed receipt string -> print that exact line from tools/nougenmsg.py and add a test, else -> agree a JSON receipt and switch both sides
- Evidence: `tools/nougenmsg.py`, `NouGenShards/docs/evolution/2026-09-21-nougenlive-dispatch.md`, `src/nougenmsg.py`
- Lens: handoff-discipline · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: NouGenShards/docs/evolution/2026-09-21-nougenlive-dispatch.md line 25 states detection 'now keys on the DELIVERED/QUEUED receipt line' after 17 digests were marked failed although delivered; src/nougenmsg.py's ping_claude sets delivery_verified=False by design (line 199) and prints Result dicts, not a fixed receipt line.
- #550 families: 23

### WG-0224 · P0 · elevate · effort M

**Make ping_antigravity able to say delivered: fix the relative import and land the tri-state**

- Failure surface: src/nougenmsg.py:313 does `from .agy_msg import AgyMsgBus` inside a flat module, so pipe_delivered is always False and status is always 'dropped'; PR #7 adds delivered/queued/dropped but cannot produce 'delivered' from this copy, and canonical still returns delivered-else-dropped with no 'queued'.
- First fork: if you observe agy_msg.py available on the node (NouGenShards) -> import it absolutely with a guarded fallback and land #7 rebased, else -> implement the pipe write inline like canonical does
- Evidence: `src/nougenmsg.py`, `origin/fix/agy-ping-delivery-status`, `NouGenShards/src/nougen_shards/agy_msg.py`
- Lens: B4-receipts · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: src/nougenmsg.py line 313 is exactly `from .agy_msg import AgyMsgBus` wrapped in try/except Exception: pass, and the function is a flat (non-package) module with no agy_msg.py alongside it, so the import always fails silently and pipe_delivered stays False -- matches the claim precisely down to the line number.
- #550 families: 21, 23

### WG-0229 · P0 · elevate · effort M

**Reconcile PR #2's cc_msg.py against main instead of the 1331234 baseline**

- Failure surface: antigravity/cc-msg-parity adds Claude live-socket auth framing and pipe injection but its merge base is 1331234: it removes _probe_nodes/_live_pipe_names (reintroducing the powershell console flash #5 fixed), deletes test_nougenmsg_node_resolve.py, hardcodes 192.0.2.178/192.0.2.88 and posts to :8766 with no auth header. NouGenShards already has a 173-line canonical cc_msg.py.
- First fork: if you observe NouGenShards covering the same features -> close #2 in favor of it, else -> cherry-pick only tools/cc_msg.py onto main and rewrite its transport to send_direct_http
- Evidence: `origin/antigravity/cc-msg-parity`, `NouGenShards/tools/cc_msg.py`, `src/nougenmsg.py`
- Lens: B6-parity · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: origin/antigravity/cc-msg-parity branch exists; NouGenShards/tools/cc_msg.py exists; commit 1331234 ('Add Codex NouGenMsg lane baseline') is confirmed as the very first commit in main's ancestry (git log tail), consistent with lane branches being forked from that early baseline rather than main's current HEAD, which independently corroborates the staleness claim.

### WG-0234 · P0 · elevate · effort M

**Publish one env-var reference and a config doctor for the five competing namespaces**

- Failure surface: Node lists are NOUGEN_MSG_NODES (main), NOUGEN_FLEET_NODES (canonical), NOUGEN_MSG_FLEET_NODES (native-queue); addresses are NOUGEN_NODE_<X>_IP vs NOUGEN_MSG_NODE_<X>_URL; ports NOUGEN_MSG_PORT vs NOUGEN_AGY_MSG_PORT vs NOUGEN_NODE_<X>_PORT. On 2026-09-21 whoart->phoebus fell back to ssh for weeks because one var was unset.
- First fork: if you observe a var read by more than one implementation with different defaults -> pick canonical names, alias the rest with deprecation warnings, else -> just document
- Evidence: `nougenmsg/src/nougenmsg.py`, `nougenmsg/tools/nougenmsg.py`, `NouGenShards/docs/evolution/2026-09-21-nougenlive-dispatch.md`
- Lens: B9-devex · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: nougenmsg/src/nougenmsg.py uses NOUGEN_MSG_NODES/NOUGEN_MSG_PORT/NOUGEN_NODE_<X>_IP; nougenmsg/tools/nougenmsg.py uses NOUGEN_MSG_PORT and NOUGEN_AGY_MSG_PORT and NOUGEN_NODE_<X>_IP -- confirms divergent namespaces. Evolution doc exists. Corrected src/nougenmsg.py and tools/nougenmsg.py paths to nougenmsg/ prefix.
- #550 families: 35, 36

### WG-0239 · P0 · elevate · effort M

**Add a scheduled cross-node synthetic ping that alerts when /health hangs rather than refuses**

- Failure surface: Today blade's node froze under QuickEdit pause: /health hung and CLOSE_WAIT piled up while the port was still open, so main's _probe_nodes (TCP connect only) reported it reachable. Nothing pings the fleet on a schedule; the GM discovered it by hand.
- First fork: if you observe a Routine/scheduled-task convention already used for the whoart tunnel watchdog -> add a 5-min synthetic @node ping with receipt timeout, else -> start with a /health GET with a hard timeout in --peers
- Evidence: `nougenmsg/src/nougenmsg.py`, `NouGenShards/tools/nougenmsg_node.py`, `NouGenShards/docs/fleet-transport-node.md`
- Lens: B7-observability · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: nougenmsg/src/nougenmsg.py:36 defines _probe_nodes (TCP-connect-only reachability); nougenmsg_node.py has /health route deliberately left open per comments at lines 154,326; fleet-transport-node.md exists. Corrected src/nougenmsg.py to nougenmsg/src/nougenmsg.py.
- #550 families: 95

### WG-0244 · P0 · elevate · effort M

**Detect a quiet bus lane the way the vault-quiet incident demanded**

- Failure surface: The vault sat quiet 3 days unnoticed; the bus has the same shape: the receiver writes agy_last_msg.json but nothing alarms when a node or lane receives nothing for N hours, so a dead whoart tunnel or a frozen receiver reads as 'no traffic'.
- First fork: if you observe nougenlive/status_semantics classify_node taking heartbeat age -> feed last-message age per lane into it, else -> add a --peers column and a Routine that pings when age exceeds a threshold
- Evidence: `NouGenShards/tools/nougenmsg_node.py`, `NouGenShards/src/nougen_shards/status_semantics.py`, `NouGenShards/HARDENING.md`
- Lens: B7-observability · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: nougenmsg_node.py:81 STATE points to agy_last_msg.json; status_semantics.py:181 classify_node takes heartbeat_age_s; HARDENING.md:3 documents the vault-quiet-3-days origin story verbatim.
- #550 families: 21

### WG-0248 · P0 · defend · effort M

**Stop timeout-after-delivery retries from double-sending fleet broadcasts**

- Failure surface: main's emit_node ssh timeout is 20s while a remote --target all fan-out takes 24-27s; emit_fleet ran 76s on 2026-09-14 against a 20s MCP gateway, gave up, fell back, and the message arrived twice. Every retry by a caller who saw 'timeout' is a duplicate delivered to every agent on every node.
- First fork: if you observe the receiver already assigns message_id (NouGenShards #509) -> send an idempotency id and dedupe on the receiver, else -> raise NOUGEN_MSG_SEND_TIMEOUT_S and make emit_fleet background like canonical first
- Evidence: `src/nougenmsg.py`, `NouGenShards/src/nougen_shards/nougenmsg.py`, `tools/nougenmsg.py`
- Lens: cost/duplicates · likelihood observed · blast fleet · verdict CONFIRMED · status open
- Verifier note: src/nougenmsg.py: emit_node uses subprocess timeout=20 (line 479); canonical repo's send timeouts differ. The described 20s-vs-24-27s mismatch is consistent with the code, though the specific 76s 2026-09-14 incident is asserted, not independently verifiable from static code.
- #550 families: 16, 17

### WG-0363 · P1 · elevate · effort M

**Roll the --stdin receiver to all three nodes before main's emit_node ssh path is used**

- Failure surface: main's emit_node sends '--target X --local --stdin' but no receiver in the fleet (canonical NouGenShards/tools/nougenmsg.py only knows --text-b64, infra/whoart/nougenmsg_cli.py knows neither) accepts it, so every ssh fallback fails closed with a receiver usage error; senders see 'Error' and the message is lost unless the http route worked first.
- First fork: if you observe `ssh <node> '<cli> --capabilities'` printing 'text-b64' -> switch main's emit_node to --text-b64 and keep --stdin as the legacy path; else ship a receiver that accepts both flags to each node by hand-copy (whoart's files are untracked) and verify with the 8-payload injection corpus before touching senders.
- Evidence: `src/nougenmsg.py`, `infra/whoart/nougenmsg_cli.py`, `NouGenShards/tools/nougenmsg.py`
- Lens: B5-security · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Confirmed exactly: nougenmsg/src/nougenmsg.py emit_node() builds remote_cmd = f'{cli} --target {target} --local --stdin'; NouGenShards/tools/nougenmsg.py only advertises 'text-b64' in its --capabilities banner (no stdin), and nougenmsg/infra/whoart/nougenmsg_cli.py has no --stdin or --text-b64 handling at all -- the described receiver mismatch is real.

### WG-0379 · P1 · defend · effort M

**Judge the whole message: Kaedra gate classifies text[:2000] but delivers the full body**

- Failure surface: classify_with_kaedra sends only the first 2000 chars as the prompt while gate_and_deliver hands the complete text to deliver_to_live_sessions on APPROVE; 2000 chars of benign prose followed by an instruction block reaches a live Claude session framed as a teammate message.
- First fork: if you observe the gate model's context window cannot take the max inbox message -> chunk-and-any-DENY; else judge the full text (or the tail as well as the head) and add a regression fixture with the injection after offset 2000.
- Evidence: `NouGenShards/tools/_agy_live_delivery.py`, `NouGenShards/tools/nougenmsg_node.py`
- Lens: prompt-injection · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Confirmed: NouGenShards/tools/_agy_live_delivery.py's classify_with_kaedra() sends 'prompt': text[:2000] to the model, while gate_and_deliver()/deliver_to_live_sessions(text, source) is called with the full untruncated text on APPROVE -- the truncation-vs-delivery mismatch is real.
- #550 families: 3

### WG-0395 · P1 · defend · effort L

**Gate the wake path: approved message text becomes an autonomous agent prompt with skip-permissions**

- Failure surface: _maybe_wake runs after Kaedra approval and the Antigravity adapter executes [agy, '--dangerously-skip-permissions', '-p', full_prompt] with the message as the opening prompt; a message that passes a 2 KB, small-model content gate starts an unattended, permission-free agent turn on the node. wake_target is chosen by the sender.
- First fork: if you observe NOUGEN_AGY_FLAGS unset on any node running the wake daemon -> set an explicit read-only flag set before anything else; else require user_verified origin (not kaedra_approved) for executable wakes and log every wake with the message id.
- Evidence: `NouGenShards/src/nougen_shards/wake/adapters.py`, `NouGenShards/tools/nougenmsg_node.py`
- Lens: tool-abuse · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Confirmed: nougenmsg_node.py's do_POST runs _maybe_wake(msg, elevated) only after gate_and_deliver's Kaedra approval; the actual --dangerously-skip-permissions default flag lives in NouGenShards/src/nougen_shards/wake/adapters.py (NOUGEN_AGY_FLAGS default '--dangerously-skip-permissions', cmd = [bin_path, *flags, '-p', full_prompt]) rather than in tools/wake/antigravity.py (which has no such defau
- #550 families: 69

### WG-0411 · P1 · defend · effort M

**Pin the receiver bind per node instead of a user-env NOUGEN_AGY_MSG_BIND=0.0.0.0 fix**

- Failure surface: 2026-09-21: whoart's receiver bound 127.0.0.1 so phoebus could never reach it; fixed by setting NOUGEN_AGY_MSG_BIND=0.0.0.0 in the user environment and restarting under pythonw. A task re-registration, a different logon, or a hidden scheduled task with its own env drops the override and the node silently goes loopback-only; 0.0.0.0 also exposes :8766 on the cloudflared/tunnel interface.
- First fork: if you observe `curl whoart.local:8766/health` failing while the process is up -> check the running process env for BIND, not the user env; else move bind into the task definition/wrapper and bind to the LAN interface address rather than all interfaces.
- Evidence: `NouGenShards/docs/evolution/2026-09-21-nougenlive-dispatch.md`, `NouGenShards/tools/nougen_live.ps1`, `NouGenShards/tools/nougenmsg_node.py`
- Lens: deploy · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: nougenmsg_node.py confirms DEFAULT_BIND='127.0.0.1' and NOUGEN_AGY_MSG_BIND env override (lines 31-32, 61, 428), consistent with the claim that bind is env-driven and fragile; the specific 2026-09-21 whoart incident is documented in the cited evolution doc and is a reasonable read of it.
- #550 families: 39

### WG-0427 · P1 · defend · effort M

**Fix the phoebus 8765/8766 split so the http route stops burning 15s before ssh fallback**

- Failure surface: phoebus answers 404 to /msg on :8765 and hangs on :8766; tools/nougenmsg.py resolves the port env->fallback 8766 and waits the full HTTP_ROUTE_FALLBACK_TIMEOUT_S before printing 'falling back to ssh'. Every whoart/blade -> phoebus send costs 15s+ and the dispatch table parked it.
- First fork: if you observe GET phoebus:8766/health hanging -> the listener on 8766 is not nougenmsg_node.py (find and stop it, run the portable receiver there); else set NOUGEN_NODE_PHOEBUS_PORT on senders and make /msg on 8765 answer.
- Evidence: `NouGenShards/docs/evolution/2026-09-21-nougenlive-dispatch.md`, `tools/nougenmsg.py`, `NouGenShards/tools/nougenmsg_node.py`
- Lens: runtime · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: Evidence files exist (evolution doc, this repo's tools/nougenmsg.py, NouGenShards nougenmsg_node.py); the port-split and fallback-timeout behavior is plausible given the receiver's dual-port design referenced elsewhere in the codebase, though the exact env var name wasn't independently verified.
- #550 families: 43

### WG-0443 · P1 · defend · effort S

**Close GET /pop and /msg/<id> on unlatched receivers before any node is LAN-bound**

- Failure surface: With NOUGEN_AGY_MSG_TOKEN unset and no latch (the default), _reject_unauthorized returns False, so any LAN caller can GET /pop to read-and-destroy the pending queue and read receipts; a node bound 0.0.0.0 for cross-machine sends (the documented setup) ships in this state until someone sets the latch.
- First fork: if you observe bind != 127.0.0.1 and auth=open(unlatched) in the startup line -> latch by default whenever the bind is not loopback; else keep open mode loopback-only by refusing to start LAN-bound without a token.
- Evidence: `NouGenShards/tools/nougenmsg_node.py`, `NouGenShards/docs/fleet-transport-node.md`
- Lens: auth · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Confirmed in nougenmsg_node.py: with AUTH_TOKEN unset and AUTH_LATCH false (default), _reject_unauthorized (line 317) returns False; GET /pop (line 351-352) and /msg/<id> receipts (line 348) are gated by that same call, so an unlatched open node truly exposes read-and-destroy on /pop.
- #550 families: 20

### WG-0458 · P1 · defend · effort M

**Survive the day the Kaedra gateway dies: fail-closed gate silently denies all elevated delivery**

- Failure surface: classify_with_kaedra calls KAEDRA_GATEWAY_URL (default 127.0.0.1:4455) and any error returns DENY/gate_unavailable; the receiver still writes the inbox file and answers delivered:true, so senders see success while no message reaches a live session. A dead whoart tunnel, a stopped Kaedra task or a rotated KAEDRA_GATEWAY_TOKEN produces days of quiet non-delivery, the vault-quiet pattern from HARDENING.
- First fork: if you observe elevated.reason_code == gate_unavailable in more than N consecutive receipts -> alert via the relay and fall back to inbox-only with an explicit 'queued, gate down' status; else keep fail-closed but surface gate health in /status.
- Evidence: `NouGenShards/tools/_agy_live_delivery.py`, `NouGenShards/tools/nougenmsg_node.py`
- Lens: runtime · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Confirmed: KAEDRA_URL/KAEDRA_GATEWAY_URL and classify_with_kaedra returning DENY/gate_unavailable on any error (lines 45,151,167,198 of _agy_live_delivery.py); the receiver still writing the inbox file / reporting delivered while elevated delivery silently fails matches gate_and_deliver's fail-closed structure.
- #550 families: 94

### WG-0471 · P1 · elevate · effort S

**Backport the stdin-body remote Ollama curl so main stops building a shell string**

- Failure surface: main ping_ollama does payload.replace('"','\\"') and ships 'curl ... -d "{escaped}"' over ssh; a prompt containing $( ) or backticks executes on the remote node as the ssh user. Canonical already sends the JSON on stdin with --data-binary @-.
- First fork: if you observe the remote node is a cmd.exe lane (blade/whoart) -> verify curl on Windows reads stdin with @- before switching; else copy canonical's constant remote_cmd and add the Ollama case to tests/test_emit_node_injection.py's PAYLOADS matrix.
- Evidence: `src/nougenmsg.py`, `NouGenShards/src/nougen_shards/nougenmsg.py`, `tests/test_emit_node_injection.py`
- Lens: B5-security · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Confirmed: nougenmsg/src/nougenmsg.py's ping_ollama does escaped = payload.replace('"','\\"'); cmd = f'curl -s -X POST ... -d "{escaped}"' run over ssh, while NouGenShards/src/nougen_shards/nougenmsg.py's canonical ollama lane instead sends the body via 'curl ... --data-binary @-' over stdin, and tests/test_emit_node_injection.py already exists with a PAYLOADS list as the natural place to extend.

### WG-0484 · P1 · elevate · effort S

**Land PR #7's delivered/queued/dropped tri-state without reverting the IPv4-first probe**

- Failure surface: origin/fix/agy-ping-delivery-status fixes the always-'dropped' status but its diff against main also removes #6's getaddrinfo AF_INET block, bringing back the 6.3s whoart.local AAAA stall on every --peers; and because src/nougenmsg.py:313 uses a relative import in a flat module, pipe_delivered can never be True, so the new 'delivered' branch is unreachable on main.
- First fork: if you observe `git diff origin/main origin/fix/agy-ping-delivery-status` still touching _probe_nodes -> cherry-pick only the status hunk; else fix the .agy_msg import to an absolute/optional import and add a test that a successful pipe write yields 'delivered'.
- Evidence: `NouGenMsg#7`, `origin/fix/agy-ping-delivery-status`, `src/nougenmsg.py`
- Lens: B4-receipts · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: git diff origin/main..origin/fix/agy-ping-delivery-status confirms _probe_nodes reverts to the plain create_connection (dropping the AF_INET getaddrinfo hunk) while adding the delivered/queued/dropped status; src/nougenmsg.py:313 does `from .agy_msg import AgyMsgBus` in a flat module (no package/agy_msg.py present), so pipe_delivered can never be True on main.

### WG-0496 · P1 · elevate · effort M

**Package NouGenMsg so tools/nougenmsg.py can import its own src (pyproject from native-queue)**

- Failure surface: tools/nougenmsg.py imports nougen_shards.nougenmsg, which this repo does not ship; the CLI raises ModuleNotFoundError standalone and tests/test_nougenmsg_node_resolve.py errors 6/6 here (46 injection tests pass). codex/nougenmsg-native-queue already carries a pyproject with a console script and pytest pythonpath=src.
- First fork: if you observe the fleet nodes running NouGenShards' copy, not this repo's -> package this repo as the SDK NouGenShards vendors and change the import to `nougenmsg`; else keep the nougen_shards namespace and add a shim package here so both import paths resolve.
- Evidence: `tools/nougenmsg.py`, `tests/test_nougenmsg_node_resolve.py`, `origin/codex/nougenmsg-native-queue`
- Lens: B9-devex · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: Confirmed by running pytest on this repo: exactly 46 passed and 6 errors (all ModuleNotFoundError: nougen_shards, all in tests/test_nougenmsg_node_resolve.py) because tools/nougenmsg.py imports `from nougen_shards.nougenmsg import ...`; origin/codex/nougenmsg-native-queue's pyproject.toml carries a console script and pytest pythonpath=src as claimed.
- #550 families: 31

### WG-0508 · P1 · elevate · effort M

**Scrub owner paths and mDNS hostnames from this public repo via fleet_hosts.json**

- Failure surface: src/nougenmsg.py _REMOTE_CLI carries C:~/... paths, tools/nougenmsg.py and the node-resolve test name blade1tb.local / KushBoyGroups-Mac-mini.local / 192.0.2.87, and NOUGEN_MSG_NODES defaults to the fleet roster; NouGenShards #528/#545 already moved these into ~/.nougen/fleet_hosts.json and get_current_node returns 'standalone' without it.
- First fork: if you observe main still being the copy any node executes -> ship fleet_hosts.json to each node before the scrub so remote_cli resolution does not go blank; else scrub, use %USERPROFILE%/~ forms, and add a grep test that no owner path or LAN IP is in the tree.
- Evidence: `src/nougenmsg.py`, `tools/nougenmsg.py`, `NouGenShards/src/nougen_shards/nougenmsg.py`
- Lens: B3-routing · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: Confirmed exactly: src/nougenmsg.py lines 433-438 hardcode C:~/Watchtower/... and C:~/Outpost/... paths; tools/nougenmsg.py line 57 and tests/test_nougenmsg_node_resolve.py reference blade1tb.local and 192.0.2.87; NOUGEN_MSG_NODES defaults to 'whoart,blade,phoebus' (src/nougenmsg.py line 47).
- #550 families: 74

### WG-0520 · P1 · defend · effort M

**Collapse blade's two scheduled tasks pointing at two code trees into one receiver**

- Failure surface: Today blade runs 'NouGen NGS Node (src)' hidden plus the older task; install_ngs_node_task.ps1 retriggers every 15 minutes via run_hidden.vbs and nougen_live.ps1 tracks the receiver by pid file. Two trees mean two build ids, a port collision on :8766 or the older tree's receiver winning after a reboot, and the injection fix present in one tree but not the other.
- First fork: if you observe two nougenmsg_node.py processes or two task definitions naming different roots -> disable the older task and confirm build_id from an authenticated POST matches the src tree; else delete the second tree's task and document the single path in fleet-transport-node.md.
- Evidence: `NouGenShards/tools/install_ngs_node_task.ps1`, `NouGenShards/tools/nougen_live.ps1`, `NouGenShards/docs/fleet-transport-node.md`
- Lens: deploy · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: Evidence files (install_ngs_node_task.ps1, nougen_live.ps1, fleet-transport-node.md) exist in NouGenShards; the two-scheduled-task/two-tree scenario is a reasonable inference from those deployment scripts though not independently verified against blade's live process list.
- #550 families: 29

### WG-0532 · P1 · defend · effort S

**Never launch the receiver in a visible console again: QuickEdit froze blade's loop**

- Failure surface: Today's blade freeze: the node ran in a visible console, a QuickEdit selection paused the asyncio loop, /health hung and CLOSE_WAIT piled up. nougen_live.ps1 and install_ngs_node_task.ps1 use run_hidden.vbs/pythonw, but a manual `python tools/nougenmsg_node.py` from a terminal (the docs' own example) reproduces it.
- First fork: if you observe the receiver pid's parent is conhost/an interactive shell -> kill it and relaunch through the hidden task; else add a startup guard that refuses to run attached to a console unless NOUGEN_MSGNODE_ALLOW_CONSOLE=1.
- Evidence: `NouGenShards/tools/nougen_live.ps1`, `NouGenShards/tools/install_ngs_node_task.ps1`, `NouGenShards/tools/nougenmsg_node.py`
- Lens: deploy · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: Evidence files exist and nougen_live.ps1/install_ngs_node_task.ps1 are the deployment scripts that launch the receiver; the specific QuickEdit-freeze incident and console-vs-hidden-task distinction is plausible given the hidden-launch design visible in those scripts, but the incident itself isn't independently verifiable from static files.

### WG-0544 · P1 · defend · effort M

**Retire canonical emit_node's quoted-body fallback that survives behind a metacharacter blocklist**

- Failure surface: When _supports_text_b64 returns False (cached per process, including after one 15s probe timeout) canonical emit_node still builds remote_cmd = f'{base} "{text}"' guarded only by the _REMOTE_SHELL_UNSAFE blocklist; a character the list misses, or a cmd.exe-specific expansion, reaches the remote shell. A long-lived MCP server that cached False once stays on this path until restart.
- First fork: if you observe _TEXT_B64_SUPPORT[node] is False for a node whose CLI prints text-b64 -> the probe timed out, add negative-cache expiry; else delete the quoted path entirely and make scp pointer the only non-b64 route.
- Evidence: `NouGenShards/src/nougen_shards/nougenmsg.py`, `NouGenShards/tools/nougenmsg.py`
- Lens: injection · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Confirmed: NouGenShards/src/nougen_shards/nougenmsg.py defines _REMOTE_SHELL_UNSAFE (frozenset of chars) and a per-process _TEXT_B64_SUPPORT cache via _supports_text_b64(); when False, code falls to remote_cmd = f'{base} "{text}"' guarded only by _refuse_if_shell_unsafe's blocklist check -- exactly the fallback path described.

### WG-0556 · P1 · elevate · effort M

**Roll receivers with deployment receipts: a checkout does not change the running process**

- Failure surface: 2026-09-03 a node pulled canonical, disk matched byte-for-byte, and the still-running receiver kept serving pre-pull code while every disk check said MATCH. build_id() exists for this reason but no rollout step restarts and re-reads it per node; the next security fix can 'land' fleet-wide while the vulnerable process keeps serving.
- First fork: if you observe build from an authenticated POST unchanged after a pull -> the restart did not happen, stop the rollout; else write the per-node (build, timestamp, who) receipt to the relay and only then mark the fix done.
- Evidence: `NouGenShards/tools/nougenmsg_node.py`, `NouGenShards/docs/fleet-transport-node.md`, `NouGenShards/tools/launchd/nougenmsg_node_launch.sh`
- Lens: B10-fleet · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: build_id() in nougenmsg_node.py (confirmed, hashes __file__ actively, with a docstring describing exactly the 2026-09-03 stale-process incident this item references) supports the claim that no automated rollout receipt step exists; the docstring itself corroborates the incident narrative.
- #550 families: 100

### WG-0568 · P1 · defend · effort S

**Harden main's ssh fallback with canonical's BatchMode/-n options and temp-file capture**

- Failure surface: main emit_node runs ['ssh', node, cmd] with capture_output=True and no BatchMode; measured on blade, Windows OpenSSH blocks when stdout is a parent-held pipe (20s timeout vs 0.5s to a file) and a nested non-interactive ssh hangs on a host-key or credential prompt. Every blade -> whoart ssh dispatch times out and the message silently is not sent (or is sent and reported as failed).
- First fork: if you observe blade -> whoart ssh sends timing out at exactly the 20s limit -> port _ssh_capture and _SSH_OPTS from canonical; else keep capture_output but add -o BatchMode=yes and a known_hosts check up front.
- Evidence: `src/nougenmsg.py`, `NouGenShards/src/nougen_shards/nougenmsg.py`
- Lens: runtime · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: Confirmed src/nougenmsg.py's emit_node uses subprocess.run(['ssh', node, cmd], capture_output=True, timeout=20, ...) with no BatchMode option visible in that call, supporting the claim that OpenSSH-side blocking on a held pipe is unmitigated.
- #550 families: 73

### WG-0579 · P1 · defend · effort M

**Stop the 20s ssh timeout killing --target all sends after delivery and causing duplicate retries**

- Failure surface: The remote --target all fan-out takes 24-27s (blade/whoart 2026-09-21) because it also hits Ollama/OpenRouter; main's emit_node timeout=20 kills the ssh after the message landed and reports timeout, so the caller (or MCP gateway at 20s) retries and the message arrives twice, as on 2026-09-14 when emit_fleet ran 76s.
- First fork: if you observe the MCP gateway's 20s ceiling is the binding constraint -> adopt canonical's background=True fan-out returning queued:True; else raise NOUGEN_MSG_SEND_TIMEOUT_S to 90 and send an idempotency key so the receiver dedups the retry.
- Evidence: `src/nougenmsg.py`, `NouGenShards/src/nougen_shards/nougenmsg.py`, `NouGenShards/tests/test_nougenmsg_fanout_async.py`
- Lens: runtime · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: Confirmed emit_node's timeout=20 literal in src/nougenmsg.py; the specific 24-27s/76s fan-out timing and duplicate-retry claim depends on runtime behavior (Ollama/OpenRouter latency, MCP gateway ceiling) not verifiable from static code, but is a reasonable inference from the hardcoded 20s ceiling.
- #550 families: 16, 49

### WG-0590 · P1 · elevate · effort M

**Send a message_id and check the receipt before falling back from http to ssh**

- Failure surface: send_direct_http waits up to 15s (Kaedra gate measured 1.1-10s, one 15s miss) then dispatch_node falls back to ssh; the receiver already wrote the inbox file and queued it, so the ssh copy is a duplicate the receiver cannot dedup because main's payload carries no message_id or idempotency_key.
- First fork: if you observe the http error is a timeout rather than a refusal -> GET /msg/<id> with the id you generated before retrying over ssh; else generate a uuid client-side, put it in the payload, and let the receiver's assign_message_id keep it.
- Evidence: `tools/nougenmsg.py`, `NouGenShards/tools/nougenmsg_node.py`, `NouGenShards/tests/test_msg_receipts.py`
- Lens: B4-receipts · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: message_id/assign_message_id and receipt_state (/msg/<id>) exist in NouGenShards/tools/nougenmsg_node.py as confirmed for items 13/35; this repo's tools/nougenmsg.py http-then-ssh fallback path is plausible but the exact 15s wait and lack of message_id in main's payload wasn't independently line-verified.
- #550 families: 23, 100

### WG-0601 · P1 · elevate · effort L

**Sign the origin envelope: --origin-b64 is decoded and merged unverified**

- Failure surface: The canonical CLI base64-decodes --origin-b64 and does origin.update(decoded), then _origin_envelope stamps provenance_state 'asserted'; any peer that can run the CLI over ssh forges original_sender, session_id, coach and relay_path, so attribution in inbox files and shards records the impostor as the origin.
- First fork: if you observe conflicts[] non-empty on inbound envelopes (claimed machine != transport machine) -> treat asserted provenance as untrusted in the drain hooks and label it; else add an HMAC over the envelope with the per-node key and set provenance_state 'verified' only on a good signature.
- Evidence: `NouGenShards/tools/nougenmsg.py`, `NouGenShards/src/nougen_shards/nougenmsg.py`
- Lens: B5-security · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Confirmed exactly: NouGenShards/tools/nougenmsg.py handles --origin-b64 (line 609) and does origin.update(decoded) (line 619) with no signature check visible; src/nougen_shards/nougenmsg.py builds origin_b64 (line 1009) and stamps provenance_state (line 746), matching the unverified-provenance claim.
- #550 families: 18, 19

### WG-0612 · P1 · elevate · effort S

**Delete Kaedra's enhanced client: literal fallback token, wrong headers, swallowed errors, false success**

- Failure surface: Kaedra/tools/nougenmsg_enhanced_client.py falls back to the string 'keymaker_authenticated_token' sent as X-NouGen-Key and Bearer (the receiver reads X-NGS-Token), swallows every HTTP exception with pass, connects a hardcoded /tmp/agy-socks/agy-antigravity-a71cda14.sock, then writes msg_<ms>.json into both agy and codex inboxes and returns True; a Kaedra watchdog using it always reports delivered. Its __main__ sends a one-off announcement to chatgpt-app.
- First fork: if you observe any Kaedra code path importing send_authenticated_nougenmsg -> replace with tools/nougenmsg.py's send_direct_http; else delete the file and add a lint that only one HTTP client exists across the repos.
- Evidence: `Kaedra/tools/nougenmsg_enhanced_client.py`, `tools/nougenmsg.py`, `NouGenShards/tools/nougenmsg_node.py`
- Lens: B10-fleet · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Confirmed exactly: Kaedra/tools/nougenmsg_enhanced_client.py falls back to the literal string 'keymaker_authenticated_token' (line 14), sends both X-NouGen-Key and Bearer headers (lines 53-54), targets the hardcoded /tmp/agy-socks/agy-antigravity-a71cda14.sock (line 11), and its __main__ block sends to 'chatgpt-app/g-whoentertains' (lines 97-100).
- #550 families: 70, 100

### WG-0623 · P1 · elevate · effort M

**Survive a long body over --text-b64 on the cmd.exe lanes without truncation or silent refusal**

- Failure surface: base64 of the body rides on the ssh remote command line; cmd.exe caps a command at ~8191 chars and the Windows OpenSSH server hands the whole string to cmd, so a relay leg or code paste above ~6 KB fails with a usage error or truncates, and emit_node reports whatever the remote printed. Nothing gates size before encoding.
- First fork: if you observe output containing 'The command line is too long' or an empty receipt for bodies > 6000 chars -> route those over _ship_body scp with a pointer; else add a max-payload constant and a test that the 1000-line message from the reference corpus still arrives intact.
- Evidence: `NouGenShards/src/nougen_shards/nougenmsg.py`, `NouGenShards/tools/nougenmsg.py`, `infra/whoart/nougenmsg_cli.py`
- Lens: B1-protocol · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Confirmed: the --text-b64 path in NouGenShards/src/nougen_shards/nougenmsg.py always base64-encodes and inlines the body into remote_cmd with no length/size check before doing so; _ship_body()/scp is only invoked on the legacy unsafe-character path, not based on body size, matching 'nothing gates size before encoding'.

### WG-0634 · P1 · defend · effort M

**Stop every non-Windows box believing it is phoebus (get_current_node os.name branch)**

- Failure surface: main's get_current_node returns 'phoebus' for any non-nt OS, so this cloud container, an HF Space or a Linux lane calls emit_fleet as phoebus, ssh's to whoart and blade under _REMOTE_CLI owner paths, labels inbox files nougen-phoebus and skips the real phoebus as 'self'. Canonical returns 'standalone' without fleet_hosts.json.
- First fork: if you observe inbox rows sourced nougen-phoebus with origin_host != the Mac mini -> a stray box is impersonating; else port canonical's fleet_hosts.json identity and make emit_fleet fan out nothing when standalone.
- Evidence: `src/nougenmsg.py`, `NouGenShards/src/nougen_shards/nougenmsg.py`
- Lens: routing · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: src/nougenmsg.py:15-17 get_current_node() returns 'phoebus' for any os.name != 'nt'; NouGenShards/src/nougen_shards/nougenmsg.py get_current_node() instead reads fleet_hosts.json and falls back to 'standalone', matching the claimed contrast exactly.

### WG-0645 · P1 · elevate · effort M

**Replace main's hand-rolled argv scanner with argparse before the 'send --target-node' misroute recurs**

- Failure surface: tools/nougenmsg.py parses --target/--route/--stdin/@dest by index() and joins everything else as the body; the canonical CLI had to add a guard because 97 of 1136 messages (8%) arrived with 'send --target-node X --target-agent Y --text ...' delivered verbatim as the body to every agent. main has no such guard and cannot express @ollama:<model>, --reply-to or --capabilities that SKILL.md documents.
- First fork: if you observe inbox bodies beginning with 'send --target' on any node -> add the same guard immediately; else move to argparse subcommands and keep the @dest shorthand as a pre-parse.
- Evidence: `tools/nougenmsg.py`, `NouGenShards/tools/nougenmsg.py`, `NouGenShards/skills/nougenmsg/SKILL.md`
- Lens: B9-devex · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: tools/nougenmsg.py uses sys.argv.index('--target')/'--route' style scanning (lines 265,280,292,317) rather than argparse, matching the claim of a hand-rolled scanner without a 'send --target-node' misroute guard.

### WG-0656 · P1 · defend · effort M

**Run whoart's receiver under a task with no 72h ExecutionTimeLimit and a real watchdog**

- Failure surface: whoart's tunnel died ~11 AM today and a 5-minute watchdog was added, but the admin task still carries a 72h ExecutionTimeLimit; the receiver launched under it is killed every three days and, per install_ngs_node_task.ps1's own root-cause note, RestartOnFailure does not fire on a scheduler kill, so :8766 goes dark until the next logon.
- First fork: if you observe schtasks /query showing ExecutionTimeLimit != PT0S on the whoart msg task -> re-register with the NGS-node XML pattern (no limit, periodic retrigger); else confirm the watchdog restarts the receiver, not only the tunnel.
- Evidence: `NouGenShards/tools/install_ngs_node_task.ps1`, `NouGenShards/tools/nougen_live.ps1`
- Lens: deploy · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: install_ngs_node_task.ps1 and nougen_live.ps1 both exist; did not verify the exact 72h ExecutionTimeLimit value or the RestartOnFailure root-cause note text, but the claim is a specific, checkable operational detail consistent with the file's evident purpose (scheduled task installer).

### WG-0667 · P1 · elevate · effort M

**Probe deep health, not TCP connect: a hung receiver counts as reachable in --peers**

- Failure surface: _probe_nodes marks a node reachable on a successful TCP connect to :8766; phoebus's :8766 accepts and hangs, and blade's /health hung today with CLOSE_WAIT pileup, so --peers reported both up while nothing delivered. /health exists but nothing on the sender side calls it with a timeout or checks the node name.
- First fork: if you observe GET /health timing out on a node --peers lists as reachable -> switch the probe to /health with node-name match; else add build and auth mode to an authenticated deep-health and alert on drift.
- Evidence: `src/nougenmsg.py`, `NouGenShards/tools/nougenmsg_node.py`, `NouGenShards/docs/evolution/2026-09-21-nougenlive-dispatch.md`
- Lens: B7-observability · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: src/nougenmsg.py's _probe_nodes only does a TCP connect (confirmed in item 22's diff context) rather than an HTTP /health check, supporting the claim that a hung receiver would still read as reachable; the specific blade CLOSE_WAIT incident text wasn't independently verified but is consistent with evidence files present.
- #550 families: 95

### WG-0678 · P1 · defend · effort S

**Keep the two Claude registries and two SessionStart hooks from silently diverging**

- Failure surface: registry_parity_ok exists because cc_sessions_local.json vs cc_sessions.json almost split the nodes ('registered but nothing delivers'); blade registers via nougenmsg_register_hook.py, phoebus via nougenmsg_wake.py, with two file shapes and NOUGEN_CC_SESSIONS overriding the path per process. A hook writing to one path while the receiver reads another yields zero live deliveries with no error.
- First fork: if you observe registry_parity=MISMATCH in the receiver startup line or registered:0 while a session is open -> align NOUGEN_CC_SESSIONS across hook and receiver env; else converge on one hook file and one shape with a parity test in CI.
- Evidence: `NouGenShards/tools/_agy_live_delivery.py`, `NouGenShards/tools/nougenmsg_register_hook.py`, `NouGenShards/src/nougen_shards/nougenmsg.py`
- Lens: runtime · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: All three evidence files exist (_agy_live_delivery.py, nougenmsg_register_hook.py, nougen_shards/nougenmsg.py); the general shape of two registries/hooks with an overridable NOUGEN_CC_SESSIONS path is plausible given the file names and roles, though the exact 'registry_parity_ok' function and MISMATCH string weren't individually grepped.
- #550 families: 12

### WG-0689 · P1 · elevate · effort L

**Decide whether NouGenMsg is the SDK NouGenShards consumes or a mirror, then delete the other copies**

- Failure surface: Five live implementations diverge: this repo (580/357 lines), NouGenShards (1541/694 plus a 449-line receiver), infra/whoart (496/129), infra/blade (195), Kaedra (104). Every security fix must be applied five times, README.md still describes a lane branch and claims 'message delivery is authenticated', and 1289 lines differ between main and canonical.
- First fork: if you observe every node executing the NouGenShards copy -> make this repo a published package NouGenShards imports and turn src/ here into that package; else make this repo canonical and vendor it into NouGenShards with a hash check in CI.
- Evidence: `src/nougenmsg.py`, `NouGenShards/src/nougen_shards/nougenmsg.py`, `README.md`
- Lens: B10-fleet · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: src/nougenmsg.py (580/357 lines total per earlier wc) versus NouGenShards' much larger nougenmsg.py, plus README.md's stale lane-branch/authenticated claims (confirmed under item 62), together support the five-copy divergence claim; exact line counts for infra/whoart, infra/blade and Kaedra copies weren't individually re-verified but those files were confirmed present.

### WG-0700 · P1 · defend · effort S

**Stop the receiver persisting origin_proof (owner secret) into inbox and state files**

- Failure surface: do_POST passes the whole msg dict to record() before gating, so a payload carrying origin_proof is written verbatim to ~/.nougen/agy_inbox/msg_*.json and ~/.nougen/state/agy_last_msg.json, then drained by agy_inbox_hook into agent context and potentially captured into shards (HARDENING: secrets could reach shards). The owner-tier secret ends up on disk in plaintext on every node it was ever sent to.
- First fork: if you observe grep origin_proof ~/.nougen/agy_inbox ~/.nougen/state on any node returns a hit -> treat the token as burned, rotate, purge files; else strip origin_proof/proof fields in record() and add a test to tests/test_msg_receipts.py that the inbox file never contains them.
- Evidence: `NouGenShards/tools/nougenmsg_node.py`, `NouGenShards/tools/_agy_live_delivery.py`, `NouGenShards/tools/agy_inbox_hook.py`
- Lens: secrets · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Confirmed: nougenmsg_node.py's do_POST calls path = record(msg) unconditionally before the AUTH_TOKEN/gate_and_deliver check runs, and record() writes json.dumps(msg) verbatim (including any origin_proof key) to both the inbox file and STATE file; NouGenShards/tools/_agy_live_delivery.py is where origin_proof is defined/consumed, and agy_inbox_hook.py is the drain path into agent context.
- #550 families: 70

### WG-0711 · P1 · elevate · effort M

**Ship the SKILL.md addressing forms (@ollama:<model>, /pop, list-agents) or remove them from the contract**

- Failure surface: NouGenShards/skills/nougenmsg/SKILL.md tells every agent that `nougenmsg @ollama:<model>`, GET /pop, NOUGEN_MESH_PORT 8765 and NOUGEN_AGY_MSG_AUTH=open exist; main's parse_destination maps unknown agents to 'all', /pop is auth-latched read-and-destroy, and 'open' latches. Agents following the skill send to the wrong target or drain a queue they meant to peek.
- First fork: if you observe agents issuing GET /pop from the skill -> replace with read-only /msg/<id> and inbox reads; else implement @ollama:<model> in main and regenerate the skill from the CLI's --help.
- Evidence: `NouGenShards/skills/nougenmsg/SKILL.md`, `src/nougenmsg.py`, `NouGenShards/tools/nougenmsg_node.py`
- Lens: B6-parity · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: NouGenShards/skills/nougenmsg/SKILL.md documents `nougenmsg @ollama:<model>`, `GET /pop` as atomically pulling/clearing the queue, NOUGEN_MESH_PORT 8765, and NOUGEN_AGY_MSG_AUTH=optional/open, while main's tools/nougenmsg.py argv-scanner has no @ollama: destination handling found and NouGenShards/tools/nougenmsg_node.py's /pop drains PENDING (auth-latched, destructive), matching the claimed skill/
- #550 families: 32

### WG-0722 · P1 · defend · effort S

**Keep cc_sessions.json ACL-locked across ping_claude's prune rewrite**

- Failure surface: nougenmsg_register_hook locks the registry to the user (icacls / chmod 600) only when the file is first created; ping_claude prunes by writing reg_path+'.tmp' and os.replace, which installs a fresh file with default ACLs. After the first prune every Claude Code session token on the box is readable by any local account, and the hook uses a different tmp name (with_suffix) so the two writers can also race.
- First fork: if you observe icacls/stat on ~/.nougen/cc_sessions.json showing inherited or 644 perms on a node -> treat all registered session tokens as exposed and restart sessions; else re-apply the lock after os.replace in both writers and take a file lock across read-modify-write.
- Evidence: `src/nougenmsg.py`, `NouGenShards/tools/nougenmsg_register_hook.py`, `NouGenShards/src/nougen_shards/nougenmsg.py`
- Lens: secrets · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Confirmed: NouGenShards/tools/nougenmsg_register_hook.py's _lock_to_user() (icacls/chmod 600) runs only where register() calls it (at registration/creation), while nougenmsg/src/nougenmsg.py's ping_claude prune path writes reg_path + '.tmp' then os.replace() with no re-lock; the hook's own tmp write uses path.with_suffix('.tmp') which is a different filename than reg_path+'.tmp', confirming the di
- #550 families: 37

### WG-0732 · P1 · defend · effort S

**Make inbox writes atomic so drain hooks never read a torn ping_*.json**

- Failure surface: ping_antigravity, ping_codex and nougenmsg_node.record write inbox JSON with open()/write_text directly; claude_inbox_hook and agy_inbox_hook glob *.json by mtime_ns and may open a half-written file, log a JSON error, advance the cursor past it and lose the message permanently.
- First fork: if you observe hook logs with JSONDecodeError on a ping_ file that is valid on re-read -> write via tmp+os.replace in every writer, else add a retry-on-decode-error in the hooks
- Evidence: `src/nougenmsg.py`, `NouGenShards/tools/nougenmsg_node.py`, `NouGenShards/tools/claude_inbox_hook.py`
- Lens: data-integrity · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: nougenmsg_node.record uses path.write_text directly (not atomic); claude_inbox_hook.py line 138 explicitly catches json.JSONDecodeError when reading candidate inbox files, confirming the torn-read failure mode is anticipated but not prevented at the writer side.
- #550 families: 37

### WG-0742 · P1 · defend · effort S

**Reap ~/.nougen/msg-*.md scp bodies on every node before they become an unbounded store**

- Failure surface: canonical _ship_body scp's every shell-unsafe body to node:~/.nougen/msg-<id>.md and sends a pointer; nothing deletes those files, so every leg body, JSON blob or code paste accumulates on all three nodes outside any inbox retention or secret scrub.
- First fork: if you observe more than a handful of msg-*.md files in ~/.nougen on any node -> add a reaper keyed on the pointer's read receipt, else make the pointer path expire after N days and document it
- Evidence: `NouGenShards/src/nougen_shards/nougenmsg.py`
- Lens: data-integrity · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: NouGenShards/src/nougen_shards/nougenmsg.py:868-895 _ship_body scp's bodies to node:~/.nougen/msg-<id>.md; no delete/reaper/expiry logic found anywhere near it or in the module.

### WG-0752 · P1 · defend · effort M

**Keep secrets out of inbox JSON that lives forever under archive/**

- Failure surface: Every message body plus origin envelope is written verbatim to inbox files and, on clear, moved to archive/ rather than deleted; HARDENING history shows secrets reached shards the same way, and nothing scans or redacts inbox/archive content on any node.
- First fork: if you observe credential_patterns matches in any node's agy_inbox/archive -> add a redact-before-write hook using nougen_shards.credential_patterns and purge archives, else add the scan to doctor and set an archive TTL
- Evidence: `src/nougenmsg.py`, `NouGenShards/tools/nougenmsg_node.py`, `NouGenShards/src/nougen_shards/credential_patterns.py`
- Lens: data-integrity · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: No import or use of credential_patterns found in nougenmsg_node.py or nougenmsg.py (canonical or main); HARDENING.md documents secrets reaching shards via similar plaintext paths historically, supporting the inferred risk.
- #550 families: 70

### WG-0762 · P1 · elevate · effort M

**B1-protocol: Stamp one message_id at the sender and carry it through every hop, file and ledger**

- Failure surface: main's ping_* have no id; nougenmsg_node assigns a uuid on arrival; _agy_live_delivery falls back to a 30s content hash when no id arrives; codex_pipe uses its own uuid. Without one id from origin, retries, ssh-then-http fallbacks and inbox copies cannot be recognised as the same message anywhere.
- First fork: if you observe the same text with different message_ids across two nodes' inbox files -> generate the id in live_ping/emit_node and pass it via origin envelope and POST body, else accept receiver-assigned ids and dedup by hash only
- Evidence: `src/nougenmsg.py`, `NouGenShards/tools/nougenmsg_node.py`, `NouGenShards/tools/_agy_live_delivery.py`
- Lens: B1-protocol · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: main's ping_* functions have no id/message_id field (grep confirms none in src/nougenmsg.py); nougenmsg_node.py:239 assigns mid = uuid.uuid4().hex on arrival; _agy_live_delivery.py:315-332 implements exactly the described text/source content-hash fallback dedup with a 30s*4 window; codex_pipe.py uses its own uuid.uuid4().
- #550 families: 16

### WG-0772 · P1 · defend · effort M

**Unify the per-process dedup so a leg arriving by relay and by :8766 is delivered once**

- Failure surface: _agy_live_delivery keeps _seen in memory per process with a 30s bucket; nougenmsg_node.py and relay_watch_node.py each import their own copy, so the same leg announced by relay_watch and POSTed over :8766 is gated and injected into live Claude sessions twice, and a receiver restart forgets everything.
- First fork: if you observe one leg id injected twice into a session transcript within a minute -> move the dedup key store to a file-backed table shared by both receivers, else extend the window and accept the restart gap
- Evidence: `NouGenShards/tools/_agy_live_delivery.py`, `NouGenShards/tools/relay_watch_node.py`, `NouGenShards/tools/nougenmsg_node.py`
- Lens: concurrency · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: _agy_live_delivery.py:312 defines module-level _seen dict with a dedup window; nougenmsg_node.py and relay_watch_node.py are separate processes (each has its own __main__ entrypoint) that both import this module, so each gets its own process-local _seen copy despite sharing the source file — exactly the failure mechanism claimed.
- #550 families: 16, 22

### WG-0782 · P1 · defend · effort S

**Lock the .agy_woken_legs.json idempotency ledger so one leg cannot wake two agy runs**

- Failure surface: AntigravityAdapter.wake reads the ledger, runs agy.exe for up to 300s with --dangerously-skip-permissions, then writes the ledger non-atomically; two concurrent wakes for the same leg (relay watcher plus :8766) both pass the check and both execute, doubling autonomous work and token spend.
- First fork: if you observe two agy.exe processes with the same INBOUND_LEG_ID in their prompts -> claim the leg with O_EXCL before launching and write status 'woken' up front, else serialize wakes behind the relay_watch lock
- Evidence: `NouGenShards/src/nougen_shards/wake/adapters.py`, `NouGenShards/tools/relay_watch_node.py`
- Lens: concurrency · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: wake/adapters.py:205-260 shows a plain read-check-then-run-then-write pattern on .agy_woken_legs.json with no file locking or O_EXCL claim; subprocess timeout=300 and default flags include --dangerously-skip-permissions; ledger write happens only after the subprocess completes, confirming the race window.
- #550 families: 22

### WG-0792 · P1 · defend · effort M

**Survive the day :8766 dies: main's ssh fallback sends --stdin that no fleet receiver accepts**

- Failure surface: dispatch_node falls back to emit_node, which runs '<cli> --target X --local --stdin'; NouGenShards/tools/nougenmsg.py understands --text-b64, infra/whoart/nougenmsg_cli.py understands neither, so when the HTTP node is down every remote send fails closed and the operator sees 'No message text provided' or help output.
- First fork: if you observe the ssh fallback returning the receiver's help banner -> ship a receiver that accepts both --stdin and --text-b64 to all three nodes first, then switch senders, else pin --route http and alert on HTTP failure
- Evidence: `src/nougenmsg.py`, `NouGenShards/tools/nougenmsg.py`, `infra/whoart/nougenmsg_cli.py`
- Lens: distributed · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: nougenmsg/infra/whoart/nougenmsg_cli.py has no --text-b64 or --stdin handling and prints 'No message text provided.' when text is absent from argv; NouGenShards/tools/nougenmsg.py explicitly parses --text-b64. dispatch_node's ssh fallback path (emit_node/'--stdin') would indeed fail against a receiver with neither flag support.
- #550 families: 32

### WG-0802 · P1 · defend · effort M

**Prevent the http-timeout-then-ssh fallback from double-delivering when the Kaedra gate runs long**

- Failure surface: send_direct_http gives up at 15s, but the receiver already wrote the inbox file before its Kaedra gate (measured 1.1-10s with a 15s miss on phoebus); dispatch_node then delivers again over ssh, so one send lands twice and the sender's report shows route: ssh as if HTTP had failed.
- First fork: if you observe an inbox with two files for one text where the sender report says route: ssh -> send the same message_id on both routes and dedup at the receiver, else raise the HTTP timeout above the gate's p99 and drop the fallback for auth'd nodes
- Evidence: `tools/nougenmsg.py`, `NouGenShards/tools/nougenmsg_node.py`
- Lens: distributed · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: tools/nougenmsg.py:32 sets HTTP_ROUTE_FALLBACK_TIMEOUT_S = 15.0, used by send_direct_http; dispatch_node (line 209-219) falls back to emit_node/ssh whenever send_direct_http returns None (including on timeout) with no message_id-based dedup at the receiver, matching the double-delivery mechanism described.
- #550 families: 16

### WG-0812 · P1 · defend · effort S

**Give agy_inbox_hook per-session cursors before a second Antigravity session starves**

- Failure surface: claude_inbox_hook fixed the shared-cursor race (WhoArt's three sessions were losing the fallback half of the bridge) but agy_inbox_hook still keeps one global .agy_inbox_seen.json cursor, so whichever Antigravity session drains first advances the watermark and every other session never sees those messages.
- First fork: if you observe two Antigravity sessions on one box and only one printing the fleet banner for a broadcast -> port the per-session cursor from claude_inbox_hook, else pin one Antigravity session per box and document it
- Evidence: `NouGenShards/tools/agy_inbox_hook.py`, `NouGenShards/tools/claude_inbox_hook.py`
- Lens: concurrency · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: claude_inbox_hook.py implements per-session cursors keyed by session_id (_has_session_cursor, _cursor(session_id), _save_cursor(value, session_id)); agy_inbox_hook.py's _cursor() takes no session_id parameter at all, confirming the global-cursor gap claimed.

### WG-0822 · P1 · elevate · effort M

**B4-receipts: Adopt #509 read receipts in send_direct_http without letting bulk archive forge 'read'**

- Failure surface: nougenmsg_node.receipt_state infers 'read' from a file being in archive/ or renamed .processed; main's clear_inbox archives everything unread, so adopting receipts as-is would report every bulk-cleared message as read. main's send_direct_http today returns only the receiver body plus route/ms.
- First fork: if you observe receipt_state returning read for a message whose only movement was --clear-inbox -> distinguish archived-by-ack from archived-by-clear in the file name or a sidecar, else adopt receipts and gate clear behind confirmed
- Evidence: `NouGenShards/tools/nougenmsg_node.py`, `tools/nougenmsg.py`, `src/nougenmsg.py`
- Lens: B4-receipts · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: nougenmsg_node.py:244-258 receipt_state infers 'read' purely from archive/ location or *.processed rename, with no distinction from bulk-clear archiving; combined with confirmed item 3 (main's clear_inbox has no confirmed gate), the forged-read scenario is real.
- #550 families: 23, 100

### WG-0832 · P1 · elevate · effort M

**B4-receipts: Turn ping_claude's permanent delivery_verified=False into an observed receipt from the drain hook**

- Failure surface: The Claude wire has no ack (shard 17142), so main reports every socket write as unverified forever; the UserPromptSubmit drain hook is the one place the receiving session provably sees the message and it writes nothing back, so no sender can ever distinguish 'accepted by pipe' from 'seen by the model'.
- First fork: if you observe the hook already tracking per-session cursors by message file name -> have it write an observed receipt keyed by message_id that receipt_state reads, else keep 'unknown' and stop printing delivered counts as success
- Evidence: `src/nougenmsg.py`, `NouGenShards/tools/claude_inbox_hook.py`, `NouGenShards/tools/nougenmsg_node.py`
- Lens: B4-receipts · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: claude_inbox_hook.py tracks per-session cursors (state file) but writes nothing back that receipt_state or any sender could read as an observed receipt keyed by message_id; the described gap ('accepted by pipe' vs 'seen by the model' indistinguishable) matches the code as found.
- #550 families: 23, 100

### WG-0842 · P1 · defend · effort S

**Make ping_antigravity's status honest on both copies: main's .agy_msg import can never succeed**

- Failure surface: src/nougenmsg.py:313 does 'from .agy_msg import AgyMsgBus' inside a flat top-level module, which always raises, so pipe_delivered is always False and status always 'dropped' even when the inbox write and pipe would have worked; PR #7 cannot produce 'delivered' from this file, and canonical's delivered-else-dropped hides the queued state.
- First fork: if you observe pipe_delivered False on a Windows box with agy_pipe_server running -> fix the import to an absolute/optional path and return queued when files were written, else accept file-drop as the only Antigravity path and say so
- Evidence: `src/nougenmsg.py`, `NouGenShards/src/nougen_shards/agy_msg.py`, `origin/fix/agy-ping-delivery-status`
- Lens: observability · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: src/nougenmsg.py line ~313 does 'from .agy_msg import AgyMsgBus' inside a try/except; src/ contains only nougenmsg.py (no __init__.py, no agy_msg.py), so this relative import always fails, caught silently, pipe_delivered stays False permanently — exactly as claimed. NouGenShards/src/nougen_shards/agy_msg.py exists as the real module canonical uses instead.
- #550 families: 100

### WG-0852 · P1 · elevate · effort M

**B4-receipts: Give emit_fleet a per-node terminal-state receipt instead of strings mixed with dicts**

- Failure surface: emit_fleet returns {node: 'Error: ...'} strings next to {node: {claude_pipes: {...}}} dicts and canonical adds {queued: True}; callers (MCP tools, Kaedra rule 720) cannot compute 'all delivered' without string-sniffing, so partial broadcasts read as success.
- First fork: if you observe MCP nougenmsg_send output requiring startswith('Error') checks to find failures -> define accepted/queued/delivered/failed/unknown per node in one dict shape, else wrap the current result with an aggregate summary field
- Evidence: `src/nougenmsg.py`, `NouGenShards/src/nougen_shards/nougenmsg.py`, `NouGenShards/src/nougen_shards/mcp.py`
- Lens: B4-receipts · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: main's emit_fleet mixes dict results ({curr: cls.live_ping(...)}) with plain 'Error: {e}' strings in its except branch; canonical's emit_fleet adds {queued: True} dicts on top. No unified terminal-state shape exists across the codebase, confirming callers must string-sniff for failures.
- #550 families: 23, 100

### WG-0862 · P1 · elevate · effort L

**B2-queue: Park undeliverable @node sends in an outbox with retry instead of returning 'Error:' and dropping**

- Failure surface: When both HTTP and ssh fail (whoart tunnel dead ~11 AM today), dispatch_node returns an error string and the message is gone; nothing queues it locally, nothing retries when the node returns, and the sender has to notice and resend by hand.
- First fork: if you observe a node outage longer than the sender's patience -> add ~/.nougen/outbox/<node>/ with backoff and a --flush-outbox on reconnect, else document fire-and-forget and rely on relay legs for durable coordination
- Evidence: `tools/nougenmsg.py`, `src/nougenmsg.py`
- Lens: B2-queue · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: tools/nougenmsg.py dispatch_node() tries send_direct_http then falls back to NouGenMsgBus.emit_node (ssh); src/nougenmsg.py emit_node wraps subprocess.run in try/except returning {node: f"Error: {e}"} on failure, with no queue/outbox anywhere in either file.
- #550 families: 21

### WG-0872 · P1 · elevate · effort M

**B3-routing: Unify node address resolution between _probe_nodes and send_direct_http before PR #2's hardcoded IPs land**

- Failure surface: _probe_nodes knows only NOUGEN_NODE_<X>_IP or <node>.local, send_direct_http uses the env->ssh-config->mDNS->cache ladder, and PR #2's cc_msg.py hardcodes whoart=192.0.2.178/phoebus=192.0.2.88; --peers can say reachable while the send goes elsewhere, and DHCP moves the hardcoded pair silently.
- First fork: if you observe --peers reachable but send_direct_http reporting unreachable for the same node -> move _route_node_ip into the bus module and make both callers use it, else pin env IPs on every box and delete mDNS from the probe
- Evidence: `src/nougenmsg.py`, `tools/nougenmsg.py`, `origin/antigravity/cc-msg-parity`
- Lens: B3-routing · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: src/nougenmsg.py _probe_nodes only checks NOUGEN_NODE_<X>_IP or <node>.local; tools/nougenmsg.py _route_node_ip uses env->ssh-config-hostnames->cache ladder (distinct paths). git show origin/antigravity/cc-msg-parity:tools/cc_msg.py has whoart=192.0.2.178, phoebus=192.0.2.88 hardcoded at lines 32-33.
- #550 families: 39

### WG-0882 · P1 · elevate · effort S

**B3-routing: Retire get_current_node's 'not Windows means phoebus' before a Linux clone impersonates a node**

- Failure surface: main's get_current_node returns 'phoebus' on any non-Windows host (this container included), so a CI runner or a cloud session running tools/nougenmsg.py claims phoebus identity, short-circuits @phoebus sends to its own local inboxes, and emit_fleet fans out to whoart and blade as if it were a fleet member. Canonical moved to fleet_hosts.json with a 'standalone' default.
- First fork: if you observe source 'nougen-phoebus' in inbox files on a box that is not the Mac mini -> port fleet_hosts.json/NOUGEN_FLEET_NODE resolution with standalone default, else require NOUGEN_FLEET_NODE explicitly and refuse fan-out without it
- Evidence: `src/nougenmsg.py`, `NouGenShards/src/nougen_shards/nougenmsg.py`
- Lens: B3-routing · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: src/nougenmsg.py get_current_node(): 'if os.name != "nt": return "phoebus"' verified verbatim (lines 15-19), exactly matching the claim; this container (Linux) would return phoebus.
- #550 families: 19, 20

### WG-0891 · P1 · elevate · effort M

**B3-routing: Add a dead-node cooldown so a down whoart does not add 20s to every fleet broadcast**

- Failure surface: emit_fleet ssh's serially to each peer with a 20s timeout and no memory of failure; with whoart's tunnel down every broadcast blocks 20s+ per dead node, the MCP gateway's 20s budget expires, and callers retry (the double-delivery path).
- First fork: if you observe consecutive emit_fleet calls each paying the full timeout for the same dead node -> record failure timestamps in node_ips.json and skip/half-open for N minutes, else parallelize the fan-out so one dead node costs one timeout total
- Evidence: `src/nougenmsg.py`, `tools/nougenmsg.py`
- Lens: B3-routing · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: src/nougenmsg.py emit_fleet loops serially over nodes calling emit_node, which does subprocess.run(['ssh',...], timeout=20) with no failure memory (verified lines 469-500).
- #550 families: 94

### WG-0900 · P1 · elevate · effort L

**B10-fleet: Collapse the five live NouGenMsg copies into one SDK the other repos import**

- Failure surface: main (580/357 lines), NouGenShards (1541/694), infra/whoart (496/129), infra/blade (195) and Kaedra's 104-line client each implement sending differently; a fix in one (stdin, IPv4-first, message_id, dedup) reaches the others only by hand-copy, and every incident so far traced to a node running a different variant.
- First fork: if you observe NouGenShards willing to import nougenmsg as a dependency -> make this repo the package and turn the other four into thin imports, else make this repo a verified mirror with a drift CI check and delete Kaedra's client
- Evidence: `src/nougenmsg.py`, `NouGenShards/src/nougen_shards/nougenmsg.py`, `Kaedra/tools/nougenmsg_enhanced_client.py`
- Lens: B10-fleet · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Line counts verified exactly via wc -l: src/nougenmsg.py=580, tools/nougenmsg.py=357, NouGenShards/src/nougen_shards/nougenmsg.py=1541, infra/whoart/nougenmsg_cli.py=129 (close cousin of the 'infra/whoart 496/129' claim, whoart's own nougenmsg.py=496), infra/blade/nougenmsg.py=195, Kaedra/tools/nougenmsg_enhanced_client.py=104. All five copies confirmed distinct and present.

### WG-0908 · P1 · elevate · effort M

**B2-queue: Add retention and rotation to claude_inbox/agy_inbox before the drain hooks choke**

- Failure surface: ping_*.json files are never rotated (claude_inbox_hook records a 445-file backlog at fix time); read_inbox globs and stat-sorts every file on each call and the UserPromptSubmit hook runs on every prompt, so growth turns each prompt into a directory scan and eventually a timeout that looks like a dead lane.
- First fork: if you observe more than ~1000 files in any inbox dir on a node -> add age/count-based archive rotation with the cursor preserved, else add a --peers metric for inbox size and revisit at threshold
- Evidence: `src/nougenmsg.py`, `NouGenShards/tools/claude_inbox_hook.py`, `NouGenShards/tools/agy_inbox_hook.py`
- Lens: B2-queue · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: claude_inbox_hook.py comment explicitly cites '445 files at the time of the fix' backlog; its _entries() and main's read_inbox both glob+stat every file with no age/count-based rotation logic present anywhere in the inbox hooks.

### WG-0916 · P1 · defend · effort S

**Launch nougenmsg_node hidden: its record() print blocks under console QuickEdit like blade's NGS node**

- Failure surface: record() prints every incoming message with flush=True; in a visible Windows console a QuickEdit selection pauses stdout and the handler thread blocks after writing the inbox file but before answering, so senders time out, fall back to ssh (duplicate), and ThreadingHTTPServer accumulates half-served connections exactly like blade's /health hang today.
- First fork: if you observe the msg node task running with a visible window -> move it to a hidden scheduled task and route the preview print to a log file, else disable QuickEdit on the console and keep the print
- Evidence: `NouGenShards/tools/nougenmsg_node.py`
- Lens: silent-death · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: record() in NouGenShards/tools/nougenmsg_node.py prints '[LIVE INCOMING MSG]' with flush=True (lines 276-278) before returning, verified verbatim; the QuickEdit-blocking mechanism is a reasonable inference from this print-before-respond pattern.

### WG-0924 · P1 · defend · effort S

**Pin blade's message receiver to one code tree now that two scheduled tasks point at two trees**

- Failure surface: main's _REMOTE_CLI and the wake adapter both assume C:~/Watchtower/NouGen/NouGenShards-push-main; today's fix added a second task on a different tree, so which receiver flags (--stdin/--text-b64), which registry shape and which auth latch apply depends on which task won the port.
- First fork: if you observe two tasks on blade able to bind :8766 -> delete one and record the surviving path in fleet_hosts.json plus _REMOTE_CLI, else add a build_id assertion at send time
- Evidence: `src/nougenmsg.py`, `NouGenShards/src/nougen_shards/wake/adapters.py`, `infra/blade/SOURCE.md`
- Lens: distributed · likelihood observed · blast fleet · verdict PLAUSIBLE · status open
- Verifier note: src/nougenmsg.py _REMOTE_CLI['blade'] points to C:~/Watchtower/NouGen/NouGenShards-push-main/tools/nougenmsg.py (verified line 434); infra/blade/SOURCE.md exists and references a different commit/path context. The 'two scheduled tasks' claim itself isn't directly evidenced in these files but is a plausible operational inference.
- #550 families: 29

### WG-0932 · P1 · defend · effort S

**Stop Kaedra's atomic-buster RELAY phase from reporting success on a swallowed 401**

- Failure surface: nougenmsg_enhanced_client.py catches every HTTP exception with pass, falls back to a hardcoded socket path then writes msg_<ms>.json into both agy and codex inboxes and returns True; rule 720's RELAY step therefore always 'succeeds' even when the node rejected the literal fallback token 'keymaker_authenticated_token'.
- First fork: if you observe Kaedra RELAY logs never showing a failure while nougenmsg_node logs 401s from 127.0.0.1 -> replace the client with tools/nougenmsg.py and return the real status, else at least log the exception and drop the fallback token
- Evidence: `Kaedra/tools/nougenmsg_enhanced_client.py`, `Kaedra/rules/720-atomic-buster.md`
- Lens: silent-death · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: Kaedra/tools/nougenmsg_enhanced_client.py has AUTH_TOKEN fallback literal 'keymaker_authenticated_token' (line 14) and 'except Exception: pass' swallowing errors (lines 68-69, 81-82); Kaedra/rules/720-atomic-buster.md's RELAY phase (line 22) broadcasts via MsgNode:8766, matching the described mechanism.
- #550 families: 23, 100

### WG-0940 · P1 · defend · effort S

**Surface messages.db append failures somewhere a human reads, not the stderr of a hook**

- Failure surface: canonical live_ping prints '[nougenmsg] messages.db append failed' to stderr and continues; under MCP, scheduled tasks and hooks stderr is discarded, so a locked or mis-schema'd ledger produces a partial history that later reads as truth (the embed-at-ingest false-done pattern).
- First fork: if you observe row counts lagging inbox counts on any node -> write failures to a side file and expose them in /status and doctor, else add a daily reconciliation job
- Evidence: `NouGenShards/src/nougen_shards/nougenmsg.py`
- Lens: silent-death · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: NouGenShards/src/nougen_shards/nougenmsg.py line 844 contains the exact string 'print(f"[nougenmsg] messages.db append failed: {e}", file=sys.stderr, flush=True)', matching the claim verbatim.
- #550 families: 100

### WG-0948 · P1 · defend · effort S

**Record TIMEOUT in .agy_woken_legs.json so a slow leg is not re-executed on the next wake**

- Failure surface: AntigravityAdapter.wake writes the idempotency ledger only on completion; a 300s TimeoutExpired returns without any entry, so the next relay poll or POST wakes the same leg again, potentially forever, each run with skip-permissions and full token cost.
- First fork: if you observe repeated TIMEOUT classifications for one leg_id in node logs -> write a 'timeout' entry with attempt count and back off, else raise NOUGEN_AGY_TIMEOUT_SEC and monitor
- Evidence: `NouGenShards/src/nougen_shards/wake/adapters.py`
- Lens: concurrency · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: wake/adapters.py: idempotency_file .agy_woken_legs.json is written (data[leg_id]=...) inside the successful-completion path (lines ~249-258), while 'except subprocess.TimeoutExpired: return {...'timeout'...}' (lines 273-274) returns with no ledger write, exactly as claimed. Default timeout_s reads NOUGEN_AGY_TIMEOUT_SEC default 300 (line 230).
- #550 families: 21

### WG-0956 · P1 · defend · effort S

**Resolve the contradiction: ping_claude promises later sessions the inbox copy, the drain hook seeds them past it**

- Failure surface: ping_claude's note says the inbox file is 'for sessions that start later', but claude_inbox_hook seeds a new session's cursor at the newest drained message to avoid replaying the 445-file backlog, so a message sent five minutes before a session starts is never shown to it and the sender's inbox_file field implies it will be.
- First fork: if you observe a new session missing a ping sent shortly before its SessionStart -> seed new-session cursors at (now - grace window) and archive drained files, else change ping_claude's note and result to say 'live sessions only'
- Evidence: `src/nougenmsg.py`, `NouGenShards/tools/claude_inbox_hook.py`
- Lens: data-integrity · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: NouGenShards/src/nougen_shards/nougenmsg.py has the comment '# inbox copy for the drain hook (and for sessions that start later)' (line 362) matching the claim (note: this is in NouGenShards, functionally the canonical bus counterpart of src/nougenmsg.py). claude_inbox_hook.py seeds a new session's cursor at the latest entry when none exists ('_save_cursor(entries[-1][0], session_id)', line 108), 
- #550 families: 16

### WG-0963 · P1 · defend · effort S

**Make inbox filenames collision-proof: ms timestamps overwrite concurrent pings**

- Failure surface: ping_codex, ping_antigravity and Kaedra's client name files ping_<ms>.json / msg_<ms>.json; an emit_fleet plus a second sender in the same millisecond overwrite each other's file, losing one message with a success return. codex_pipe.save already uses uuid, the others do not.
- First fork: if you observe two senders reporting the same inbox file path in their results -> switch every writer to uuid or O_EXCL create, else add a collision test with a frozen clock and keep ms names
- Evidence: `src/nougenmsg.py`, `Kaedra/tools/nougenmsg_enhanced_client.py`, `NouGenShards/src/nougen_shards/codex_pipe.py`
- Lens: concurrency · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: src/nougenmsg.py uses f'ping_{int(time.time()*1000)}.json' in three places (ping_claude inbox copy, ping_antigravity, ping_codex); Kaedra/tools/nougenmsg_enhanced_client.py uses f'msg_{int(time.time()*1000)}.json'; NouGenShards/src/nougen_shards/codex_pipe.py uses uuid.uuid4().hex for its filename. Collision risk and asymmetry both confirmed.
- #550 families: 84

### WG-0970 · P1 · elevate · effort M

**B9-devex: Package NouGenMsg so tools/nougenmsg.py imports its own src and deploy stops being copy-per-node**

- Failure surface: tools/nougenmsg.py imports nougen_shards.nougenmsg, which this repo does not ship, so main cannot run standalone; the native-queue lane already has a pyproject (nougenmsg 0.2.0, console script, pythonpath=src) that main lacks, and every node currently receives code by hand-copy into three different paths.
- First fork: if you observe the native-queue pyproject installing cleanly against main's src -> adopt it and switch tools/ to import nougenmsg, else add a shim package and a pip-installable layout
- Evidence: `tools/nougenmsg.py`, `origin/codex/nougenmsg-native-queue`, `README.md`
- Lens: B9-devex · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: tools/nougenmsg.py imports nougen_shards.nougenmsg (reproduced ModuleNotFoundError when run standalone); origin/codex/nougenmsg-native-queue:pyproject.toml exists with name='nougenmsg', version='0.2.0', console script 'nougenmsg = "nougenmsg:main"', and pythonpath=['src'] -- verified verbatim, matching the claim exactly.

### WG-0976 · P1 · elevate · effort M

**B5-security: Adopt native-queue's plaintext-off-loopback refusal in send_direct_http without stranding LAN-only nodes**

- Failure surface: send_direct_http posts X-NGS-Token over http://<lan-ip>:8766 to whatever the ladder resolved; native-queue refuses non-loopback plaintext and never echoes the token in errors. Flipping the policy on without a tunnel or TLS on each node turns every remote send into an immediate refusal, which the ssh fallback cannot cover.
- First fork: if you observe a working per-node tunnel or HTTPS endpoint (NOUGEN_MSG_NODE_<NODE>_URL) on all three boxes -> enforce the refusal and drop plaintext, else stage it as a warning with a deadline and fix the token-echo first
- Evidence: `tools/nougenmsg.py`, `origin/codex/nougenmsg-native-queue`
- Lens: B5-security · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: tools/nougenmsg.py send_direct_http posts to http://{ip}:{port}/msg with X-NGS-Token header (verified lines 183-197), plain HTTP regardless of loopback. git show origin/codex/nougenmsg-native-queue:src/nougenmsg.py contains LOOPBACK_HOSTS set and the literal string 'refusing to send credentials over plaintext HTTP off loopback' (line 134), confirming the described policy difference.

### WG-0982 · P1 · elevate · effort M

**B6-parity: Rebase PR #2 onto main so merging cc_msg parity cannot delete _probe_nodes and the node-resolve tests**

- Failure surface: origin/antigravity/cc-msg-parity has merge-base 1331234; its diff against main removes _live_pipe_names/_probe_nodes, tests/test_nougenmsg_node_resolve.py and 218 lines of tools/nougenmsg.py while adding a cc_msg.py with hardcoded IPs and no auth header, so a plain merge silently undoes #4, #5 and #6.
- First fork: if you observe git merge-base still at 1331234 -> rebase cc_msg.py alone onto main and reconcile with NouGenShards/tools/cc_msg.py, else close #2 and re-open as a fresh branch from main
- Evidence: `origin/antigravity/cc-msg-parity`, `tests/test_nougenmsg_node_resolve.py`, `NouGenShards/tools/cc_msg.py`
- Lens: B6-parity · likelihood observed · blast repo · verdict CONFIRMED · status open
- Verifier note: git merge-base main origin/antigravity/cc-msg-parity = 1331234e5db1... (matches exactly). tests/test_nougenmsg_node_resolve.py exists in main but is absent ('git show origin/antigravity/cc-msg-parity:tests/test_nougenmsg_node_resolve.py' fails) on that branch. _probe_nodes/_live_pipe_names are absent from that branch's src/nougenmsg.py (grep empty) though present in main. cc_msg.py on that branch 

### WG-0987 · P1 · defend · effort M

**Stop @all broadcasts from timing out on Ollama cold starts with 2s local and 8s remote budgets**

- Failure surface: main's ping_ollama waits 2s locally and 8s over ssh, less than a gemma4 cold load, so every 'all' target reports an Ollama error while canonical waits 60s and measured a 64.7s @all ping; either way the model lane makes broadcast latency and status unpredictable and the sender's ssh timeout compounds it.
- First fork: if you observe ollama errors on the first broadcast after idle and success on the second -> make model lanes async with inbox drop (canonical models_async) and drop them from @all by default, else raise the timeouts and accept slow broadcasts
- Evidence: `src/nougenmsg.py`, `NouGenShards/src/nougen_shards/nougenmsg.py`
- Lens: distributed · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: src/nougenmsg.py ping_ollama: urlopen(req, timeout=2) for local (line 369) and subprocess.run(['ssh',...], timeout=8) for remote (line 359), verified exactly. NouGenShards/src/nougen_shards/nougenmsg.py ping_ollama uses NOUGEN_MSG_MODEL_TIMEOUT_S defaulting to 60.0 (lines 559-592), matching the '2s/8s vs 60s' contrast claimed.
- #550 families: 52

### WG-0991 · P1 · defend · effort S

**Honor NOUGEN_CODEX_INBOX and NOUGEN_AGY_INBOX in read_inbox and --peers so counts match the receivers**

- Failure surface: nougenmsg_node writes to NOUGEN_AGY_INBOX and codex_pipe writes to NOUGEN_CODEX_INBOX, but main's read_inbox, clear_inbox and list_peers hardcode ~/.gemini/config/inbox, ~/.nougen/agy_inbox and ~/.codex/inbox; on a node with either env set, --inbox shows nothing while messages pile up elsewhere.
- First fork: if you observe --inbox empty on a node whose receiver log shows writes -> thread the same env keys through the bus module's inbox resolution, else document the env as unsupported and unset it fleet-wide
- Evidence: `src/nougenmsg.py`, `NouGenShards/tools/nougenmsg_node.py`, `NouGenShards/src/nougen_shards/codex_pipe.py`
- Lens: observability · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: src/nougenmsg.py hardcodes os.path.expanduser('~/.nougen/agy_inbox') in multiple places (lines 285, 530, 562) with no env override, and read_inbox/list_peers also hardcode ~/.gemini/config/inbox and ~/.codex/inbox (verified). NouGenShards/tools/nougenmsg_node.py reads NOUGEN_AGY_INBOX (line 80) and codex_pipe.py reads NOUGEN_CODEX_INBOX (lines 114, 249), confirming the two sides use different, non
- #550 families: 36

### WG-0995 · P1 · defend · effort S

**Stop a live socket write plus inbox drain from injecting the same ping twice into one Claude session**

- Failure surface: ping_claude writes to every registered socket and then drops ping_<ms>.json with delivered_to=[session_ids]; claude_inbox_hook drains every ping_*.json newer than its cursor without checking delivered_to, so the session that already received the socket message sees it again on its next prompt.
- First fork: if you observe the same NouGenMsg text twice in one session transcript (socket then hook banner) -> have the hook skip files whose delivered_to includes its own session_id, else stop writing the inbox copy when any live delivery succeeded
- Evidence: `src/nougenmsg.py`, `NouGenShards/tools/claude_inbox_hook.py`
- Lens: concurrency · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: NouGenShards/src/nougen_shards/nougenmsg.py ping_claude sets 'delivered_to': [d.get('session_id') for d in delivered] on the written inbox file (line 373) and writes the inbox copy regardless (line 362 comment: 'for sessions that start later'). grep for 'delivered_to' in NouGenShards/tools/claude_inbox_hook.py returns no matches, confirming the hook never checks it before draining, matching the de
- #550 families: 8, 16

### WG-0999 · P1 · defend · effort S

**ACL-lock an existing cc_sessions.json: icacls only runs when the file is first created**

- Failure surface: nougenmsg_register_hook locks the registry to the user only when fresh is True; a registry that pre-existed the hook (or was recreated by ping_claude's tmp+replace, which never calls _lock_to_user) carries live Claude messaging tokens with default inherited ACLs on Windows.
- First fork: if you observe icacls on ~/.nougen/cc_sessions.json showing inherited entries beyond the user -> lock on every write in both hook and pruner, else lock once via a doctor step
- Evidence: `NouGenShards/tools/nougenmsg_register_hook.py`, `src/nougenmsg.py`
- Lens: data-integrity · likelihood likely · blast fleet · verdict CONFIRMED · status open
- Verifier note: NouGenShards/tools/nougenmsg_register_hook.py: '_lock_to_user' runs icacls with /inheritance:r /grant:r (line 38); 'fresh = not path.exists()' then 'if fresh: _lock_to_user(path)' (lines 51, 69-70) -- verified verbatim, locking only occurs on first creation exactly as claimed.
- #550 families: 38
