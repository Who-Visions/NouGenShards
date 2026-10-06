import pytest

from nougen_shards.claim_state import ClaimLedger, ClaimState, TransitionRefused

S = ClaimState
PR = "https://github.com/Who-Visions/NouGenShards/pull/725"


@pytest.fixture
def ledger(tmp_path):
    return ClaimLedger(tmp_path / "claims.db")


def _climb(ledger, cid, upto, lane="blade"):
    for to in [S.EVIDENCED, S.EXECUTED, S.OBSERVED][: upto]:
        ledger.advance(cid, to, lane=lane, evidence=PR)


def test_full_ladder_with_independent_verifier(ledger):
    cid = ledger.claim("blade", "#725 merged")
    _climb(ledger, cid, 3)
    ledger.advance(cid, S.INDEPENDENTLY_VERIFIED, lane="phoebus", evidence="sha 18ae3f2")
    assert ledger.state(cid) == S.INDEPENDENTLY_VERIFIED
    assert [s.state for s in ledger.history(cid)] == [
        S.CLAIMED, S.EVIDENCED, S.EXECUTED, S.OBSERVED, S.INDEPENDENTLY_VERIFIED
    ]


def test_cannot_skip_rungs(ledger):
    cid = ledger.claim("blade", "x landed")
    with pytest.raises(TransitionRefused):
        ledger.advance(cid, S.EXECUTED, lane="blade", evidence=PR)
    with pytest.raises(TransitionRefused):
        ledger.advance(cid, S.INDEPENDENTLY_VERIFIED, lane="phoebus", evidence=PR)
    assert ledger.state(cid) == S.CLAIMED


def test_evidence_ref_required(ledger):
    cid = ledger.claim("blade", "x landed")
    with pytest.raises(TransitionRefused):
        ledger.advance(cid, S.EVIDENCED, lane="blade", evidence="trust me")


def test_self_verification_refused(ledger):
    cid = ledger.claim("blade", "x landed")
    _climb(ledger, cid, 2)
    ledger.advance(cid, S.OBSERVED, lane="codex", evidence=PR)
    for lane in ("blade", "codex"):
        with pytest.raises(TransitionRefused):
            ledger.advance(cid, S.INDEPENDENTLY_VERIFIED, lane=lane, evidence=PR)


def test_refuted_from_any_rung_is_terminal(ledger):
    cid = ledger.claim("whoart", "#711 landed")
    ledger.advance(cid, S.EVIDENCED, lane="whoart", evidence=PR)
    ledger.advance(cid, S.REFUTED, lane="blade", evidence="Who-Visions/NouGenShards#711 is open")
    with pytest.raises(TransitionRefused):
        ledger.advance(cid, S.EXECUTED, lane="whoart", evidence=PR)
    assert ledger.state(cid) == S.REFUTED


def test_verified_can_still_be_refuted(ledger):
    cid = ledger.claim("blade", "y")
    _climb(ledger, cid, 3)
    ledger.advance(cid, S.INDEPENDENTLY_VERIFIED, lane="phoebus", evidence=PR)
    ledger.advance(cid, S.REFUTED, lane="codex", evidence="sha 3a7f9c2 reverted it")
    assert ledger.state(cid) == S.REFUTED
    assert len(ledger.history(cid)) == 6


def test_unknown_claim(ledger):
    with pytest.raises(KeyError):
        ledger.state("nope")


def test_chain_detects_tampering(ledger):
    import sqlite3
    cid = ledger.claim("blade", "z merged")
    _climb(ledger, cid, 2)
    assert ledger.verify_chain(cid)
    db = sqlite3.connect(ledger.path)
    db.execute("UPDATE steps SET lane = 'phoebus' WHERE claim_id = ? AND seq = 1", (cid,))
    db.commit()
    db.close()
    assert not ledger.verify_chain(cid)
