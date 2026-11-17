import hashlib
import json

import pytest

from ai_worker.model_router import ollama_call_record, resolve_model_route


@pytest.mark.parametrize(
    ("stage", "expected"),
    [
        ("planning", "qwen2.5-coder:7b"),
        ("drafting", "qwen2.5-coder:7b"),
        ("repair", "qwen2.5-coder:7b"),
        ("review", "deepseek-coder:6.7b"),
    ],
)
def test_model_route_defaults_to_installed_local_roles(stage, expected):
    route = resolve_model_route(stage, environment={})

    assert route.provider == "ollama_loopback"
    assert route.model == expected
    assert route.selected_by == "role_default"


def test_model_route_preserves_legacy_role_environment_precedence():
    assert resolve_model_route(
        "planning",
        environment={"AI_WORKER_OLLAMA_MODEL": "planner-local"},
    ).model == "planner-local"
    assert resolve_model_route(
        "drafting",
        environment={"AI_WORKER_MODEL": "developer-local"},
    ).model == "developer-local"
    assert resolve_model_route(
        "review",
        environment={"AI_WORKER_REVIEWER_MODEL": "review-local"},
    ).model == "review-local"


def test_explicit_model_override_wins_without_selecting_remote_provider():
    route = resolve_model_route(
        "drafting",
        override="explicit-local-model",
        environment={"AI_WORKER_MODEL": "configured-local"},
    )

    assert route.model == "explicit-local-model"
    assert route.selected_by == "explicit_argument"
    assert route.provider == "ollama_loopback"


@pytest.mark.parametrize("model", ["", "bad model", "x" * 129])
def test_model_route_rejects_invalid_model_names(model):
    with pytest.raises(ValueError, match="invalid model name"):
        resolve_model_route("drafting", override=model)


def test_model_route_rejects_unknown_stage():
    with pytest.raises(ValueError, match="Unsupported model-routing stage"):
        resolve_model_route("remote-codex", environment={})


def test_ollama_usage_record_contains_hashes_and_metadata_but_no_content():
    request_body = b'{"prompt":"private prompt"}'
    response_body = b'{"message":{"content":"private output"}}'
    record = ollama_call_record(
        stage="drafting",
        model="qwen2.5-coder:7b",
        request_body=request_body,
        response_body=response_body,
        response_data={
            "prompt_eval_count": 11,
            "eval_count": 7,
            "total_duration": 123456,
        },
        started_ns=0,
        outcome="schema_valid",
    )

    serialized = json.dumps(record)
    assert record["request_sha256"] == hashlib.sha256(request_body).hexdigest()
    assert record["response_sha256"] == hashlib.sha256(response_body).hexdigest()
    assert record["prompt_tokens"] == 11
    assert record["completion_tokens"] == 7
    assert record["total_tokens"] == 18
    assert record["model_duration_ns"] == 123456
    assert record["cost_usd"] is None
    assert "private prompt" not in serialized
    assert "private output" not in serialized


def test_ollama_usage_record_does_not_treat_boolean_token_count_as_integer():
    record = ollama_call_record(
        stage="review",
        model="deepseek-coder:6.7b",
        request_body=b"{}",
        response_body=None,
        response_data={"prompt_eval_count": True, "eval_count": 2},
        started_ns=0,
        outcome="request_failed",
        error_type="TimeoutError",
    )

    assert record["prompt_tokens"] is None
    assert record["completion_tokens"] == 2
    assert record["total_tokens"] is None
    assert record["error_type"] == "TimeoutError"
