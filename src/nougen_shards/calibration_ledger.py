"""Lane self-model calibration and independence-weighted consensus for RSI.

A lane commits a success forecast before a case is scored; the evaluator then
records the outcome. Per-lane Brier scores measure whether a lane knows its own
competence, and a promotion check refuses harness changes that buy accuracy by
degrading calibration. The same outcomes give consensus weights: reliability
(1 - Brier) times independence (how rarely a lane fails alongside its peers), so
correlated routes stop counting as independent votes.

Keep this database with the evaluator, outside candidate sandboxes.
"""

from __future__ import annotations

import math
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Mapping


class ForecastLocked(RuntimeError):
    """A forecast already exists, or the case was already resolved."""


@dataclass(frozen=True)
class LaneCalibration:
    lane: str
    n: int
    brier: float


class CalibrationLedger:
    """Trusted evaluator API. Forecasts are write-once and must precede outcomes."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS forecasts (
                    lane TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    family TEXT NOT NULL,
                    harness TEXT NOT NULL,
                    p REAL NOT NULL CHECK (p >= 0 AND p <= 1),
                    outcome INTEGER CHECK (outcome IN (0, 1)),
                    forecast_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    resolved_at TEXT,
                    PRIMARY KEY (lane, case_id, harness)
                );
                CREATE INDEX IF NOT EXISTS forecast_case ON forecasts(case_id, harness);
                """
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        try:
            yield db
        finally:
            db.close()

    def forecast(
        self, lane: str, case_id: str, p: float, *, family: str = "default", harness: str = "base"
    ) -> None:
        if not all(isinstance(v, str) and v.strip() for v in (lane, case_id, family, harness)):
            raise ValueError("lane, case_id, family and harness must be nonempty strings")
        if not (isinstance(p, (int, float)) and math.isfinite(p) and 0.0 <= p <= 1.0):
            raise ValueError("p must be a probability in [0, 1]")
        with self._connect() as db:
            try:
                db.execute(
                    "INSERT INTO forecasts (lane, case_id, family, harness, p) VALUES (?, ?, ?, ?, ?)",
                    (lane, case_id, family, harness, float(p)),
                )
            except sqlite3.IntegrityError as exc:
                raise ForecastLocked(f"{lane}/{case_id}/{harness} already forecast") from exc

    def resolve(self, case_id: str, outcomes: Mapping[str, bool], *, harness: str = "base") -> int:
        """Record outcomes per lane. Lanes without a prior forecast are ignored."""
        resolved = 0
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                for lane, ok in outcomes.items():
                    cur = db.execute(
                        "UPDATE forecasts SET outcome = ?, resolved_at = CURRENT_TIMESTAMP "
                        "WHERE lane = ? AND case_id = ? AND harness = ? AND outcome IS NULL",
                        (1 if ok else 0, lane, case_id, harness),
                    )
                    resolved += cur.rowcount
                db.commit()
            except BaseException:
                db.rollback()
                raise
        return resolved

    def calibration(self, *, harness: str = "base", family: str | None = None) -> dict[str, LaneCalibration]:
        sql = (
            "SELECT lane, COUNT(*), AVG((p - outcome) * (p - outcome)) FROM forecasts "
            "WHERE outcome IS NOT NULL AND harness = ?"
        )
        args: list = [harness]
        if family is not None:
            sql += " AND family = ?"
            args.append(family)
        with self._connect() as db:
            rows = db.execute(sql + " GROUP BY lane", args).fetchall()
        return {lane: LaneCalibration(lane, n, brier) for lane, n, brier in rows}

    def promotion_ok(
        self, baseline: str, candidate: str, *, epsilon: float = 0.02, min_n: int = 30
    ) -> tuple[bool, dict[str, float]]:
        """Refuse a harness whose calibration worsens beyond epsilon on any lane.

        Lanes with fewer than min_n resolved cases under either harness are not
        judged; if no lane qualifies the check fails closed.
        """
        base = self.calibration(harness=baseline)
        cand = self.calibration(harness=candidate)
        deltas = {
            lane: cand[lane].brier - base[lane].brier
            for lane in base.keys() & cand.keys()
            if base[lane].n >= min_n and cand[lane].n >= min_n
        }
        if not deltas:
            return False, {}
        return all(d <= epsilon for d in deltas.values()), deltas

    def weights(self, *, harness: str = "base", min_n: int = 10) -> dict[str, float]:
        """Consensus weight per lane: (1 - Brier) * independence.

        Independence = 1 - mean over peers of P(peer wrong | lane wrong), using
        shared resolved cases. A lane that never fails alone gets no credit for
        agreeing; a lane with no shared failures is treated as fully independent.
        """
        cal = self.calibration(harness=harness)
        with self._connect() as db:
            rows = db.execute(
                "SELECT lane, case_id, outcome FROM forecasts WHERE outcome IS NOT NULL AND harness = ?",
                (harness,),
            ).fetchall()
        by_case: dict[str, dict[str, int]] = {}
        for lane, case_id, outcome in rows:
            by_case.setdefault(case_id, {})[lane] = outcome
        out: dict[str, float] = {}
        for lane, c in cal.items():
            if c.n < min_n:
                continue
            co_rates = []
            for peer in cal:
                if peer == lane:
                    continue
                fails = [v for v in by_case.values() if v.get(lane) == 0 and peer in v]
                if fails:
                    co_rates.append(sum(1 for v in fails if v[peer] == 0) / len(fails))
            independence = 1.0 - (sum(co_rates) / len(co_rates) if co_rates else 0.0)
            out[lane] = max(0.0, 1.0 - c.brier) * independence
        return out


def effective_lanes(ledger: CalibrationLedger, *, harness: str = "base", min_shared: int = 10) -> tuple[float, float]:
    """Kish-style effective lane count n_eff = n / (1 + (n - 1) * rho_bar).

    rho_bar is the mean pairwise phi correlation of lane outcomes over cases both
    lanes resolved (pairs with fewer than min_shared cases, or a constant
    outcome, are skipped). Negative correlation is floored at 0 so disagreement
    never inflates n_eff past n. Returns (n_eff, rho_bar); (0.0, 0.0) if no lanes.
    """
    with ledger._connect() as db:
        rows = db.execute(
            "SELECT lane, case_id, outcome FROM forecasts WHERE outcome IS NOT NULL AND harness = ?",
            (harness,),
        ).fetchall()
    by_lane: dict[str, dict[str, int]] = {}
    for lane, case_id, outcome in rows:
        by_lane.setdefault(lane, {})[case_id] = outcome
    lanes = sorted(by_lane)
    n = len(lanes)
    if n == 0:
        return 0.0, 0.0
    rhos = []
    for i, a in enumerate(lanes):
        for b in lanes[i + 1:]:
            shared = by_lane[a].keys() & by_lane[b].keys()
            if len(shared) < min_shared:
                continue
            xs = [by_lane[a][c] for c in shared]
            ys = [by_lane[b][c] for c in shared]
            mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
            vx = sum((x - mx) ** 2 for x in xs)
            vy = sum((y - my) ** 2 for y in ys)
            if vx == 0 or vy == 0:
                continue
            cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
            rhos.append(max(0.0, cov / math.sqrt(vx * vy)))
    rho = sum(rhos) / len(rhos) if rhos else 0.0
    return n / (1 + (n - 1) * rho), rho


def weighted_consensus(votes: Mapping[str, float], weights: Mapping[str, float]) -> float:
    """Noisy-OR confidence C = 1 - prod_i (1 - p_i) ** w_i.

    votes maps lane -> that lane's probability the claim is true. Lanes absent
    from weights contribute nothing, so unknown or correlated routes cannot
    inflate confidence by sheer count.
    """
    log_miss = 0.0
    for lane, p in votes.items():
        w = weights.get(lane, 0.0)
        if w <= 0:
            continue
        p = min(max(float(p), 0.0), 1.0)
        if p >= 1.0:
            return 1.0
        log_miss += w * math.log1p(-p)
    return 1.0 - math.exp(log_miss)
