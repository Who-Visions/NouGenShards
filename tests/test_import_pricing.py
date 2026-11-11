"""Tests for tools/import_pricing.py across Markdoc, HTML, and Markdown matrix formats."""
from __future__ import annotations

import pytest
import tools.import_pricing as ip
import nougen_shards.billing as billing


def test_google_markdoc_handles_escaped_tabs_four_columns_and_schedules():
    doc = """
## Gemini 4 Carbon  {% id=&quot;gemini-4-carbon&quot; %}
*[`gemini-4-carbon`](/docs/models/gemini-4-carbon)*

{% tabs %}
  {% tab title=&quot;Standard&quot; %}
  {% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD
  * Enterprise Tier

  ---

  * Input price
  * Not available
  * $2.00 through November 30, 2026.
  $4.00 starting December 1, 2026.
  * $99.00

  ---

  * Output price (including thinking tokens)
  * Not available
  * $10.00 through November 30, 2026.
  $20.00 starting December 1, 2026.
  * $499.00

  ---

  * Context caching price
  * Not available
  * $0.10 through November 30, 2026.
  $0.20 starting December 1, 2026.
  * $9.90

  ---

  * Grounding with Google Search
  * Not available
  * $14 / 1,000 search queries
  * Included
  {% /table %}
  {% /tab %}
{% /tabs %}
"""
    built = ip.build("google", {"shape": "sections", "tier": "Standard"}, doc, "test")
    assert "gemini-4-carbon" in built["models"]
    m = built["models"]["gemini-4-carbon"]
    assert m["input"] == 2.0
    assert m["output"] == 10.0
    assert m["cache_read"] == 0.1
    assert m["schedule"] == {
        "2026-12-01": {"input": 4.0, "output": 20.0, "cache_read": 0.2},
    }
    assert billing._resolve_scheduled(m, "2026-11-15") == (2.0, 10.0)
    assert billing._resolve_scheduled(m, "2026-12-01") == (4.0, 20.0)


def test_google_markdoc_excludes_stt_tts_and_ambiguous_shapes():
    doc = """
## Gemini 4 Transcribe
*[`gemini-4-transcribe`](/docs/models/gemini-4-transcribe)*

{% tabs %}
  {% tab title="Standard" %}
  {% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD

  ---

  * Input price
  * Free
  * $3.50 or $0.005/min (audio)

  ---

  * Output price
  * Free
  * $21.00 (text)
  {% /table %}
  {% /tab %}
{% /tabs %}

## Gemini 4 TTS
*[`gemini-4-tts`](/docs/models/gemini-4-tts)*

{% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD

  ---

  * Input price
  * Free
  * $0.50 (text)

  ---

  * Output price
  * Free
  * $9.00 (audio)
{% /table %}

## Gemini 4 BatchOnly
*[`gemini-4-batchonly`](/docs/models/gemini-4-batchonly)*

{% tabs %}
  {% tab title="Batch" %}
  {% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD

  ---

  * Input price
  * Free
  * $1.00

  ---

  * Output price
  * Free
  * $5.00
  {% /table %}
  {% /tab %}
{% /tabs %}
"""
    built = ip.build("google", {"shape": "sections", "tier": "Standard"}, doc, "test")
    assert built["models"] == {}


def test_anthropic_html_strips_captions_and_ignores_fast_mode():
    html_page = """
<html><body>
<h2>Model pricing</h2>
<table>
  <tr><th>Model</th><th colspan="2">Base tokens</th><th colspan="3">Prompt caching</th></tr>
  <tr><th>Name</th><th>Input</th><th>Output</th><th>5m writes</th><th>1h writes</th><th>Hits and refreshes</th></tr>
  <tr>
    <td><div><a href="/docs/fable">Claude Fable 5.2</a><span class="text-caption">For demanding reasoning</span></div></td>
    <td>$8 / MTok</td><td>$40 / MTok</td><td>$10 / MTok</td><td>$16 / MTok</td><td>$0.20 / MTok</td>
  </tr>
  <tr>
    <td><div><span>Claude Haiku 5.5 (for prompts up to 100,000 tokens)</span></div></td>
    <td>$0.10 / MTok</td><td>$0.50 / MTok</td><td>$0.125 / MTok</td><td>$0.20 / MTok</td><td>$0.01 / MTok</td>
  </tr>
  <tr>
    <td><div><span>Claude Haiku 5.5 (for prompts over 100,000 tokens)</span></div></td>
    <td>$0.50 / MTok</td><td>$2.50 / MTok</td><td>$0.625 / MTok</td><td>$1 / MTok</td><td>$0.05 / MTok</td>
  </tr>
</table>
<h3>Fast mode pricing</h3>
<table>
  <tr><th>Model</th><th>Input</th><th>Output</th></tr>
  <tr><td>Claude Fable 5.2</td><td>$16 / MTok</td><td>$80 / MTok</td></tr>
</table>
</body></html>
"""
    cfg = ip.DEFAULT_SOURCES["anthropic"]
    built = ip.build("anthropic", cfg, html_page, "test")
    assert "claude-fable-5.2" in built["models"]
    assert built["models"]["claude-fable-5.2"]["input"] == 8.0
    assert built["models"]["claude-fable-5.2"]["output"] == 40.0
    assert built["models"]["claude-fable-5.2"]["cache_read"] == 0.20
    assert "claude-fable-5.2for-demanding-reasoning" not in built["models"]
    assert built["models"]["claude-haiku-5.5"]["input"] == 0.10
    assert built["models"]["claude-haiku-5.5"]["output"] == 0.50


def test_anthropic_markdown_table_supported():
    md_page = """
## Model pricing
| Model | Base input tokens | 5m cache writes | 1h cache writes | Cache hits and refreshes | Output tokens |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Claude Opus 5.5 | $4 / MTok | $5 / MTok | $8 / MTok | $0.20 / MTok | $20 / MTok |
"""
    cfg = ip.DEFAULT_SOURCES["anthropic"]
    built = ip.build("anthropic", cfg, md_page, "test")
    assert built["models"]["claude-opus-5.5"]["input"] == 4.0
    assert built["models"]["claude-opus-5.5"]["output"] == 20.0
    assert built["models"]["claude-opus-5.5"]["cache_read"] == 0.20


def test_shipped_pricing_snapshots_load_in_billing():
    p_nov = billing._load_pricing("2026-11-11")
    p_dec = billing._load_pricing("2026-12-01")
    assert p_nov["gemini-4-carbon"] == pytest.approx((2.0, 10.0))
    assert p_dec["gemini-4-carbon"] == pytest.approx((4.0, 20.0))
    assert p_nov["claude-fable-5.2"] == pytest.approx((8.0, 40.0))
    assert p_nov["claude-haiku-5.5"] == pytest.approx((0.10, 0.50))
