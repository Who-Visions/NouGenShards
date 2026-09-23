#!/usr/bin/env python3
"""
custom_model_resolver.py - Dynamic & Deterministic Custom Ollama Model Resolution Engine.

Implements a deterministic multi-tier ranking and scoring algorithm to auto-detect and prioritize
the user's custom Ollama models, node-aligned player personas, and fine-tuned edge models.
"""

import os
import socket
from dataclasses import dataclass
from typing import List, Dict, Any, Optional


@dataclass
class ModelBudgetConfig:
    """Configuration for local LLM invocation."""
    model_name: str
    n_ctx: int = 4096
    max_tokens: Optional[int] = None
    temperature: float = 0.7

    def to_kwargs(self) -> dict:
        """Helper to unpack into Ollama or LMStudio options."""
        return {
            "model": self.model_name,
            "num_ctx": self.n_ctx,
            "temperature": self.temperature,
            "num_predict": self.max_tokens
        }


# Known embedding-only prefixes and substrings (never used for chat/reasoning)
EMBED_MARKERS = (
    "embed",
    "bge-",
    "bge_",
    "nomic-embed",
    "minilm",
    "gte-",
    "gte_",
    "e5-",
    "text-embedding",
    "all-minilm"
)

# Standard stock vendor prefixes that are NOT user custom models
STOCK_VENDOR_PREFIXES = (
    "gemma",
    "llama",
    "mistral",
    "mixtral",
    "phi",
    "deepseek",
    "codellama",
    "starcoder",
    "qwen",
    "granite",
    "command-r"
)


def detect_node_identity() -> Dict[str, Any]:
    """Detects node hardware identity, player assignment, and VRAM constraint."""
    env_node = os.getenv("NOUGEN_NODE_NAME") or os.getenv("NOUGEN_MACHINE") or ""
    hostname = socket.gethostname().lower()
    combined = f"{env_node.lower()} {hostname}"

    # 1. Hyperion (ASUS ProArt PX13)
    if any(k in combined for k in ("hyperion", "px13", "proart", "whoart", "who-art")):
        return {
            "node_name": "Hyperion",
            "stadium": "ASUS ProArt PX13",
            "primary_player": "Yukiai",
            "player_aliases": ["yukiai", "yuki-ai", "yuki"],
            "vram_ceiling_gb": 6.0,
            "optimal_tags": ["Yukiai:e2b", "yukiai:e2b", "Yukiai:e4b", "yukiai:e4b", "gemma4:e2b-qat"]
        }

    # 2. Apollo (Razer Blade 2020)
    if any(k in combined for k in ("apollo", "blade", "razer")):
        return {
            "node_name": "Apollo",
            "stadium": "Razer Blade 2020 Super Max-Q",
            "primary_player": "Sol-Ai",
            "player_aliases": ["solai", "sol-ai", "sol_ai"],
            "vram_ceiling_gb": 8.0,
            "optimal_tags": ["solai:e2b", "sol-ai:e2b", "solai:e4b", "sol-ai:e4b", "solai:latest"]
        }

    # 3. Phoebus (Apple Mac Mini)
    if any(k in combined for k in ("phoebus", "mac", "darwin")):
        return {
            "node_name": "Phoebus",
            "stadium": "Apple Mac Mini M2",
            "primary_player": "Keadracode",
            "player_aliases": ["keadracode", "keadra", "keadra-code"],
            "vram_ceiling_gb": 16.0,
            "optimal_tags": ["keadracode:latest", "keadra:e4b", "keadra:latest"]
        }

    # Default fallback node profile (assume tactical edge 6GB)
    return {
        "node_name": "TacticalEdge",
        "stadium": "Local Stadium",
        "primary_player": "Yukiai",
        "player_aliases": ["yukiai", "yuki-ai", "solai", "sol-ai", "keadra"],
        "vram_ceiling_gb": 6.0,
        "optimal_tags": ["Yukiai:e2b", "solai:e2b", "gemma4:e2b-qat"]
    }


def is_embedding_model(model_name: str) -> bool:
    """Returns True if the model is an embedding-only model."""
    clean = model_name.replace("\\", "/").lower()
    base = os.path.basename(clean)
    return any(marker in base for marker in EMBED_MARKERS)


def is_custom_user_model(model_name: str) -> bool:
    """Returns True if the model is a custom user-created/fine-tuned model."""
    clean = model_name.replace("\\", "/").lower()
    base = os.path.basename(clean)

    if is_embedding_model(clean):
        return False

    # Check known user custom model names & personas
    known_custom = (
        "yukiai", "yuki-ai", "solai", "sol-ai", "mrs-b", "mrsb",
        "keadra", "keadracode", "dav1d", "dav3", "davos", "griot",
        "rhea", "rhea-noir", "iris", "iris-ai", "tedley", "janitor",
        "gemma4-aggressive"
    )
    if any(k in base for k in known_custom):
        return True

    # Check file paths / GGUFs / custom models
    if base.endswith(".gguf") or base.endswith(".bin") or "/" in clean or "\\" in model_name:
        return True

    # If it starts with an official vendor prefix, only consider it custom if it has explicit custom tags
    is_stock = any(base.startswith(prefix) for prefix in STOCK_VENDOR_PREFIXES)
    if is_stock:
        custom_vendor_modifiers = ("-custom", "-fine", "-adapter", "-lora", "-aggressive", "-finetuned")
        return any(mod in base for mod in custom_vendor_modifiers)

    return True


def score_model(
    model_name: str,
    node_info: Optional[Dict[str, Any]] = None,
    persona_hint: Optional[str] = None
) -> float:
    """
    Computes a deterministic score for an Ollama model candidate.
    Higher score = higher priority selection.
    """
    if not model_name:
        return -100000.0

    if is_embedding_model(model_name):
        return -100000.0

    if node_info is None:
        node_info = detect_node_identity()

    score = 0.0
    model_lower = model_name.lower()
    base_name = os.path.basename(model_name.replace("\\", "/")).lower()

    # 1. Explicit Environment Override (+50000)
    explicit_env = os.getenv("NOUGEN_OLLAMA_MODEL") or os.getenv("NOUGEN_LOCAL_MODEL") or ""
    if explicit_env and (model_lower == explicit_env.lower() or base_name == explicit_env.lower()):
        return 50000.0

    # 2. Explicit Persona Hint Match (+10000)
    if persona_hint:
        p_clean = persona_hint.lower().replace("-", "").replace("_", "")
        m_clean = base_name.replace("-", "").replace("_", "")
        if p_clean in m_clean or m_clean.startswith(p_clean):
            score += 10000.0

    # 3. Node-Aligned Player Match (+4000 to +5000)
    player_aliases = node_info.get("player_aliases", [])
    is_player = any(alias in base_name for alias in player_aliases)
    if is_player:
        score += 4500.0
        # Optimal edge tags for this node get an extra boost
        optimal_tags = [t.lower() for t in node_info.get("optimal_tags", [])]
        if any(opt == model_lower or opt in model_lower for opt in optimal_tags):
            score += 800.0

    # 4. Specialized Fleet Domain Persona Models (+3500)
    specialized_personas = (
        "mrs-b", "mrsb", "solai", "sol-ai", "yukiai", "yuki-ai",
        "dav1d", "dav3", "davos", "griot", "rhea-noir", "rhea",
        "iris-ai", "iris", "keadracode", "keadra", "tedley"
    )
    if any(p in base_name for p in specialized_personas):
        score += 3500.0

    # 5. User Custom Architecture & Quantization Boost (+2000 to +3000)
    if is_custom_user_model(model_name):
        score += 2500.0

    vram_ceiling = node_info.get("vram_ceiling_gb", 6.0)

    if "e2b-qat" in base_name or "qat" in base_name:
        score += 3000.0
    elif ":e2b" in base_name or "-e2b" in base_name:
        score += 2200.0
    elif ":e4b" in base_name or "-e4b" in base_name:
        score += 1000.0

    # 6. VRAM Capacity Fitness Penalty / Reward
    # If on a 6GB card (Hyperion), heavy local 31B/70B/12B models receive a penalty to prevent GPU spill
    # Cloud models (:cloud / -cloud) run on remote servers and are exempt from local VRAM limits
    is_cloud_model = ":cloud" in base_name or "-cloud" in base_name
    if not is_cloud_model and ("31b" in base_name or "70b" in base_name or "120b" in base_name or "12b" in base_name):
        if vram_ceiling < 12.0:
            score -= 2200.0  # Prefer edge models over heavy models on 6GB/8GB laptop cards
        else:
            score += 500.0

    # 7. Cloud Gateway Models (+1500)
    if is_cloud_model:
        score += 1500.0

    return score


def resolve_best_custom_model(
    models: List[str],
    persona_hint: Optional[str] = None,
    node_info: Optional[Dict[str, Any]] = None
) -> Optional[ModelBudgetConfig]:
    """
    Dynamically and deterministically selects the best available custom Ollama model.
    """
    if not models:
        return None

    if node_info is None:
        node_info = detect_node_identity()

    # Filter out embedding models
    candidates = [m for m in models if not is_embedding_model(m)]
    if not candidates:
        return None

    # Deterministic ranking: sort by (score DESC, input_index ASC)
    scored_candidates = [
        (score_model(m, node_info, persona_hint), idx, m)
        for idx, m in enumerate(candidates)
    ]
    # Reverse sort by score DESC, idx ASC (using -idx)
    scored_candidates.sort(key=lambda x: (x[0], -x[1]), reverse=True)

    winner_score, winner_idx, winner_model = scored_candidates[0]

    # Calculate optimal context budget based on model name
    base_name = os.path.basename(winner_model.replace("\\", "/")).lower()
    n_ctx = 4096
    if "-8k" in base_name or "8k" in base_name:
        n_ctx = 8192
    elif "-16k" in base_name or "16k" in base_name:
        n_ctx = 8192
    elif any(k in base_name for k in ("dav1d", "rhea-noir", "griot", "janitor", "-2k", "2k")):
        n_ctx = 2048
    elif "e2b" in base_name or "2b" in base_name:
        n_ctx = 4096

    # Temperature policy: tight for reasoning/system models, balanced for creative
    temperature = 0.2 if any(k in base_name for k in ("e2b", "dav1d", "griot", "janitor")) else 0.7

    return ModelBudgetConfig(
        model_name=winner_model,
        n_ctx=n_ctx,
        temperature=temperature
    )


def estimate_custom_model_vram_gb(model_name: str) -> float:
    """
    Dynamically estimates the VRAM load footprint in GB for any custom or stock model.
    Ensures custom models pass the VRAM admission gate safely without hardcoded lookups.
    """
    clean = model_name.replace("\\", "/").lower()
    base = os.path.basename(clean)

    # Cloud models take 0 local VRAM
    if ":cloud" in base or "-cloud" in base:
        return 0.0

    # Embedding models
    if is_embedding_model(base):
        return 0.4

    # Measured QAT footprints
    if "qat" in base:
        return 1.66

    # Dense E-series vs standard quantized parameters
    if "e2b" in base:
        # Standard Q4_0 paged is ~2.0-2.5 GB; full dense uncompressed is 7.51 GB
        return 2.5
    if "e4b" in base:
        return 4.2
    if "2b" in base:
        return 2.0
    if "3b" in base or "4b" in base:
        return 3.5
    if "7b" in base or "8b" in base:
        return 5.2
    if "12b" in base or "14b" in base:
        return 8.5
    if "27b" in base or "31b" in base:
        return 19.5
    if "70b" in base:
        return 42.0

    # Default safe estimate for standard small Ollama models
    return 3.5
