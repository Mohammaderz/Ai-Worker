"""Conservative model routing and metadata for local Ollama calls.

This module records routing policy; it does not call remote providers or Codex.
"""
from __future__ import annotations

import hashlib
import os
import time
from dataclasses import asdict, dataclass
from typing import Mapping


DEFAULT_LOCAL_MODEL = "qwen2.5-coder:7b"
DEFAULT_REVIEW_MODEL = "deepseek-coder:6.7b"

_ROLES = {
    "planning": ("AI_WORKER_OLLAMA_MODEL", "AI_WORKER_MODEL", DEFAULT_LOCAL_MODEL),
    "drafting": ("AI_WORKER_MODEL", "AI_WORKER_OLLAMA_MODEL", DEFAULT_LOCAL_MODEL),
    "repair": ("AI_WORKER_MODEL", "AI_WORKER_OLLAMA_MODEL", DEFAULT_LOCAL_MODEL),
    "review": ("AI_WORKER_REVIEWER_MODEL", None, DEFAULT_REVIEW_MODEL),
}


@dataclass(frozen=True, slots=True)
class ModelRoute:
    stage: str
    provider: str
    model: str
    selected_by: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def resolve_model_route(
    stage: str,
    *,
    override: str | None = None,
    environment: Mapping[str, str] | None = None,
) -> ModelRoute:
    """Choose a compatible local model, preserving existing override precedence."""
    if stage not in _ROLES:
        raise ValueError(f"Unsupported model-routing stage: {stage}")
    env = os.environ if environment is None else environment
    primary_env, secondary_env, default = _ROLES[stage]
    if override is not None:
        model, selected_by = override, "explicit_argument"
    elif env.get(primary_env):
        model, selected_by = env[primary_env], primary_env
    elif secondary_env and env.get(secondary_env):
        model, selected_by = env[secondary_env], secondary_env
    else:
        model, selected_by = default, "role_default"
    if not isinstance(model, str) or not model or len(model) > 128 or any(c.isspace() for c in model):
        raise ValueError("Model route contains an invalid model name")
    reason = {
        "planning": "Use the local general coding model for evidence-based planning.",
        "drafting": "Use the local coding model for patch generation.",
        "repair": "Keep repair on the original local generator for bounded continuity.",
        "review": "Use a separately configured local model for independent review.",
    }[stage]
    return ModelRoute(stage, "ollama_loopback", model, selected_by, reason)


def _metadata_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def ollama_call_record(
    *,
    stage: str,
    model: str,
    request_body: bytes,
    response_body: bytes | None,
    response_data: object,
    started_ns: int,
    outcome: str,
    error_type: str | None = None,
) -> dict:
    """Return non-content telemetry; never persist prompts or raw model output."""
    metadata = response_data if isinstance(response_data, dict) else {}
    prompt_tokens = _metadata_int(metadata.get("prompt_eval_count"))
    completion_tokens = _metadata_int(metadata.get("eval_count"))
    model_duration_ns = _metadata_int(metadata.get("total_duration"))
    return {
        "schema_version": 1,
        "provider": "ollama_loopback",
        "stage": stage,
        "model": model,
        "outcome": outcome,
        "request_sha256": hashlib.sha256(request_body).hexdigest(),
        "response_sha256": (
            hashlib.sha256(response_body).hexdigest() if response_body is not None else None
        ),
        "elapsed_ms": round(max(0, time.perf_counter_ns() - started_ns) / 1_000_000, 3),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": (
            prompt_tokens + completion_tokens
            if prompt_tokens is not None and completion_tokens is not None
            else None
        ),
        "model_duration_ns": model_duration_ns,
        "cost_usd": None,
        "error_type": error_type,
    }
