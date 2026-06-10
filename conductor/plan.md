# NouGenShards Landing Page Implementation Plan

## Objective
Create a modern, dark-themed, conversion-focused landing page for NouGenShards using the provided copy. The page will embody the "NouGenAi" brand identity with a high-end, developer-focused aesthetic.

## Architecture & Tech Stack
- **Framework**: HTML5, Vanilla CSS3, and minimal Vanilla JS for interactions. This ensures maximum speed, minimal overhead, and adheres to the vanilla CSS preference for visually impactful prototypes.
- **Styling**: Vanilla CSS with CSS Variables for theme management. 
- **Aesthetic**: Deep dark backgrounds (`#0a0a0c`), crisp typography (sans-serif like Inter or system fonts), subtle glowing accents (glassmorphism/neon borders for "shards"), and high-contrast primary CTA buttons.

## Page Structure & Copy Mapping

1. **Header / Hero Section**
   - **Microline (Eyebrow)**: "Deep grep. Retrieve. Recall. Repeat."
   - **Title**: NouGenShards
   - **Subhead**: "Persistent local memory for coding agents. Stop paying for expensive amnesia. Store machine experience as shards, retrieve the right few at the right time, and ship faster without blowing up the product."
   - **CTAs**: 
     - Primary (Solid Button): "See the Workflow"
     - Secondary (Ghost/Outline Button): "Install the Shard Layer"

2. **Features / Value Bullets (Grid Layout)**
   - Displayed as a responsive grid of "shard" cards.
   - SQLite + WAL: fast, local, durable storage (offline-first).
   - FTS5 + BM25: deep grep + ranked recall that’s explainable.
   - Hybrid retrieval: lexical + semantic candidates, merged and deduped.
   - Reranking: promote what worked, demote what broke, honor scope.
   - Vector search: semantic recall when the words don’t match.
   - Graph memory: link fixes ↔ files ↔ commands ↔ decisions.
   - Cache: stop reprocessing repeated work; reuse verified answers.
   - MCP: tool bridge (files, git, tests, builds) with control.

3. **How It Works (Process Steps)**
   - A visual 4-step timeline or stacked list.
   - 1) Capture agent events (decisions, errors, fixes, commands, outcomes).
   - 2) Store them as NouGen Shards (persistent units of machine experience).
   - 3) Retrieve + rank (FTS5/BM25 + hybrid + rerank + graph).
   - 4) Return a Recall Packet the agent can act on, then write back the result.

4. **Metrics / Impact Block**
   - Emphasized as large, trustworthy statistics or bold claims.
   - Higher hit-rate recall (the right shard, not a long prompt)
   - Fewer repeated fixes (cache + confirmation loops)
   - Less token waste (compact recall packets; no re-learning the repo)

5. **Footer / Closing**
   - **Closing Line**: "Your agents have prompts. Mine have shards." (Large, impactful typography).

## Implementation Steps
1. Create `site/index.html` with the semantic HTML structure.
2. Create `site/styles.css` implementing the NouGenAi dark theme, responsive grids, and subtle animations (e.g., hover effects on the shard cards).
3. Extract `nougenshards-site.zip` if it is a template to use for this project (will request execution permission).
4. Verify the layout on mobile and desktop viewports.

## Verification
- Ensure all provided copy is present exactly as requested.
- Verify the site is visually impactful and aligns with the NouGenAi brand guidelines (dark, premium, developer-focused).
- Test responsive behavior.