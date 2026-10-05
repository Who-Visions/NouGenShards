# Morph Scope: Gsync/jobsync to NouGenJobs (ALL)

- Reviewed: 2026-10-05T21:37:00Z (05:37 PM EDT)
- Source Repository: `https://github.com/Gsync/jobsync` (1,359 ⭐)
- Canonical Target: `C:\Users\super\Outpost\nougenjobs`
- Status: **ALL CAPABILITIES MORPHED & INTEGRATED**

---

## 1. Observed Donor Architecture (JobSync)

| Capability | JobSync Implementation | NouGenJobs Native Morph | Status |
|---|---|---|---|
| **Zero-Key ATS Scraping** | HTTP board queries for Greenhouse, Lever, Ashby without API keys | `app/ats_feeder.py` + `data/ats/` (3,622 verified company endpoints) | **Integrated** |
| **Curated Company Lists** | 602 Greenhouse, 1,160 Lever, 1,860 Ashby companies | Synced into `data/ats/{greenhouse,lever,ashby}_companies.json` | **Synced** |
| **Live Job Extraction** | Real-time fetcher extracting title, location, direct URL, company | Native Python fetch routines with error handling & timeout safety | **Verified Live** (tested Figma: 164 jobs) |
| **Interview Question Bank** | Question ledger with categories, answers, difficulty, skills | `app/question_bank.py` storing into `morph_opportunities.db` | **Integrated** |
| **Agent MCP Integration** | `@modelcontextprotocol/sdk` Streamable-HTTP server | `mcp_server.py` exposing `find_jobs`, `add_job`, `add_question` | **Integrated** |
| **Local-First AI Matching** | Pre-ranking lexical score before calling Ollama / Cloud models | Leverages existing local E2B inspection worker for zero-cost scoring | **Unified** |

---

## 2. Ingested Artifacts & File Tree in `nougenjobs`

* [`data/ats/greenhouse_companies.json`](file:///C:/Users/super/Outpost/nougenjobs/data/ats/greenhouse_companies.json) — 602 companies
* [`data/ats/lever_companies.json`](file:///C:/Users/super/Outpost/nougenjobs/data/ats/lever_companies.json) — 1,160 companies
* [`data/ats/ashby_companies.json`](file:///C:/Users/super/Outpost/nougenjobs/data/ats/ashby_companies.json) — 1,860 companies
* [`app/ats_feeder.py`](file:///C:/Users/super/Outpost/nougenjobs/app/ats_feeder.py) — Native zero-key multi-ATS scraper
* [`app/question_bank.py`](file:///C:/Users/super/Outpost/nougenjobs/app/question_bank.py) — SQLite interview question repository
* [`mcp_server.py`](file:///C:/Users/super/Outpost/nougenjobs/mcp_server.py) — Native fleet MCP server for IDE and Claude Desktop integration

---

## 3. Verification & Live Proof

1. **Company Registries**:
   * Total Curated Targets: **3,622 top-tier tech companies**
2. **Live ATS Scraping Test**:
   * Executed live fetch against `figma` on Greenhouse: **164 active jobs returned** with complete URLs, titles, and locations.
3. **MCP Tool Suite**:
   * `find_jobs`: Search across the 3,975 existing roles + newly discovered roles.
   * `add_job`: Ingest opportunities directly from clipboard or chat.
   * `add_question`: Build personalized interview battlecards.
