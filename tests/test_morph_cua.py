"""
Unit tests for nougen_morph.cua (Hark Pro Shang Tsung Absorption inside nougenshards).
"""

from nougen_morph import (
    ActionCard,
    HeadlessHandoffSession,
    GenerativePanel,
    AtmosphericSkyEngine,
    SecuredVaultDetokenizer,
)


def test_nougenshards_action_card():
    card = ActionCard(
        card_id="card_shards_01",
        title="Unused Cloud Compute Instance",
        summary="Idle for 72h. Potential savings $45/mo.",
        action_type="stop_instance",
        payload={"instance_id": "inst_99"},
        suggested_button_label="Stop Instance"
    )
    assert card.status == "pending"
    assert card.execute(lambda p: p["instance_id"] == "inst_99") is True
    assert card.status == "completed"


def test_nougenshards_open_kitchen_abort():
    session = HeadlessHandoffSession(session_id="handoff_shards_01")
    session.start(goal="Order groceries on Instacart")
    s1 = session.execute_step(action="navigate", target="https://instacart.com")
    assert s1["status"] == "completed"

    session.cancel_by_user(reason="Instant cancel from Open Kitchen")
    s2 = session.execute_step(action="click", target="button#checkout")
    assert s2["status"] == "aborted"
    assert "Instant cancel" in s2["reason"]


def test_nougenshards_generative_panel():
    panel = GenerativePanel(
        panel_id="panel_shards_01",
        title="Active Shard Matrix",
        widget_type="chart",
        config={"type": "radar", "lanes": 12}
    )
    panel.mutate_via_reply("Shift to bar view", {"type": "bar"})
    assert panel.config["type"] == "bar"


def test_nougenshards_atmospheric_sky():
    state = AtmosphericSkyEngine.get_atmospheric_state(lat=26.7153, lon=-80.0534, temp_f=87.0)
    assert "sky_gradient" in state
    assert len(state["sky_gradient"]) >= 3


def test_nougenshards_vault_detokenizer():
    vault = SecuredVaultDetokenizer()
    tok = vault.register_token("api_key", "sec_live_998877")
    assert tok.startswith("tok_")
    assert vault.detokenize_at_boundary(tok, "https://api.stripe.com") == "sec_live_998877"
