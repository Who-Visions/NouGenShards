"""Tests for Dynamic & Deterministic Custom Ollama Model Resolver."""
import pytest
from unittest.mock import patch
from nougen_shards.custom_model_resolver import (
    resolve_best_custom_model,
    score_model,
    detect_node_identity,
    is_embedding_model,
    is_custom_user_model,
    estimate_custom_model_vram_gb,
    ModelBudgetConfig
)


def test_embedding_models_are_disqualified():
    """Embedding models must be disqualified from chat/reasoning with a huge negative score."""
    embed_models = [
        "nomic-embed-text:latest",
        "bge-m3:latest",
        "bge-large:latest",
        "all-minilm-l6-v2:latest",
        "text-embedding-3-small:latest"
    ]
    for m in embed_models:
        assert is_embedding_model(m) is True
        assert score_model(m) <= -50000.0


def test_custom_user_models_identified():
    """User-created personas and fine-tunes must be classified as custom."""
    custom_models = [
        "Yukiai:e2b",
        "solai:e2b",
        "mrs-b:latest",
        "keadracode:latest",
        "dav1d:e2b",
        "griot:e2b",
        "rhea-noir:e4b",
        "iris-ai:e4b",
        "my-finetuned-assistant:latest"
    ]
    for m in custom_models:
        assert is_custom_user_model(m) is True

    # Standard stock vendor models without custom tags
    assert is_custom_user_model("llama3:latest") is False
    assert is_custom_user_model("mistral:latest") is False


def test_hyperion_node_resolution():
    """On Hyperion (PX13, 6GB VRAM), Yukiai:e2b must be selected deterministically."""
    models = [
        "yuki-ai:31b",
        "Yukiai:e2b",
        "mrs-b:latest",
        "gemma2:2b",
        "gemma4:e2b-qat",
        "solai:e2b",
        "solai:e4b",
        "Yukiai:e4b",
        "nomic-embed-text:latest"
    ]
    hyperion_node = {
        "node_name": "Hyperion",
        "stadium": "ASUS ProArt PX13",
        "primary_player": "Yukiai",
        "player_aliases": ["yukiai", "yuki-ai", "yuki"],
        "vram_ceiling_gb": 6.0,
        "optimal_tags": ["Yukiai:e2b", "yukiai:e2b", "Yukiai:e4b", "yukiai:e4b", "gemma4:e2b-qat"]
    }
    winner = resolve_best_custom_model(models, node_info=hyperion_node)
    assert winner is not None
    assert winner.model_name == "Yukiai:e2b"
    assert winner.n_ctx == 4096


def test_apollo_node_resolution():
    """On Apollo (Razer Blade, 8GB VRAM), solai:e2b must be selected deterministically."""
    models = [
        "yuki-ai:31b",
        "Yukiai:e2b",
        "solai:e2b",
        "solai:e4b",
        "gemma4:e2b-qat"
    ]
    apollo_node = {
        "node_name": "Apollo",
        "stadium": "Razer Blade 2020 Super Max-Q",
        "primary_player": "Sol-Ai",
        "player_aliases": ["solai", "sol-ai"],
        "vram_ceiling_gb": 8.0,
        "optimal_tags": ["solai:e2b", "sol-ai:e2b", "solai:e4b", "solai:latest"]
    }
    winner = resolve_best_custom_model(models, node_info=apollo_node)
    assert winner is not None
    assert winner.model_name == "solai:e2b"


def test_persona_hint_routing():
    """When a specific persona hint is provided, the matching custom persona model must win."""
    models = [
        "Yukiai:e2b",
        "mrs-b:latest",
        "solai:e2b",
        "dav1d:e2b",
        "griot:e2b"
    ]
    winner_mrsb = resolve_best_custom_model(models, persona_hint="mrs-b")
    assert winner_mrsb is not None
    assert winner_mrsb.model_name == "mrs-b:latest"

    winner_griot = resolve_best_custom_model(models, persona_hint="griot")
    assert winner_griot is not None
    assert winner_griot.model_name == "griot:e2b"


def test_explicit_env_override(monkeypatch):
    """NOUGEN_OLLAMA_MODEL environment variable must win unconditionally."""
    models = [
        "Yukiai:e2b",
        "mrs-b:latest",
        "gemma4:e4b"
    ]
    monkeypatch.setenv("NOUGEN_OLLAMA_MODEL", "gemma4:e4b")
    winner = resolve_best_custom_model(models)
    assert winner is not None
    assert winner.model_name == "gemma4:e4b"


def test_vram_estimation():
    """Custom models must have positive dynamic VRAM footprint estimations."""
    assert estimate_custom_model_vram_gb("Yukiai:e2b") > 0.0
    assert estimate_custom_model_vram_gb("mrs-b:latest") > 0.0
    assert estimate_custom_model_vram_gb("nomic-embed-text:latest") <= 0.5
    assert estimate_custom_model_vram_gb("llama3:70b") >= 35.0
    assert estimate_custom_model_vram_gb("my-custom-model:cloud") == 0.0
