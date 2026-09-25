"""NouGen War Games: adversarial simulation layer (first implementation slice).

Doctrine: docs/wargames-doctrine.md, section 83. This slice ships:

* ``model``        scenario objects + JSON loader/validator
* ``adjudication`` deterministic invariant checks and victory conditions
* ``runner``       turn engine: inject -> Blue claim -> White verdict -> repair
* ``receipts``     JSON receipt, Markdown AAR, ledger line, elevation candidate

Everything here is deterministic. No model calls, no network, no production
mutation: the arena floor first, the arcade cabinet later.
"""
from .model import WarGame, load_scenario, list_scenarios, validate_scenario  # noqa: F401
from .runner import run_game, replay_receipt, POLICIES  # noqa: F401
from .receipts import Receipt, write_receipt, render_aar  # noqa: F401
