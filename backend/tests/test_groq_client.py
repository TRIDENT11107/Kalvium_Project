import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils import llm_client


def completion_response(content, status_code=200, headers=None):
    response = Mock()
    response.status_code = status_code
    response.ok = 200 <= status_code < 300
    response.headers = headers or {}
    response.json.return_value = {
        "choices": [{"message": {"content": content}}]
    }
    return response


def test_groq_json_completion_retries_rate_limit_without_exposing_key(monkeypatch):
    secret = "test-groq-key-that-must-not-appear-in-errors"
    monkeypatch.setattr(llm_client, "GROQ_API_KEY", secret)
    monkeypatch.setattr(llm_client, "GROQ_MAX_RETRIES", 1)
    monkeypatch.setattr(llm_client.time, "sleep", lambda _delay: None)
    post = Mock(side_effect=[
        completion_response("", 429, {"Retry-After": "0"}),
        completion_response('{"ok": true}'),
    ])
    monkeypatch.setattr(llm_client.requests, "post", post)

    result = llm_client.generate_json("Return JSON only.", "Return ok=true.")

    assert result == {"ok": True}
    assert post.call_count == 2
    assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer " + secret
    assert post.call_args.kwargs["json"]["response_format"] == {"type": "json_object"}
    assert post.call_args.kwargs["json"]["max_completion_tokens"] == llm_client.GROQ_MAX_COMPLETION_TOKENS
    assert post.call_args.kwargs["json"]["reasoning_effort"] == "low"


def test_groq_error_redacts_api_key(monkeypatch):
    secret = "test-groq-key-that-must-not-appear-in-errors"
    monkeypatch.setattr(llm_client, "GROQ_API_KEY", secret)
    monkeypatch.setattr(llm_client, "GROQ_MAX_RETRIES", 0)
    response = completion_response("", 400)
    response.json.return_value = {"error": {"message": "invalid value " + secret}}
    monkeypatch.setattr(llm_client.requests, "post", Mock(return_value=response))

    with pytest.raises(llm_client.LLMError) as error:
        llm_client.generate_json("Return JSON only.", "Return a result.")

    assert secret not in str(error.value)
    assert "[redacted]" in str(error.value)


def test_groq_timeout_returns_sanitized_error(monkeypatch):
    monkeypatch.setattr(llm_client, "GROQ_API_KEY", "test-key")
    monkeypatch.setattr(llm_client, "GROQ_MAX_RETRIES", 0)
    monkeypatch.setattr(llm_client.requests, "post", Mock(side_effect=requests.Timeout()))

    with pytest.raises(llm_client.LLMError, match="timed out") as error:
        llm_client.generate_json("Return JSON only.", "Return a result.")

    assert "test-key" not in str(error.value)


def test_json_parser_accepts_wrapped_json_object():
    assert llm_client._parse_json('Result:\n```json\n{"ok": true}\n```') == {"ok": True}


def test_rate_limit_reset_header_controls_backoff():
    response = Mock()
    response.headers = {"x-ratelimit-reset-tokens": "7.66s"}

    assert llm_client._retry_delay(response, 0) == pytest.approx(7.66)


def test_provider_tpm_message_controls_retry_delay(monkeypatch):
    response = completion_response("", 429)
    response.json.return_value = {
        "error": {"message": "Rate limit exceeded. Limit 8000 TPM, Used 4233, Requested 4507."}
    }
    assert llm_client._retry_delay(response, 0) == 60


def test_backoff_adds_jitter_when_provider_gives_no_timing(monkeypatch):
    response = completion_response("", 503)
    monkeypatch.setattr(llm_client.random, "uniform", lambda _low, _high: 0.25)
    assert llm_client._retry_delay(response, 0) == pytest.approx(1.25)
    assert llm_client._retry_delay(response, 1) == pytest.approx(2.25)


def test_token_budget_exhaustion_avoids_request(monkeypatch):
    monkeypatch.setattr(llm_client, "GROQ_API_KEY", "test-key")
    monkeypatch.setattr(llm_client, "GROQ_TPM_BUDGET", 10)
    llm_client._token_reservations.clear()
    post = Mock()
    monkeypatch.setattr(llm_client.requests, "post", post)

    with pytest.raises(llm_client.GroqTokenBudgetError):
        llm_client.generate_json("System " * 20, "Prompt " * 20)

    post.assert_not_called()
    llm_client._token_reservations.clear()
