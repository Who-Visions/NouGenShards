"""Demo evidence for the leg's two Definition-of-Done cases.

These are FIXTURES, not observed data: timestamps, hashes and base-rate
counts are constructed to exercise the engine. The Biker Mice from Mars
premiere date is a placeholder and is NOT verified -- a live run must take it
from Griot/Shards with a real provenance hash.
"""
from datetime import datetime, timezone

from nougen_shards.synchron import BaseRates, Event, Snapshot, Window


def ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).timestamp() * 1000)


AS_OF = ms("2026-09-21T18:00:00")
EQUINOX = Window("equinox", "2026-09-20", "2026-09-24", "astronomical")
BMFM = Window("biker mice from mars anniversary", "2026-09-18", "2026-09-22", "anniversary")

RATES = BaseRates(
    concept_counts={"sun": 400, "solar system": 120, "astronomy": 300, "equinox": 60,
                    "angkor wat": 12, "cambodia": 30, "motorcycles": 200, "mars": 150,
                    "biker mice from mars": 8, "cartoons": 90, "anniversary": 70},
    cooccurrence={"angkor wat|sun": 1, "angkor wat|solar system": 0, "astronomy|angkor wat": 0,
                  "cambodia|sun": 1, "mars|motorcycles": 3, "biker mice from mars|motorcycles": 2},
    seasonal={"equinox": 0.10},
    popularity={"sun": 0.05},
    revision="fixture-r1",
)


def ev(eid, when, source_type, source_id, concepts, *, actor="dave", intent=(), lineage=(),
       canonical=None, created=None):
    t = ms(when)
    return Event(eid, ms(created) if created else t, t, source_type, source_id, actor,
                 concepts=tuple(concepts), explicit_user_intent=tuple(intent),
                 query_lineage=tuple(lineage), canonical_date=canonical,
                 provenance_hash="sha256:" + eid)


# Case B: solar research -> (independent) Cambodia -> Angkor equinox window.
SOLAR = ev("solar-doc", "2026-09-20T02:00:00", "shards_ingest", "yt:solar-5h33m",
           ["sun", "solar system", "astronomy", "equinox"])
ANGKOR = ev("angkor-equinox", "2026-09-21T14:00:00", "griot_calendar", "griot:angkor",
            ["angkor wat", "equinox", "sun", "astronomy", "cambodia"], actor="griot",
            intent=["cambodia", "trip"], canonical="2026-09-22")
# Negative control: Dave searched the equinox straight from the solar doc.
ANGKOR_SEARCHED = ev("angkor-searched", "2026-09-20T03:00:00", "web_search", "search:1",
                     ["angkor wat", "equinox", "sun", "astronomy"],
                     intent=["angkor", "equinox", "sun"], lineage=["solar-doc"])

# Case A: motorcycle research collides with a show's premiere anniversary.
MOTO = ev("moto-research", "2026-09-19T20:00:00", "shards_ingest", "notes:moto",
          ["motorcycles", "mars", "cartoons"], intent=["mars motorcycle"])
BMFM_ANNIV = ev("bmfm-anniv", "2026-09-21T09:00:00", "griot_calendar", "griot:bmfm",
                ["biker mice from mars", "motorcycles", "mars", "anniversary", "cartoons"],
                actor="griot", canonical="1993-09-19")
# Negative control: the anniversary event was back-filled weeks after the fact.
BMFM_BACKFILLED = ev("bmfm-backfill", "2026-09-21T09:00:00", "griot_calendar", "griot:bmfm2",
                     ["biker mice from mars", "motorcycles", "mars", "anniversary", "cartoons"],
                     actor="griot", canonical="1993-09-19", created="2026-08-01T00:00:00")


def snap(*events):
    return Snapshot(AS_OF, tuple(events), (EQUINOX, BMFM), RATES, "fixture")
