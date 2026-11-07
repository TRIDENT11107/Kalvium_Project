import json
import logging
import os
import random
import re
import threading
import time

import requests

from config import (
    GROQ_API_KEY,
    GROQ_MAX_COMPLETION_TOKENS,
    GROQ_MAX_RETRIES,
    GROQ_MODEL,
    GROQ_TIMEOUT,
    GROQ_TPM_BUDGET,
    GROQ_BACKOFF_MAX_SECONDS,
)


GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"


class LLMError(RuntimeError):
    pass


class GroqRateLimitError(LLMError):
    def __init__(self, message, retry_after=None):
        super().__init__(message)
        self.retry_after = retry_after


class GroqTokenBudgetError(GroqRateLimitError):
    pass


logger = logging.getLogger(__name__)
_budget_lock = threading.Lock()
_token_reservations = []


def _estimate_tokens(messages):
    return max(1, sum(len(str(message.get("content", ""))) for message in messages) // 4)


def _reserve_tokens(amount, budget=None):
    """Reserve a conservative request budget in a rolling one-minute window."""
    limit = int(budget or os.getenv("GROQ_TPM_BUDGET", GROQ_TPM_BUDGET))
    now = time.monotonic()
    with _budget_lock:
        _token_reservations[:] = [(timestamp, tokens) for timestamp, tokens in _token_reservations
                                  if now - timestamp < 60]
        used = sum(tokens for _, tokens in _token_reservations)
        if amount > limit or used + amount > limit:
            wait = 60 - (now - _token_reservations[0][0]) if _token_reservations else 60
            raise GroqTokenBudgetError(
                "Groq token budget is temporarily exhausted; retry in a moment.",
                retry_after=max(1, min(wait, GROQ_BACKOFF_MAX_SECONDS)),
            )
        _token_reservations.append((now, amount))


def _parse_json(content):
    """Parse a JSON object, including when a model adds a short wrapper around it."""
    if not isinstance(content, str):
        raise ValueError("response content was not text")

    text = content.strip().lstrip("\ufeff")
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    try:
        value = json.loads(text)
    except json.JSONDecodeError as original_error:
        # Tolerate brief prose before/after a complete object, but never salvage
        # or silently discard fields from malformed JSON itself.
        value = None
        for index, character in enumerate(text):
            if character not in "[{":
                continue
            try:
                value, _ = json.JSONDecoder().raw_decode(text[index:])
                break
            except json.JSONDecodeError:
                continue
        if value is None:
            raise original_error

    if not isinstance(value, dict):
        raise ValueError("response must be a JSON object")
    return value


def _retry_delay(response, attempt):
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return min(max(float(retry_after), 0), 60)
        except ValueError:
            pass
    reset = response.headers.get("x-ratelimit-reset-tokens")
    if reset:
        seconds = re.fullmatch(r"(?:(\d+(?:\.\d+)?)m)?(\d+(?:\.\d+)?)s", reset.strip())
        if seconds:
            minutes = float(seconds.group(1) or 0)
            remainder = float(seconds.group(2))
            return min(minutes * 60 + remainder, 60)
    body = ""
    try:
        body = str(response.json().get("error", {}).get("message", ""))
    except (ValueError, AttributeError):
        pass
    match = re.search(r"(?:retry|try again|reset).*?(\d+(?:\.\d+)?)\s*(seconds?|secs?|s|minutes?|mins?|m)\b", body, re.I)
    if match:
        value = float(match.group(1)) * (60 if match.group(2).lower().startswith(("m",)) else 1)
        return min(max(value, 0), GROQ_BACKOFF_MAX_SECONDS)
    tpm = re.search(r"limit\s+(\d+)\s*tpm.*?used\s+(\d+).*?requested\s+(\d+)", body, re.I)
    if tpm and int(tpm.group(2)) + int(tpm.group(3)) > int(tpm.group(1)):
        return min(GROQ_BACKOFF_MAX_SECONDS, 60)
    return min((2 ** attempt) + random.uniform(0, 1), GROQ_BACKOFF_MAX_SECONDS)


def _provider_error(response, api_key):
    try:
        body = response.json()
        detail = body.get("error", {}).get("message", "")
    except (ValueError, AttributeError):
        detail = ""
    return str(detail).replace(api_key, "[redacted]")[:400]


def _completion(messages, model=None, max_completion_tokens=None):
    api_key = GROQ_API_KEY or os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise LLMError("GROQ_API_KEY is required to use the Groq provider")

    selected_model = model or os.getenv("GROQ_MODEL", GROQ_MODEL)
    max_retries = max(0, int(os.getenv("GROQ_MAX_RETRIES", GROQ_MAX_RETRIES)))
    for attempt in range(max_retries + 1):
        try:
            payload = {
                "model": selected_model,
                "max_completion_tokens": max_completion_tokens or GROQ_MAX_COMPLETION_TOKENS,
                "response_format": {"type": "json_object"},
                "messages": messages,
            }
            if selected_model.startswith("openai/gpt-oss-"):
                payload["reasoning_effort"] = "low"
            response = requests.post(
                GROQ_CHAT_URL,
                headers={"Authorization": "Bearer " + api_key},
                json=payload,
                timeout=(10, GROQ_TIMEOUT),
            )
        except requests.Timeout as error:
            if attempt < max_retries:
                time.sleep(min(2 ** attempt, 8))
                continue
            raise LLMError(f"Groq request timed out after {GROQ_TIMEOUT} seconds") from error
        except requests.ConnectionError as error:
            if attempt < max_retries:
                time.sleep(min(2 ** attempt, 8))
                continue
            raise LLMError("Groq connection failed; check network access and try again") from error
        except requests.RequestException as error:
            raise LLMError("Groq request could not be completed") from error

        if response.status_code in (408, 429) or response.status_code >= 500:
            if attempt < max_retries:
                time.sleep(_retry_delay(response, attempt))
                continue
            if response.status_code == 429:
                detail = _provider_error(response, api_key)
                suffix = ": " + detail if detail else ""
                logger.warning("Groq rate limit response status=%s retry_after=%s", response.status_code, _retry_delay(response, attempt))
                raise GroqRateLimitError(
                    "The AI provider is temporarily busy. Your lesson has been saved. "
                    "Please retry in a moment." + suffix,
                    retry_after=_retry_delay(response, attempt),
                )
            raise LLMError(f"Groq request failed with HTTP {response.status_code} after retries")

        if response.status_code in (401, 403):
            raise LLMError("Groq authentication failed; verify GROQ_API_KEY")
        if not response.ok:
            detail = _provider_error(response, api_key)
            suffix = ": " + detail if detail else ""
            raise LLMError(f"Groq request failed with HTTP {response.status_code}{suffix}")

        try:
            return response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise LLMError("Groq returned an invalid chat completion response") from error


def generate_json(system, prompt, model=None, *, max_completion_tokens=None):
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]
    output_limit = max_completion_tokens or GROQ_MAX_COMPLETION_TOKENS
    try:
        _reserve_tokens(_estimate_tokens(messages) + output_limit)
        content = _completion(messages, model, max_completion_tokens)
        try:
            return _parse_json(content)
        except (ValueError, json.JSONDecodeError) as parse_error:
            repair_messages = messages + [
                {"role": "assistant", "content": content},
                {
                    "role": "user",
                    "content": (
                        "Rewrite your previous response as one complete, valid JSON object. "
                        "Preserve all information, use double quoted keys and strings, "
                        "and return JSON only without markdown or commentary."
                    ),
                },
            ]
            _reserve_tokens(_estimate_tokens(repair_messages) + output_limit)
            repaired = _completion(repair_messages, model, max_completion_tokens)
            try:
                return _parse_json(repaired)
            except (ValueError, json.JSONDecodeError) as repair_error:
                raise LLMError(
                    "Groq returned invalid JSON after one repair attempt: " + str(repair_error)
                ) from parse_error
    except LLMError:
        raise
    except requests.RequestException as error:
        raise LLMError("Groq request could not be completed") from error
