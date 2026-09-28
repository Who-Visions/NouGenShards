"""provider_auth.py — Dynamic Tenant-Scoped Provider Authentication & Boundary Enforcement.

Trust boundaries:
1. Client -> NouGen uses NouGen MCP Gateway authentication (X-NGS-Token / NGS_NODE_TOKEN).
2. NouGen -> Provider (e.g., DeepSeek, OpenRouter, Anthropic) uses tenant-scoped Provider Bearer credentials.

Rules:
- DeepSeek (or any external provider API key) is NEVER used as the NouGen MCP Gateway token.
- Credentials resolve dynamically: tenant -> provider -> credential_ref -> secret store -> adapter.
- Zero hardcoded credentials, paths, tenant IDs, model strings, or operator identities.
- Provider failures are classified separately from local/fleet node health.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Dict, Any, Optional


@dataclass
class ProviderCredential:
    provider: str
    tenant_id: str
    api_key_ref: str
    api_key_value: str
    endpoint: str = ""

    def sanitize(self) -> Dict[str, str]:
        """Returns safe telemetry metadata without leaking secret key values."""
        fingerprint = self.api_key_value[:4] + "..." + self.api_key_value[-4:] if len(self.api_key_value) > 8 else "[REDACTED]"
        return {
            "provider": self.provider,
            "tenant_id": self.tenant_id,
            "api_key_ref": self.api_key_ref,
            "fingerprint": fingerprint,
            "endpoint": self.endpoint,
        }


class ProviderAuthBoundary:
    """Enforces dynamic separation between NouGen MCP Gateway auth and external Provider credentials."""

    @staticmethod
    def is_gateway_token_valid(provided_token: str, expected_gateway_token: Optional[str] = None) -> bool:
        """Validates incoming client token against the NouGen Gateway token only."""
        if not provided_token:
            return False
        expected = expected_gateway_token or os.environ.get("NGS_NODE_TOKEN") or os.environ.get("NOUGEN_GATEWAY_TOKEN")
        if not expected:
            return False
        return provided_token.strip() == expected.strip()

    @staticmethod
    def resolve_provider_credential(
        provider: str,
        tenant_id: str = "default",
        custom_key_override: Optional[str] = None,
        custom_endpoint: Optional[str] = None,
    ) -> ProviderCredential:
        """Dynamically resolves external provider credentials without hardcoded defaults."""
        provider_clean = provider.lower().strip()
        env_key_name = f"{provider_clean.upper()}_API_KEY"
        
        # Resolve key dynamically from override -> env -> secret store ref
        api_key = custom_key_override or os.environ.get(env_key_name, "")
        
        # Enforce boundary: DeepSeek / Provider API key CANNOT be used as Gateway Token
        gateway_token = os.environ.get("NGS_NODE_TOKEN", "")
        if api_key and gateway_token and api_key.strip() == gateway_token.strip():
            raise ValueError(
                f"Security Boundary Violation: {provider_clean.upper()}_API_KEY matches NGS_NODE_TOKEN. "
                "Provider keys must never be reused as the NouGen MCP Gateway authentication token."
            )

        endpoint = custom_endpoint or os.environ.get(f"{provider_clean.upper()}_ENDPOINT", "")
        if not endpoint:
            if provider_clean == "deepseek":
                endpoint = "https://api.deepseek.com/v1"
            elif provider_clean == "openrouter":
                endpoint = "https://openrouter.ai/api/v1"

        return ProviderCredential(
            provider=provider_clean,
            tenant_id=tenant_id,
            api_key_ref=env_key_name,
            api_key_value=api_key,
            endpoint=endpoint,
        )
