from nougen_shards.consolidate import consolidate

PIZZA = [{"id": "1", "text": "Likes pizza", "status": "candidate"},
         {"id": "2", "text": "Name is Dave", "status": "candidate"}]
LOCKED = [{"id": "L", "text": "Veil is a dark matter sea", "status": "locked"}]


def dec(action, target=None):
    return lambda fact, n: {"action": action, "target_id": target, "reason": "stub"}


def test_mem0_pizza_pasta_add_is_escalated_to_supersede():
    r = consolidate("I had pizza yesterday but I don't like pizza anymore, I like pasta now", PIZZA, dec("ADD"))
    assert r["action"] == "SUPERSEDE" and r["supersedes"] == "1"
    assert "add_despite_retraction_cue" in r["guards"]


def test_plain_add_stays_add():
    r = consolidate("Likes building automations", PIZZA, dec("ADD"))
    assert r["action"] == "ADD" and r["supersedes"] is None


def test_hallucinated_target_goes_to_review_not_supersede():
    r = consolidate("Likes pasta now", PIZZA, dec("SUPERSEDE", "999"))
    assert r["action"] == "REVIEW" and r["supersedes"] is None


def test_none_with_retraction_cue_is_not_a_duplicate():
    r = consolidate("No longer likes pizza", PIZZA, dec("NONE"))
    assert r["action"] == "REVIEW"


def test_locked_neighbour_yields_conflict_never_supersede():
    r = consolidate("The Veil is no longer dark matter", LOCKED, dec("SUPERSEDE", "L"))
    assert r["action"] == "CONFLICT" and r["supersedes"] is None


def test_locked_can_supersede_locked():
    r = consolidate("Veil is not dark matter", LOCKED, dec("SUPERSEDE", "L"), new_status="locked")
    assert r["action"] == "SUPERSEDE" and r["supersedes"] == "L"


def test_dead_decider_never_drops_the_fact():
    def boom(fact, n):
        raise RuntimeError("ollama down")
    r = consolidate("Likes sushi", PIZZA, boom)
    assert r["action"] == "ADD" and "decider_failed" in r["guards"]
