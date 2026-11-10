import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nougen_shards.assumption_check import gate_report, scan_source  # noqa: E402


def test_clean_source_has_no_findings():
    receipt = scan_source("total = sum(values)\nmean = total / len(values)\n")
    assert receipt.clean
    assert "clean" in receipt.render()


def test_fillna_zero_is_flagged_with_line_number():
    receipt = scan_source("import pandas as pd\ndf['rate'] = df['rate'].fillna(0)\n")
    assert not receipt.clean
    assert receipt.findings[0].line == 2
    assert "zero" in receipt.findings[0].reason


def test_dict_get_default_zero_is_flagged():
    receipt = scan_source("price = prices.get(ticker, 0)\n")
    assert not receipt.clean


def test_dropna_is_flagged():
    assert not scan_source("clean = df.dropna()\n").clean


def test_nan_to_num_is_flagged():
    assert not scan_source("x = np.nan_to_num(x)\n").clean


def test_each_line_reports_once_even_if_several_patterns_match():
    receipt = scan_source("v = d.get(k, 0).fillna(0)\n")
    assert len(receipt.findings) == 1


def test_gate_raises_on_findings_unless_allowed():
    src = "y = x.fillna(0)\n"
    with pytest.raises(ValueError):
        gate_report(src)
    assert not gate_report(src, allow_findings=True).clean


def test_gate_passes_clean_source():
    assert gate_report("y = x + 1\n").clean


def test_multiline_swallowed_exception_is_caught():
    from nougen_shards.assumption_check import scan_source

    assert not scan_source("try:\n    x()\nexcept Exception:\n    return 0\n").clean
    assert scan_source("try:\n    x()\nexcept Exception:\n    raise\n").clean
