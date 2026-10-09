"""Deterministic attacks against the resilience reference primitives."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest

from resilience_core import (
    BudgetExceeded, Busy, Conflict, Indeterminate, Journal, Provider,
    StaleOwner, Witness, choose_provider, digest, promotion_gate,
)


class JournalAttacks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.now = 100.0
        self.path = Path(self.tmp.name) / "journal.db"
        self.journal = Journal(self.path, clock=lambda: self.now)
        self.payload = digest({"tenant": "A", "operation": "write", "input": 1})

    def test_restart_replays_commit_without_redispatch(self):
        ticket = self.journal.prepare("key", self.payload, "worker-A")
        self.journal.dispatch(ticket)
        self.journal.complete(ticket, digest("receipt"))
        restarted = Journal(self.path)
        replay = restarted.prepare("key", self.payload, "worker-B")
        self.assertEqual(replay.replay_receipt, digest("receipt"))
        with self.assertRaises(StaleOwner):
            restarted.dispatch(replay)

    def test_payload_change_cannot_reuse_idempotency_key(self):
        self.journal.prepare("key", self.payload, "worker-A")
        with self.assertRaises(Conflict):
            self.journal.prepare("key", digest("changed"), "worker-A")

    def test_live_lease_rejects_competing_worker(self):
        self.journal.prepare("key", self.payload, "worker-A")
        with self.assertRaises(Busy):
            self.journal.prepare("key", self.payload, "worker-B")

    def test_expired_prepared_lease_fences_stale_worker(self):
        old = self.journal.prepare("key", self.payload, "worker-A", lease_seconds=1)
        self.now += 2
        new = self.journal.prepare("key", self.payload, "worker-B")
        self.assertEqual(new.epoch, old.epoch + 1)
        with self.assertRaises(StaleOwner):
            self.journal.dispatch(old)
        self.journal.dispatch(new)

    def test_crash_after_dispatch_never_triggers_blind_retry(self):
        ticket = self.journal.prepare("key", self.payload, "worker-A")
        self.journal.dispatch(ticket)
        self.now += 1000
        with self.assertRaises(Indeterminate):
            self.journal.prepare("key", self.payload, "worker-B")

    def test_abrupt_process_exit_preserves_dispatched_intent(self):
        script = (
            "import os,sys; from resilience_core import Journal; "
            "j=Journal(sys.argv[1]); t=j.prepare('key',sys.argv[2],'child'); "
            "j.dispatch(t); os._exit(17)"
        )
        result = subprocess.run([sys.executable, "-c", script, str(self.path), self.payload],
                                cwd=Path(__file__).parent, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 17)
        with self.assertRaises(Indeterminate):
            Journal(self.path).prepare("key", self.payload, "restarted-worker")

    def test_reconciliation_fences_original_completion(self):
        ticket = self.journal.prepare("key", self.payload, "worker-A")
        self.journal.dispatch(ticket)
        self.journal.reconcile("key", self.payload, digest("backend-confirmed"))
        with self.assertRaises(StaleOwner):
            self.journal.complete(ticket, digest("late"))

    def test_competing_reservations_cannot_exceed_parent_budget(self):
        self.journal.budget("parent", 3)
        def reserve(i):
            try:
                self.journal.reserve_budget("parent", str(i), 1)
                return 1
            except BudgetExceeded:
                return 0
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(reserve, range(12))), 3)

    def test_crashed_reservation_stays_spent_and_duplicates_replay(self):
        self.journal.budget("parent", 1)
        self.assertTrue(self.journal.reserve_budget("parent", "attempt-1", 1))
        restarted = Journal(self.path)
        self.assertFalse(restarted.reserve_budget("parent", "attempt-1", 1))
        with self.assertRaises(BudgetExceeded):
            restarted.reserve_budget("parent", "attempt-2", 1)

    def test_budget_configuration_and_identity_are_immutable(self):
        self.journal.budget("parent", 2)
        self.journal.reserve_budget("parent", "attempt", 1)
        with self.assertRaises(Conflict):
            self.journal.budget("parent", 3)
        with self.assertRaises(Conflict):
            self.journal.reserve_budget("parent", "attempt", 2)


class RoutingAttacks(unittest.TestCase):
    def test_local_failure_cannot_leak_to_cloud(self):
        providers = [Provider("local", True, frozenset({"tools"}), 0, False),
                     Provider("cloud", False, frozenset({"tools"}), 0)]
        with self.assertRaises(Conflict):
            choose_provider(providers, local_only=True, capabilities={"tools"}, max_cost_units=0)

    def test_capability_and_budget_filters_precede_cost(self):
        providers = [Provider("cheap-incompatible", True, frozenset(), 0),
                     Provider("working", True, frozenset({"tools"}), 2)]
        result = choose_provider(providers, local_only=False, capabilities={"tools"}, max_cost_units=2)
        self.assertEqual(result.name, "working")


class PromotionAttacks(unittest.TestCase):
    def setUp(self):
        self.bindings = {key: digest(key) for key in
                         ("reference", "candidate", "workload", "environment", "policy", "evaluator")}
        self.witnesses = [Witness("formal", "kernel", "VERIFIED", digest(self.bindings), digest("proof"), "valid"),
                          Witness("heldout", "sealed-evaluator", "VERIFIED", digest(self.bindings), digest("eval"), "valid")]

    def gate(self, **changes):
        options = dict(bindings=self.bindings, witnesses=self.witnesses,
                       required_families={"formal", "heldout"}, min_groups=2,
                       critical_violation=False, verifier=lambda w: w.signature == "valid",
                       resource_bounds={"latency": (-0.2, -0.1), "memory": (-0.03, 0)})
        options.update(changes)
        return promotion_gate(**options)

    def test_authenticated_independent_evidence_and_bounded_gain(self):
        self.assertEqual(self.gate(), "IMPROVED")

    def test_critical_failure_overrides_missing_evidence(self):
        self.assertEqual(self.gate(critical_violation=True, witnesses=[]), "REGRESSED")

    def test_forged_or_wrong_candidate_witness_cannot_promote(self):
        bad = Witness("formal", "kernel", "VERIFIED", digest("wrong"), digest("proof"), "valid")
        self.assertEqual(self.gate(witnesses=[bad]), "INDETERMINATE")
        self.assertEqual(self.gate(verifier=lambda w: False), "INDETERMINATE")
        self.assertEqual(self.gate(verifier=lambda w: "false"), "INDETERMINATE")

    def test_two_families_from_one_producer_are_not_independent(self):
        copies = [Witness(w.family, "same-origin", w.status, w.bindings_hash, w.artifact_hash, w.signature)
                  for w in self.witnesses]
        self.assertEqual(self.gate(witnesses=copies), "INDETERMINATE")

    def test_verified_refutation_overrides_invalid_evidence_in_any_order(self):
        invalid = Witness("formal", "kernel", "VERIFIED", digest("wrong"), digest("bad"), "valid")
        refuted = Witness("heldout", "sealed-evaluator", "REFUTED", digest(self.bindings), digest("counterexample"), "valid")
        for witnesses in ([invalid, refuted], [refuted, invalid]):
            self.assertEqual(self.gate(witnesses=witnesses), "REGRESSED")

    def test_resource_regression_overrides_uncertainty_in_any_order(self):
        uncertain = ("latency", (-0.2, 0.1))
        regressed = ("memory", (0.1, 0.2))
        for metrics in ([uncertain, regressed], [regressed, uncertain]):
            self.assertEqual(self.gate(resource_bounds=dict(metrics)), "REGRESSED")

    def test_resource_tradeoff_is_not_pareto_improvement(self):
        self.assertEqual(self.gate(resource_bounds={"latency": (-0.2, -0.1), "memory": (0.01, 0.04)}), "REGRESSED")

    def test_uncertain_resource_gain_cannot_promote(self):
        self.assertEqual(self.gate(resource_bounds={"latency": (-0.2, 0.02)}), "INDETERMINATE")

    def test_nan_or_empty_evidence_fails_closed(self):
        self.assertEqual(self.gate(resource_bounds={"latency": (float("nan"), 0)}), "INDETERMINATE")
        self.assertEqual(self.gate(required_families=set()), "INDETERMINATE")


if __name__ == "__main__":
    unittest.main()
