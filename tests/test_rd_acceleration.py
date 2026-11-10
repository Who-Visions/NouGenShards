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


def test_jsonl_and_ledger_loaders(tmp_path):
    import json, sqlite3
    from nougen_shards.rd_acceleration import from_evaluation_ledger, load_jsonl
    from nougen_shards.rsi_evaluation_ledger import EvaluationLedger

    p = tmp_path / "g.jsonl"
    p.write_text("\n".join(json.dumps({"name": g.name, "released": g.released.isoformat(),
                                       "score": g.score}) for g in series([1.0] * 3)))
    assert [g.name for g in load_jsonl(p)] == ["m0", "m1", "m2", "m3"]

    db = tmp_path / "ledger.db"
    EvaluationLedger(db)  # creates the real schema
    con = sqlite3.connect(db)
    con.execute("INSERT INTO epochs VALUES ('e1','ev','ds',10)")
    rows = [("r1", "aaa", 1, "2026-01-01"), ("r2", "bbb", 0, "2026-02-01"),
            ("r3", "ccc", 1, "2026-03-01"), ("r4", "ddd", 1, "2026-03-01 09:00:00")]
    for rid, c, d, ts in rows:
        con.execute("INSERT INTO receipts VALUES (?, 'e1', 'ctx', ?, 'lin', 'tok', ?, ?)",
                    (rid, c, d, ts))
    con.commit(); con.close()
    gens = from_evaluation_ledger(db)
    assert [(g.released.isoformat(), g.score) for g in gens] == [
        ("2026-01-01", 1.0), ("2026-03-01", 3.0)]


def test_cli_rd_accel(tmp_path, capsys):
    import json
    from nougen_shards import cli
    p = tmp_path / "g.jsonl"
    gens = series([1.0, 1.0, 1.0, 2.0, 2.0, 2.0])
    p.write_text("\n".join(json.dumps({"name": g.name, "released": g.released.isoformat(),
                                       "score": g.score}) for g in gens))
    args = type("A", (), {"jsonl": str(p), "ledger": None, "json": True,
                          "breakpoint": gens[4].released.isoformat()})
    assert cli.cmd_rd_accel(args) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["generations"] == 7 and 1.6 < out["ratio"] < 2.4
