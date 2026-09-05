"""Regression coverage for the SQL-identifier whitelists.

Both validators guard identifiers that are interpolated into SQL strings rather
than bound as parameters, so the whitelist IS the boundary. Both were written
as `re.match(r"^...$", ident)`, and `$` matches immediately before a trailing
newline as well as at end-of-string — so a single trailing "\n" passed
validation at every site.

This is the same defect node-a closed in `nougenmsg._SAFE_IDENT` on 2026-09-04.
It existed here too, untested, in two more places. The tests below fail on
`.match()` and pass on `.fullmatch()`; that is the whole point of them.
"""
import pytest

from nougen_shards.connectors.local_vault import _is_valid_identifier
from nougen_shards.connectors.sql import is_valid_identifier

VALIDATORS = [
    pytest.param(_is_valid_identifier, id="local_vault"),
    pytest.param(is_valid_identifier, id="external_sql"),
]

ACCEPTED = ["shards", "users", "_private", "Title_Col", "a", "col9", "_9"]

# The first two are the regression: `.match()` accepts both.
REJECTED = [
    "shards\n",          # trailing LF — `$` matches before it
    "shards\n\n",        # `$` matches before the FINAL newline
    "shards\r\n",
    "shards\r",
    "shards DROP",
    "shards;DROP TABLE x",
    "shards--",
    '"shards"',
    "9shards",           # leading digit
    "",
    " shards",
    "shards ",
    "shards\tx",
    "sh\nards",
    "shards\x00",
]


@pytest.mark.parametrize("validator", VALIDATORS)
@pytest.mark.parametrize("ident", ACCEPTED)
def test_plain_identifiers_are_accepted(validator, ident):
    assert validator(ident) is True


@pytest.mark.parametrize("validator", VALIDATORS)
@pytest.mark.parametrize("ident", REJECTED)
def test_unsafe_identifiers_are_rejected(validator, ident):
    assert validator(ident) is False


@pytest.mark.parametrize("validator", VALIDATORS)
def test_trailing_newline_is_the_documented_regression(validator):
    """Kept separate and named so a future `.match()` revert says why it broke."""
    assert validator("shards") is True
    assert validator("shards\n") is False


@pytest.mark.parametrize("validator", VALIDATORS)
def test_none_does_not_raise(validator):
    """The external-DB caller passes conf['table_name'] straight through; a
    missing key must be rejected, not turned into a TypeError inside the sweep."""
    assert validator(None) is False
