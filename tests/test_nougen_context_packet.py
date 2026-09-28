from nougen_shards.context_packet import (
    scalpel_first_retrieve
)

def test_stage_1_scalpel_retrieval_sufficient():
    candidates = [
        {"id": "101", "source_node": "phoebus", "title": "Corbin Severity Lock", "content": "Corbin Veras holds Severity"},
        {"id": "102", "source_node": "blade", "title": "Random lore", "content": "Unrelated topic"}
    ]
    packet = scalpel_first_retrieve("Corbin Severity", candidates)
    assert packet.retrieval_stage == "stage_1_scalpel"
    assert len(packet.provenance_chain) == 1
    assert packet.provenance_chain[0].shard_id == "101"
    assert packet.budget_adhered is True

def test_stage_2_expansion_when_insufficient():
    stage_1 = [
        {"id": "201", "source_node": "phoebus", "title": "Vague title", "content": "Mentions something else"}
    ]
    stage_2 = [
        {"id": "301", "source_node": "whoart", "title": "Detailed Vault Item", "content": "Contains specific match phrase for expansion"}
    ]
    packet = scalpel_first_retrieve("specific match phrase", stage_1, stage_2_vault=stage_2)
    assert packet.retrieval_stage == "stage_2_expanded"
    assert any(p.shard_id == "301" for p in packet.provenance_chain)
    assert packet.budget_adhered is True
