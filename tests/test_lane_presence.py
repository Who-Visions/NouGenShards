from nougen_shards.lane_presence import LanePresence


def test_heartbeat_makes_lane_live_until_ttl():
    p = LanePresence(ttl_s=60)
    p.heartbeat("whoart", now=1000)
    assert p.is_live("whoart", now=1059)
    assert not p.is_live("whoart", now=1061)


def test_lane_names_are_case_insensitive():
    p = LanePresence()
    p.heartbeat("ChatGPT-App", now=0)
    assert p.is_live("chatgpt-app", now=1)


def test_reply_goes_to_origin_lane_when_live():
    p = LanePresence(ttl_s=60)
    p.heartbeat("whoart", now=100)
    env = {"origin_lane": "whoart", "lane": "phoebus"}
    assert p.reply_target(env, now=110) == "whoart"


def test_reply_falls_back_to_lane_then_none():
    p = LanePresence(ttl_s=60)
    p.heartbeat("blade", now=100)
    assert p.reply_target({"origin_lane": "whoart", "lane": "blade"}, now=110) == "blade"
    assert p.reply_target({"origin_lane": "whoart"}, now=110) is None


def test_reply_never_targets_a_quiet_lane():
    p = LanePresence(ttl_s=60)
    p.heartbeat("whoart", now=0)
    assert p.reply_target({"origin_lane": "whoart"}, now=1000) is None


def test_live_lanes_lists_only_fresh():
    p = LanePresence(ttl_s=60)
    p.heartbeat("a", now=0)
    p.heartbeat("b", now=100)
    assert p.live_lanes(now=110) == ["b"]


def test_default_registry_is_a_singleton():
    from nougen_shards.lane_presence import default_presence
    assert default_presence() is default_presence()


def test_origin_envelope_records_speaking_lane():
    import time
    from nougen_shards import nougenmsg
    from nougen_shards.lane_presence import default_presence
    default_presence()._seen.clear()
    nougenmsg.NouGenMsgBus._origin_envelope({"lane": "whoart", "session_id": "s1"})
    assert default_presence().is_live("whoart", now=time.time())
