"""Tests for Hardcade Quota Alert Ladder and Governor.

Validates:
1. Exact threshold transitions (<60% GREEN, 60% HEADS UP, 75% LOW AMMO, 85% DANGER, 90% RATION, 95% CONTINUE, 99% FINAL ROUND, 100% GAME OVER).
2. De-duplication per bucket (no spam when re-evaluating same band).
3. Reset condition triggers 1UP alert and restores normal routing.
4. Denominator provenance handling (metered, estimated, unknown).
5. Paid overflow enabled emits INSERT COIN instead of GAME OVER.
"""


from nougen_shards.quota_governor import (
    DenominatorProvenance,
    QuotaGovernor,
    QuotaLevel,
    RoutingDirective
)


def test_quota_ladder_threshold_classifications():
    gov = QuotaGovernor(allow_paid_overflow=False)
    
    assert gov.classify_percentage(0.0)[0] == QuotaLevel.GREEN
    assert gov.classify_percentage(59.9)[0] == QuotaLevel.GREEN
    assert gov.classify_percentage(60.0)[0] == QuotaLevel.HEADS_UP
    assert gov.classify_percentage(74.9)[0] == QuotaLevel.HEADS_UP
    assert gov.classify_percentage(75.0)[0] == QuotaLevel.LOW_AMMO
    assert gov.classify_percentage(84.9)[0] == QuotaLevel.LOW_AMMO
    assert gov.classify_percentage(85.0)[0] == QuotaLevel.DANGER
    assert gov.classify_percentage(89.9)[0] == QuotaLevel.DANGER
    assert gov.classify_percentage(90.0)[0] == QuotaLevel.RATION
    assert gov.classify_percentage(94.9)[0] == QuotaLevel.RATION
    assert gov.classify_percentage(95.0)[0] == QuotaLevel.CONTINUE
    assert gov.classify_percentage(98.9)[0] == QuotaLevel.CONTINUE
    assert gov.classify_percentage(99.0)[0] == QuotaLevel.FINAL_ROUND
    assert gov.classify_percentage(99.9)[0] == QuotaLevel.FINAL_ROUND
    assert gov.classify_percentage(100.0)[0] == QuotaLevel.GAME_OVER


def test_routing_directives_adapt_to_levels():
    gov = QuotaGovernor()

    # 75% LOW AMMO -> PREFER_LOCAL
    _, directive, route = gov.classify_percentage(75.0)
    assert directive == RoutingDirective.PREFER_LOCAL
    assert route == "ollama-local"

    # 85% DANGER -> RESTRICT_REASONING
    _, directive, route = gov.classify_percentage(85.0)
    assert directive == RoutingDirective.RESTRICT_REASONING

    # 95% CONTINUE -> CHECKPOINT_FALLBACK
    _, directive, route = gov.classify_percentage(95.0)
    assert directive == RoutingDirective.CHECKPOINT_FALLBACK

    # 100% GAME OVER -> TAG_IN_FALLBACK
    _, directive, route = gov.classify_percentage(100.0)
    assert directive == RoutingDirective.TAG_IN_FALLBACK


def test_alert_deduplication():
    gov = QuotaGovernor()

    # First time crossing 85% -> Emits DANGER alert
    alert1 = gov.evaluate_usage(
        provider="anthropic",
        bucket="tier4-token-bucket",
        used=850.0,
        limit=1000.0
    )
    assert alert1 is not None
    assert alert1.level == QuotaLevel.DANGER

    # Same band (86%) -> Deduplicated, returns None
    alert2 = gov.evaluate_usage(
        provider="anthropic",
        bucket="tier4-token-bucket",
        used=860.0,
        limit=1000.0
    )
    assert alert2 is None

    # Crossing into 95% CONTINUE -> Emits alert
    alert3 = gov.evaluate_usage(
        provider="anthropic",
        bucket="tier4-token-bucket",
        used=950.0,
        limit=1000.0
    )
    assert alert3 is not None
    assert alert3.level == QuotaLevel.CONTINUE


def test_reset_triggers_1up_event():
    gov = QuotaGovernor()

    # Push to GAME OVER (100%)
    gov.evaluate_usage(
        provider="openai",
        bucket="five-hour",
        used=1000.0,
        limit=1000.0
    )
    assert gov.get_effective_directive("openai", "five-hour") == RoutingDirective.TAG_IN_FALLBACK

    # Window resets -> Usage drops to 10%
    alert_reset = gov.evaluate_usage(
        provider="openai",
        bucket="five-hour",
        used=100.0,
        limit=1000.0
    )
    assert alert_reset is not None
    assert alert_reset.level == QuotaLevel.ONE_UP
    assert gov.get_effective_directive("openai", "five-hour") == RoutingDirective.NORMAL


def test_missing_or_invalid_quota_yields_honest_unknown():
    gov = QuotaGovernor()

    alert = gov.evaluate_usage(
        provider="custom-cloud",
        bucket="unknown-tier",
        used=150.0,
        limit=None,
        provenance=DenominatorProvenance.UNKNOWN
    )
    # Under unknown limit, it defaults to GREEN without emitting false alarm
    assert alert is None
    assert gov.get_effective_directive("custom-cloud", "unknown-tier") == RoutingDirective.NORMAL


def test_paid_overflow_emits_insert_coin():
    gov_paid = QuotaGovernor(allow_paid_overflow=True)
    alert = gov_paid.evaluate_usage(
        provider="google",
        bucket="daily-quota",
        used=1000.0,
        limit=1000.0
    )
    assert alert is not None
    assert alert.level == QuotaLevel.INSERT_COIN
    assert alert.recommended_route == "paid-overflow"
