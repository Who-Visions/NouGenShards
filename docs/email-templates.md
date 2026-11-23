# Email Templates — Render-Only Fleet Tools

The fleet ships the verified Hotel Visions tester-invite email as
**render-only** MCP tools: `email_template_list` and
`email_template_render`. They turn a template + variables into the HTML
and plain-text parts of an email. They never send anything — there is
no send tool on this surface, by design (see [Send flow](#send-flow)).

## Status — read this first

**PR unmerged; tools not live until merged + deployed.** This work
landed on branch `feat/email-templates-mcp` and is awaiting review and
merge. Until the PR merges and a supervisor release + deploy picks it
up, no fleet lane can call these tools. The template itself is verified
(the guest-pack render was checked against the first sent tester invite
on 2026-11-22); the fleet tools are unit-tested locally
(`tests/test_mcp_email_templates.py`).

What is *not* verified yet: a live render through the deployed node
(needs the merge + deploy first), and any send — no send has happened
through this path, and none will until the send flow below is followed
with a real postal address on file.

## The template system

One template ships today: **invite-tester** — the tester invitation
email, generalized from the first sent tester invite
(2026-11-22). Layout, neon-green styling, copy, structure, the public
name "Unk", and the front-desk help line are unchanged from that source;
only the tester-specific values became `{{placeholders}}`.

Files:

- `src/nougen_shards/email_templates/invite-tester.html` — HTML email,
  600 px, inline CSS, dark-mode rules.
- `src/nougen_shards/email_templates/invite-tester.txt` — matching
  plain-text version, always rendered alongside the HTML.
- `src/nougen_shards/email_templates.py` — the registry:
  `list_templates()` and `render_template(name, variables)`.

**Canonical source and sync rule.** The files under
`src/nougen_shards/email_templates/` are byte-identical copies of the
verified templates in the NouGenMuse guest-pack work
(`~/workspace/guest-pack/email/templates/`). That directory is the
canonical source. If it changes, copy the files over verbatim and
verify with `diff` — never hand-edit the shipped copies, or the two
will drift and a render here will no longer match the template the
mail worker was verified against. The renderer for the canonical
templates is `~/workspace/guest-pack/email/render_email.py`
(stdlib only); the fleet module mirrors its semantics exactly.

Rendering semantics (same as `render_email.py`):

- Plain `{{variable}}` substitution, one pass, values inserted
  verbatim — **no HTML escaping**. Keep values plain text or full URLs.
- Every variable the template uses is required. A missing variable is
  an error that names the missing ones; nothing is rendered.
- Any `{{placeholder}}` left in the output is an error. One deliberate
  exception: a variable whose value is literally its own placeholder
  text (see `{{business_address}}` below) is preserved as-is — the
  verification case.
- Non-string variable values are rejected.
- Template names are restricted to `[A-Za-z0-9_-]+`; both the `.html`
  and the `.txt` must exist, or the template is unknown.

## Fleet MCP tools

Both return JSON strings. Both are `OWNER_ONLY` in
`src/nougen_shards/tenant_policy.py` — the templates are owner IP
(house copy and voice) and render the owner's invite; tenants never
render owner-branded mail.

| Tool | What it does |
|---|---|
| `email_template_list()` | List shipped templates with the variables each requires. Read-only. |
| `email_template_render(name, variables)` | Render one template with the given variables; returns `{"status": "ok", "template", "subject", "html", "txt", "variables", "unused"}` or an error naming the missing variables / leftover placeholders. |

Example:

```python
email_template_list()
# {"status": "ok", "templates": [{"name": "invite-tester",
#   "variables": ["recipient_name", "recipient_email", ...], ...}]}

email_template_render("invite-tester", {
    "recipient_name": "Ada Tester",
    "recipient_email": "tester@example.com",
    "tester_folder_url": "https://drive.google.com/...",
    "roll_call_url": "https://docs.google.com/...",
    "guest_pack_01_url": "https://docs.google.com/...",
    "guest_pack_02_url": "https://docs.google.com/...",
    "guest_pack_03_url": "https://docs.google.com/...",
    "guest_pack_04_url": "https://docs.google.com/...",
    "guest_pack_05_url": "https://docs.google.com/...",
    "subject": "You're in. Welcome to Hotel Visions.",
    "preheader": "Your Tester folder is open — here is your first step.",
    "business_address": "123 Example Street, Anytown, ST 12345",
    "sender_name": "Mister Who",
    "sender_email": "whovisions@muse.ai",
})
```

## Variables — all 14 are required

| Variable | What it is |
|---|---|
| `{{recipient_name}}` | Tester's display name, e.g. `Ada Tester` |
| `{{recipient_email}}` | Tester's email address (the To: address) |
| `{{tester_folder_url}}` | Google Drive URL of the Nougen Tester folder (editor) |
| `{{roll_call_url}}` | Google Sheets URL of the roll call sheet (Sign-in tab) |
| `{{guest_pack_01_url}}` | Guest Pack 01 — How the House Works (Google Doc) |
| `{{guest_pack_02_url}}` | Guest Pack 02 — The Keymaker (Atibon) (Google Doc) |
| `{{guest_pack_03_url}}` | Guest Pack 03 — Shards, SheetShards, Relays, and Memory (Google Doc) |
| `{{guest_pack_04_url}}` | Guest Pack 04 — The Research Tools (Google Doc) |
| `{{guest_pack_05_url}}` | Guest Pack 05 — Fresh Findings (Google Doc) |
| `{{subject}}` | Email subject line, e.g. `You're in. Welcome to Hotel Visions.` |
| `{{preheader}}` | Hidden preview text (extends the subject, doesn't repeat it) |
| `{{business_address}}` | **Postal address for the footer — see the rule below** |
| `{{sender_name}}` | Sender's display name, e.g. `Mister Who` |
| `{{sender_email}}` | Sender's email address, e.g. `whovisions@muse.ai` |

Notes:

- `{{recipient_name}}` / `{{recipient_email}}` have no counterpart in
  the sent email (it never greets the tester by name), so they live as
  addressing metadata, not body copy: an HTML comment in `<head>` and
  a `To:` line at the top of the `.txt` header block. The visible email
  is identical either way.
- The sent email had no postal address in its footer, so
  `{{business_address}}` was added as a footer line directly under the
  "Who Visions LLC" line (same footer styling in HTML; its own line in
  the `.txt` footer).

## Compliance rules — do not skip

These come from the premium-email research
(`~/workspace/research_notes/premium-email-marketing-20261122-2102/report.md`,
section 6, footer checklist). The render tools enforce the ones they
can; the rest live at send time, which is why sending is not a fleet
tool.

- **`{{business_address}}` REQUIRED before any send.** A valid physical
  postal address in the footer is a CAN-SPAM requirement. **Never send
  an invite with the literal `{{business_address}}` text in the footer,
  and never invent an address.** No postal address has been supplied
  for Who Visions LLC — get a real one (street / P.O. box / registered
  mail receiving agency) and put it in the vars as `business_address`
  before any send. The renderer deliberately has no default for it.
  Passing the literal string `"{{business_address}}"` as the value
  renders the slot visibly — that is the verification case, proving
  the slot exists without inventing an address. It is not a sendable
  render.
- **List-Unsubscribe at send time.** The sending path must add
  `List-Unsubscribe` + `List-Unsubscribe-Post: List-Unsubscribe=One-Click`
  headers (RFC 8058) — required for bulk senders since June 2024. The
  template body already carries the visible unsubscribe line ("reply
  with the word unsubscribe", no login needed). Headers are invisible
  and cannot live in a template; the mail worker adds them.
- **Plain-text multipart always.** Every send is multipart/alternative
  with the `.txt` part matching the HTML content, text part first.
  HTML-only mail is mildly suspicious to filters and unreadable in
  text-only clients. The render tools always return both parts
  together; never send one without the other.
- **Sender authentication at send time.** SPF + DKIM + DMARC (at least
  `p=none`) on the sending domain, From-domain aligned; send from the
  custom domain, never a free Gmail/Yahoo address. That is the mail
  worker's configuration, not a template concern — but a render is not
  a sendable email until the sending path has it.
- **Honour opt-outs promptly.** CAN-SPAM allows 10 business days;
  Gmail/Yahoo bulk-sender rules require 48 hours. The reply-to path in
  the template ("just reply to this email") is a monitored inbox.

## Send flow — render here, SEND stays with the mail worker

1. A fleet lane (or the operator) calls `email_template_render` with
   all 14 variables, including a **real** `business_address`.
2. The lane hands the rendered HTML + plain-text parts to the mail
   worker (Gmail / Muse Mail) — as text, in chat, the way any draft is
   handed over.
3. The mail worker sends under **per-action approval** from the
   operator: the operator sees the rendered email and approves that
   specific send, to that specific recipient. The mail worker adds the
   `List-Unsubscribe` headers and the multipart structure, and checks
   the footer address is real before sending.
4. The send is recorded (recipient, template, subject, time) the same
   way any sent mail is — the fleet tools do not log sends because they
   never send.

**Why sending is not a fleet tool.** A fleet tool that could send mail
would bypass per-action approval: any lane, on any trigger, could put
mail in someone's inbox in the owner's name, with no operator seeing
it first. It would also bypass the compliance checks that only exist
at send time (real footer address, unsubscribe headers, authenticated
sending domain) — a render cannot verify those, so a send tool would
either silently send non-compliant mail or duplicate the mail worker's
job badly. One server, one approval path: rendering is a pure function
and safe to expose; sending is an irreversible outward action and stays
where the approval lives. This mirrors the house rule for the other
irreversible tools (`shards_forget`, `vault_put`, `dav1d_exec`,
`cf_deploy_worker` are ask-first, every time).

## Voice rules

- **Public name is "Unk".** The template's social-proof line names
  "Unk, Claude, WhoArt, Duet, Nou, and Jeannie" — the public-facing
  name for the phoebus Muse. The private name never appears in
  public-facing copy. Do not "correct" it to the private name.
- **No "the operator is the landlord" line.** The template never says the operator is
  the landlord, and neither should any new template copy. The footer
  signs "Mister Who, superintendent of Hotel Visions, for the operator" — that
  is the whole of the framing.
- **Front desk, not help desk.** The help block is "Just reply to this
  email — Mister Who reads every reply." Replies are a deliverability
  signal as well as a help path; keep the reply-to monitored.

## Brand

- **Neon green `#39FF14`** is the accent (header eyebrow, key motif,
  primary CTA fill); links on light are dark green `#0b6e1f` for
  contrast. Dark-mode rules in the template switch to near-black /
  near-white greys — no pure black or pure white anywhere.
- **Company: "Who Visions LLC".** The footer and copyright line use
  exactly that (confirmed by the operator, 2026-11-22).
- One column, 600 px, centred, ≥24 px padding; single primary CTA
  above the fold ("Open my Tester folder", first person); the
  five-step checklist follows the CTA, then the Guest Pack, social
  proof, help, and a quiet secondary CTA. This shape follows the
  premium-email research (anatomy, section 3 of the report): envelope
  → header → hero + one CTA → welcome → first step → social proof →
  help → footer.

## Errors

| Signal | Meaning | What to do |
|---|---|---|
| `missing variable(s) ...` | A required variable was not supplied. | Supply every variable in the table above. `business_address` is required, not optional — supply a real address for a send, or the literal placeholder for a verification render. |
| `unreplaced placeholder(s) left in output` | A value contained a `{{...}}` that is not a variable, or a template edit introduced one. | Fix the value (or the template); never send with a leftover placeholder. |
| `template ... is incomplete or unknown` | No such template pair ships. | Call `email_template_list()` for the shipped names. |
| `every variable value must be a string` | A value was a number, list, or object. | Pass strings only; URLs and addresses are strings. |

## Files

- `src/nougen_shards/email_templates.py` — registry + renderer
  (`list_templates`, `render_template`)
- `src/nougen_shards/email_templates/invite-tester.html` — HTML template
- `src/nougen_shards/email_templates/invite-tester.txt` — plain-text template
- `src/nougen_shards/mcp.py` — `email_template_list`,
  `email_template_render`
- `src/nougen_shards/tenant_policy.py` — both labelled `OWNER_ONLY`
- `tests/test_mcp_email_templates.py` — 14 tests
- `docs/email-templates.md` — this file
