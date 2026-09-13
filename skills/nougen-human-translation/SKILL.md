---
name: nougen-human-translation
description: Translates machine-centric technical jargon, system diagnostics, and infrastructure errors into concrete, picture-ready human explanations without loss of underlying truth, error codes, or uncertainty.
---

# 🗣️ NouGen Human Translation Layer

## Core Principle
Expert intelligence stays intact. Expert phrasing does not automatically reach the user. Translate technical/internal language into language a normal human can immediately picture, repeat, and act on. Translation is not simplification or loss of precision.

## Tool Integration
Exposed on NouGenShards node MCP and REST API:
`nougen_translate_response(raw_response: str, mode: str = "human_first", audience: str = "dave", preserve_technical: bool = True) -> dict`

### Modes:
1. **`human_first`** (Default for conversational output): Concrete mental model first, with technical detail attached.
2. **`dual_layer`** (Default for infrastructure telemetry): Structured Human View + Technical Telemetry block.
3. **`technical_first`**: Full technical readout with a human TL;DR at the top.
4. **`concise`**: 1-2 sentence human takeaway.

## Guardrails
- **Preserve Facts**: Never drop HTTP status codes (`502`, `401`, `503`), node names (`blade`, `phoebus`, `whoart`), latencies (`604ms`), or counts.
- **Preserve Uncertainty**: Never translate `unknown` into `broken`, `unreachable` into `down`, or partial coverage into full coverage.
- **Grounding First**: Translation occurs *after* facts and telemetry are retrieved and verified, never before.
