import math
from datetime import date, timedelta

from nougen_shards.rd_acceleration import Generation, assess

T0 = date(2024, 1, 1)


def series(rates, step_days=180, lags=None):
    gens, score, d = [], 1.0, T0
    for i, r in enumerate([0.0] + rates):
        score *= math.exp(r * step_days / 365.25)
        lag = lags[i] if lags else 0.0
        gens.append(Generation(f"m{i}", d, score, lag))
        d += timedelta(days=step_days)
    return gens


def test_doubling_rate_reads_about_2x():
    gens = series([1.0, 1.0, 1.0, 2.0, 2.0, 2.0])
    rep = assess(gens, gens[4].released)
    assert 1.6 < rep.ratio < 2.4
    assert rep.ci_low <= rep.ratio <= rep.ci_high


def test_steady_trend_is_not_acceleration():
    gens = series([1.0] * 6)
    rep = assess(gens, gens[3].released)
    assert abs(rep.ratio - 1.0) < 1e-6
    assert rep.pattern == "bottlenecked"


def test_compounding_detected():
    gens = series([1.0, 1.0, 1.0, 1.5, 2.5, 4.0])
    assert assess(gens, gens[4].released).pattern == "compounding"


def test_reaction_window_shrinks():
    gens = series([1.0] * 4, lags=[30, 60, 120, 200, 0])
    rep = assess(gens, gens[2].released)
    assert rep.reaction_window_shrinking
    assert any("after the next generation" in n for n in rep.notes)


def test_too_few_points():
    gens = series([1.0, 1.0])
    assert assess(gens, gens[2].released).pattern == "insufficient"
