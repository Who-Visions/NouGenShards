"""Assurance labels must be structured, redacted, and non-mutating."""
import json

from nougen_shards.assurance import assess_claim


def test_assurance_routes_to_iris_runner_and_requires_operator_gate():
    seen = []

    def iris(prompt):
        seen.append(prompt)
        return json.dumps({
            "status": "VERIFIED",
            "confidence": 0.92,
            "rationale": "The supplied receipt directly supports the claim.",
            "evidence_used": ["receipt-1"],
            "caveats": [],
        })

    result = assess_claim("the repair landed", ["receipt-1"], iris_runner=iris)
    assert seen and "the repair landed" in seen[0]
    assert result["status"] == "VERIFIED"
    assert result["verifier"] == "Iris"
    assert result["operator_gate_required"] is True


def test_assurance_redacts_secrets_before_and_after_iris():
    secret = "".join(["nougen_", "fleet_", "token_", "fixture_fake_value"])
    seen = []

    def iris(prompt):
        seen.append(prompt)
        return json.dumps({
            "status": "UNCERTAIN",
            "confidence": 2.0,
            "rationale": f"Observed {secret}",
            "evidence_used": [secret],
            "caveats": ["reachability was not tested"],
        })

    result = assess_claim(f"token is {secret}", [secret], iris_runner=iris)
    assert secret not in seen[0]
    assert secret not in json.dumps(result)
    assert result["confidence"] == 1.0


def test_assurance_fails_closed_on_bad_iris_output():
    result = assess_claim("claim", iris_runner=lambda _prompt: "not json")
    assert result["status"] == "UNVERIFIED"
    assert result["confidence"] == 0.0
    assert result["operator_gate_required"] is True
