---
name: nougentube-morph
description: "NougenMorph: Extracts actionable patterns, tools, skills, and architectural DNA from NougenTube video digests. Takes a YouTube video transcript + metadata, identifies reusable technical patterns, generates skill scaffolds, and folds knowledge back into The Observatory's NouGen substrate. The recursive self-improvement engine for video-sourced intelligence."
risk: low
source: "observatory-fleet (The Observatory)"
date_added: "2026-09-28"
---

# NougenMorph

## 1. What is NougenMorph?
- **The recursive loop**: Watch → Digest → Extract → Build → Shard
- Every YouTube video contains extractable DNA: stack patterns, workflow patterns, creative techniques, architectural decisions.
- NougenMorph automates the extraction and skill generation.

## 2. The Morph Pipeline

### Step 1: CAPTURE
*Already handled by `nougen tube <url>`.*
- Downloads transcript, metadata, chapter index.
- Shards the digest to NouGen substrate.

### Step 2: ANALYZE (The Morph)
- Read the transcript and metadata.
- Identify extractable patterns in these categories:
  - 🛠️ **Stack Patterns**: Technology combinations (e.g., Vite + GSAP + Lenis)
  - 🔄 **Workflow Patterns**: Process flows (e.g., plan → execute → review)
  - 🎨 **Creative Techniques**: Design/animation/UX tricks
  - 🏗️ **Architecture Decisions**: System design choices with rationale
  - 💡 **Tool Discoveries**: New tools, MCP servers, CLI commands
  - 📊 **Benchmarks**: Performance data, cost comparisons, model evaluations

### Step 3: GENERATE (Skill Scaffolding)
For each identified pattern, determine if it warrants:
- A new skill (if pattern is reusable and complex enough)
- A shard update (if it's a data point or benchmark)
- A tool/script (if it's an automatable process)
- A skill enhancement (if it extends an existing skill)
- Generate SKILL.md scaffolds with proper frontmatter.
- Place in the correct category directory.

### Step 4: FOLD (Recurse)
- Shard all generated artifacts to NouGen.
- Update relevant skill indices.
- Log the morph to the Observatory.

## 3. Analysis Prompt Template

When an agent performs the morph, they should use this prompt to extract the data:

```text
Given this video transcript and metadata:
- Title: {title}
- Channel: {channel}
- Duration: {duration}
- Chapters: {chapters}

Extract all actionable patterns:
1. What technology stacks are demonstrated? (exact packages + versions)
2. What workflow patterns are shown? (step-by-step processes)
3. What creative techniques are used? (design, animation, UX)
4. What architectural decisions are made? (and their rationale)
5. What tools/services are mentioned? (MCP servers, CLIs, platforms)
6. What benchmarks or performance data is shared?
7. What can be turned into a reusable Observatory skill?
```

## 4. Skill Placement Rules

| Pattern Type | Skill Category | Example |
|---|---|---|
| Frontend stack | `05-web-frontend/` | gsap-scroll-video-website |
| Backend stack | `04-development/` | php-lead-capture |
| Workflow pattern | `13-automation/` | plan-execute-autonomous |
| Creative technique | `05-web-frontend/` or `14-specialized/` | gradient-thematic-animation |
| Architecture | `03-architecture/` | mcp-connector-deployment |
| AI/ML pattern | `01-ai-ml/` | model-benchmark-comparison |
| Fleet/Meta | `99-fleet-custom/` | nougentube-morph |

## 5. Usage

```bash
# Step 1: Capture (already exists)
nougen tube "https://youtube.com/watch?v=XXXXX"

# Step 2-4: Morph (tell the agent)
# "Nougentube morph [url or video ID]" — triggers this skill
```

Or manually via the companion script:
```bash
python3 "/Users/kushboygroup/The Observatory/.agents/skills/99-fleet-custom/nougentube-morph/scripts/morph_analyze.py" --transcript /tmp/nougentube/<id>_transcript.txt --info /tmp/nougentube/<id>.info.json
```
