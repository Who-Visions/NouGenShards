"""tests/test_provider_auth_boundary.py — Unit tests for Provider Auth Boundary & Security Isolation."""

import os
import pytest
from nougen_shards.provider_auth import ProviderAuthBoundary, ProviderCredential


def test_gateway_token_validation():
    os.environ["NGS_NODE_TOKEN"] = "valid-gateway-secret-token"
    
    assert ProviderAuthBoundary.is_gateway_token_valid("valid-gateway-secret-token") is True
    assert ProviderAuthBoundary.is_gateway_token_valid("wrong-token") is False
    assert ProviderAuthBoundary.is_gateway_token_valid("") is False


def test_provider_credential_resolution():
    os.environ["DEEPSEEK_API_KEY"] = "sk-deepseek-test-key-12345"
    
    cred = ProviderAuthBoundary.resolve_provider_credential("deepseek", tenant_id="tenant-alpha")
    assert cred.provider == "deepseek"
    assert cred.tenant_id == "tenant-alpha"
    assert cred.api_key_value == "sk-deepseek-test-key-12345"
    assert cred.endpoint == "https://api.deepseek.com/v1"
    
    sanitized = cred.sanitize()
    assert sanitized["fingerprint"] == "sk-d...12345"
    assert "sk-deepseek-test-key-12345" not in str(sanitized.values())


def test_boundary_violation_rejection():
    os.environ["NGS_NODE_TOKEN"] = "shared-secret-key-error"
    os.environ["DEEPSEEK_API_KEY"] = "shared-secret-key-error"
    
    with pytest.raises(ValueError, match="Security Boundary Violation"):
        ProviderAuthBoundary.resolve_provider_credential("deepseek")
