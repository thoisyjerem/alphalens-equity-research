"""Small, explicit provider boundary for optional structured AI requests.

Google documents Chat Completions compatibility, so Gemini uses that endpoint;
OpenAI retains its existing Responses operation. No request switches providers,
retries, enables billing, browses, or supplies a key through a URL.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, ValidationError

ROOT = Path(__file__).resolve().parents[1]
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"
DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"


class ProviderError(RuntimeError):
    """A safe display message that never includes raw provider exception text."""

    def __init__(self, message: str, *, diagnostics: dict | None = None):
        super().__init__(message)
        self.diagnostics = diagnostics or {}


@dataclass(frozen=True)
class AIConfig:
    provider: str
    api_key: str = field(repr=False)
    model: str
    key_env: str
    model_env: str
    label: str

    @property
    def configured(self) -> bool:
        """Presence only: this does not claim authentication or quota was tested."""
        return bool(self.api_key and self.model)


def read_ai_config() -> AIConfig:
    """Read the project's .env regardless of launch directory.

    Explicit process environment variables take precedence. Restart Streamlit
    after editing .env: dotenv does not overwrite already loaded process values.
    Only the selected provider's credentials are read; there is no fallback.
    """
    load_dotenv(ROOT / ".env", override=False)
    provider = os.getenv("AI_PROVIDER", "gemini").strip().lower() or "gemini"
    if provider == "gemini":
        key_env, model_env, default, label = (
            "GEMINI_API_KEY", "GEMINI_MODEL", DEFAULT_GEMINI_MODEL, "Google Gemini")
    elif provider == "openai":
        key_env, model_env, default, label = (
            "OPENAI_API_KEY", "OPENAI_MODEL", DEFAULT_OPENAI_MODEL, "OpenAI")
    else:
        raise ProviderError("Set AI_PROVIDER to gemini or openai in local .env. No alternative provider was contacted.")
    return AIConfig(provider=provider, api_key=os.getenv(key_env, "").strip(),
                    model=os.getenv(model_env, "").strip() or default,
                    key_env=key_env, model_env=model_env, label=label)


@dataclass(frozen=True)
class StructuredResponse:
    output_parsed: BaseModel | None
    status: str
    provider: str
    model: str
    usage: dict[str, int]
    latency_seconds: float
    diagnostics: dict = field(default_factory=dict)


class GeminiJSONEnvelope(BaseModel):
    """Keep Gemini's wire schema simple; validate the full inner schema locally."""

    model_config = ConfigDict(extra="forbid", strict=True, revalidate_instances="always")
    result_json: str


def _gemini_messages(messages: list[dict[str, str]], schema: type[BaseModel]) -> list[dict[str, str]]:
    """Append trusted transport instructions without changing supplied evidence.

    The rich research schema was rejected by Gemini with a short prompt too,
    while a single-string wire schema accepted the original SEC messages. Keep
    the original Pydantic contract as prompt text and validate the decoded JSON
    against it before any financial/source verification or display.
    """
    instructions = (
        "\n\nTRANSPORT RESPONSE FORMAT:\n"
        "Return a JSON object with exactly one property, result_json. Its value must be a string "
        "containing the complete serialized JSON object required by the original output schema "
        "below. Do not include Markdown, code fences, commentary, or any fields outside that "
        "schema in the inner JSON. All original factual, qualitative, citation, evidence and "
        "financial-validation instructions still apply to the decoded inner object. The full "
        "inner object will be strictly validated locally before it can be displayed.\n"
        "Serialize the inner object as valid JSON: double-quoted keys and string values, "
        "no trailing commas, and no raw newlines inside strings. Then JSON-escape that "
        "serialized text as the outer result_json string. Syntax-only illustration "
        "(not the required fields): {\"result_json\":\"{\\\"example\\\":\\\"text\\\"}\"}. "
        "Use the original schema's fields instead of example; do not wrap the inner JSON in code fences.\n"
        "ORIGINAL OUTPUT SCHEMA:\n"
        + json.dumps(schema.model_json_schema(), ensure_ascii=False, separators=(",", ":"))
    )
    copied = [dict(message) for message in messages]
    for message in copied:
        if message.get("role") == "system":
            message["content"] = message["content"] + instructions
            break
    else:
        copied.insert(0, {"role": "system", "content": instructions.lstrip()})
    return copied


def _validate_gemini_native_schema(schema: type[BaseModel]) -> None:
    """Allow only the deliberately flat, string-based native wire contract.

    Nested/referenced schemas previously failed at Google's compatibility
    endpoint. Native output is therefore an explicit opt-in for a smaller
    contract, while all existing callers retain the tested JSON envelope.
    """
    message = ("Native Gemini output requires a flat object of required strings "
               "or string lists, without nested schemas or constraints. No request was made.")
    if not isinstance(schema, type) or not issubclass(schema, BaseModel):
        raise ProviderError(message)
    document = schema.model_json_schema()
    properties = document.get("properties")
    if (set(document) - {"title", "description", "type", "properties", "required", "additionalProperties"}
            or document.get("type") != "object" or document.get("additionalProperties") is not False
            or not isinstance(properties, dict) or not properties
            or set(document.get("required", ())) != set(properties)):
        raise ProviderError(message)
    metadata = {"title", "description"}
    for value in properties.values():
        if not isinstance(value, dict):
            raise ProviderError(message)
        if value.get("type") == "string" and not set(value) - (metadata | {"type"}):
            continue
        items = value.get("items")
        if (value.get("type") == "array" and not set(value) - (metadata | {"type", "items"})
                and isinstance(items, dict) and items.get("type") == "string"
                and not set(items) - (metadata | {"type"})):
            continue
        raise ProviderError(message)


def _error_codes(exc: Exception) -> set[str]:
    """Inspect only machine code fields internally; never return raw messages."""
    codes: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"code", "reason", "status", "type"} and isinstance(child, str):
                    codes.add(child.lower())
                elif isinstance(child, (dict, list)):
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(getattr(exc, "body", None))
    code = getattr(exc, "code", None)
    if isinstance(code, str):
        codes.add(code.lower())
    return codes


def _safe_error(exc: Exception, provider: str) -> str:
    from openai import APIConnectionError, APITimeoutError

    label = "Gemini" if provider == "gemini" else "OpenAI"
    key_env = "GEMINI_API_KEY" if provider == "gemini" else "OPENAI_API_KEY"
    model_env = "GEMINI_MODEL" if provider == "gemini" else "OPENAI_MODEL"
    status = getattr(exc, "status_code", None)
    codes = _error_codes(exc)
    if isinstance(exc, APITimeoutError):
        return f"{label} timed out. No automatic retry or provider fallback was made. Try again only when ready."
    if isinstance(exc, APIConnectionError):
        return f"Could not connect to {label}. Check your internet connection. No automatic retry or provider fallback was made."
    if status == 401 or codes & {"api_key_invalid", "invalid_api_key", "unauthenticated"}:
        return f"{label} rejected the API credentials. Check {key_env} in local .env, then restart Streamlit. Never share the key in chat."
    if status == 403:
        return f"{label} denied access. Check the selected project's key permissions, account eligibility and supported region. No billing was enabled or alternative provider contacted."
    if status == 429:
        if provider == "gemini":
            return "Gemini rate limit or free quota is unavailable or exhausted. Check AI Studio's project limits and wait for quota to reset. A free-tier project does not require enabling billing. No retry or paid fallback was made."
        if codes & {"insufficient_quota", "billing_hard_limit_reached", "billing_not_active"}:
            return "OpenAI API quota or credits are unavailable. ChatGPT subscriptions do not include API credits. No retry or provider fallback was made."
        return "OpenAI rate limit reached. Wait before making another explicit request. No automatic retry or provider fallback was made."
    if status == 404 or codes & {"model_not_found", "not_found"}:
        return f"{label} could not access the selected model. Check {model_env} and model availability for your project. No alternative model or provider was used."
    if status in {400, 422}:
        return f"{label} rejected the model or structured-output request. Check {model_env}, model compatibility and project or regional access. No billing was enabled or fallback attempted."
    if isinstance(status, int) and status >= 500:
        return f"{label} is temporarily unavailable. No automatic retry or provider fallback was made."
    return f"{label} did not return a valid structured response matching the required schema. The response was rejected; core SEC research remains available."


def _usage(response: Any, provider: str) -> dict[str, int]:
    usage = getattr(response, "usage", None)
    names = {"input_tokens": "prompt_tokens", "output_tokens": "completion_tokens",
             "total_tokens": "total_tokens"} if provider == "gemini" else {
                 "input_tokens": "input_tokens", "output_tokens": "output_tokens", "total_tokens": "total_tokens"}
    result = {}
    for public, source in names.items():
        value = getattr(usage, source, None)
        if type(value) is int and value >= 0:
            result[public] = value
    # Return only documented numeric usage, never raw provider metadata.
    return result


_OPERATIONS = frozenset({"structured_response", "ai_commentary", "research_briefing", "thesis_challenge"})


def _safe_model_name(model: str, api_key: str) -> str:
    """Retain a bounded model identifier, never a misconfigured credential."""
    clean = model.strip()
    if (api_key.strip() in clean or
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}", clean) is None):
        return "[redacted model identifier]"
    return clean


def _schema_issue_details(exc: ValidationError, schema: type[BaseModel]) -> tuple[list[dict], bool]:
    """Expose only bounded schema-owned paths and error codes, never inputs.

    Pydantic error inputs, contexts and arbitrary extra-field names can contain
    private model text. Unknown path components are therefore masked too.
    """
    fields: set[str] = set()

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            properties = value.get("properties")
            if isinstance(properties, dict):
                fields.update(name for name in properties
                              if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", name))
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(schema.model_json_schema())
    collect(GeminiJSONEnvelope.model_json_schema())
    errors = exc.errors(include_url=False, include_context=False, include_input=False)
    issues = []
    for error in errors[:12]:
        path = ""
        location = error.get("loc", ())
        for part in location[:8]:
            if type(part) is int:
                path += f"[{part}]" if 0 <= part <= 100000 else "[index]"
            else:
                name = part if isinstance(part, str) and part in fields else "[unrecognized_field]"
                path += ("." if path else "") + name
        if len(location) > 8:
            path += ".[truncated]"
        code = error.get("type", "validation_error")
        if not isinstance(code, str) or re.fullmatch(r"[a-z0-9_]{1,80}", code) is None:
            code = "validation_error"
        issues.append({"path": path or "$", "type": code})
    return issues, len(errors) > 12


def request_structured(*, provider: str, api_key: str, model: str,
                       messages: list[dict[str, str]], schema: type[BaseModel],
                       max_output_tokens: int, timeout: float,
                       client=None, operation: str = "structured_response",
                       gemini_native: bool = False,
                       repair_question_kind: bool = False) -> StructuredResponse:
    """Make exactly one selected-provider operation, then validate its shape.

    Callers must obtain explicit consent before invoking this function. An API
    key cannot reveal whether a Gemini project has paid billing enabled; account
    tier must be checked by the user in AI Studio before any live evaluation.
    """
    if provider not in {"gemini", "openai"}:
        raise ProviderError("Select gemini or openai explicitly. No alternative provider was contacted.")
    if type(gemini_native) is not bool:
        raise ProviderError("Native Gemini output must be explicitly enabled with a boolean. No request was made.")
    if type(repair_question_kind) is not bool or repair_question_kind and (provider != "gemini" or gemini_native):
        raise ProviderError("Local question classification repair is restricted to the legacy Gemini envelope. No request was made.")
    if gemini_native:
        if provider != "gemini":
            raise ProviderError("Native Gemini output is supported only by Gemini. No alternative provider was contacted.")
        _validate_gemini_native_schema(schema)
    key_env = "GEMINI_API_KEY" if provider == "gemini" else "OPENAI_API_KEY"
    model_env = "GEMINI_MODEL" if provider == "gemini" else "OPENAI_MODEL"
    if not isinstance(api_key, str) or not api_key.strip():
        raise ProviderError(f"Optional AI needs {key_env} in local .env. Core financial research remains available.")
    if not isinstance(model, str) or not model.strip():
        raise ProviderError(f"Set {model_env} to a model supporting structured outputs.")
    if type(max_output_tokens) is not int or max_output_tokens < 1 or max_output_tokens > 6000:
        raise ProviderError("AI output token limit must be between one and six thousand.")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 120:
        raise ProviderError("AI request timeout must be positive and at most two minutes.")
    started = monotonic()
    timestamp = datetime.now(timezone.utc).isoformat()
    response = None
    stage = "provider_response"
    parsing = "not_run"
    schema_result = "not_run"
    repair_paths = []

    def diagnostics(status: str, *, exc: Exception | None = None,
                    issues: list[dict] | None = None, truncated: bool = False) -> dict:
        http_status = getattr(exc, "status_code", None) if exc is not None else None
        result = {"timestamp_utc": timestamp, "operation": operation if isinstance(operation, str) and operation in _OPERATIONS else "structured_response",
            "provider": provider, "model": _safe_model_name(model, api_key), "status": status,
            "http_status": http_status if type(http_status) is int and 100 <= http_status <= 599 else None,
            "latency_seconds": round(monotonic() - started, 3), "usage": _usage(response, provider),
            "parsing_result": parsing, "schema_validation_result": schema_result,
            "validation_stage": stage, "validation_issues": issues or [], "issues_truncated": truncated}
        if repair_paths:
            result["local_repair_paths"] = list(repair_paths)
        return result

    def incomplete() -> StructuredResponse:
        metadata = diagnostics("incomplete")
        return StructuredResponse(output_parsed=None, status="incomplete", provider=provider,
            model=model.strip(), usage=_usage(response, provider),
            latency_seconds=metadata["latency_seconds"], diagnostics=metadata)

    try:
        if client is None:
            from openai import OpenAI
            options = {"api_key": api_key.strip(), "timeout": timeout, "max_retries": 0}
            if provider == "gemini":
                options["base_url"] = GEMINI_BASE_URL
            client = OpenAI(**options)
        if provider == "gemini":
            if gemini_native:
                # The SDK parses the provider's object directly. No nested JSON
                # serialization, schema prompt injection, or repair is needed.
                stage = "native_output"
            response = client.chat.completions.parse(model=model.strip(),
                messages=([dict(message) for message in messages] if gemini_native
                          else _gemini_messages(messages, schema)),
                response_format=schema if gemini_native else GeminiJSONEnvelope,
                max_tokens=max_output_tokens)
            stage = "native_output" if gemini_native else "envelope"
            choices = response.choices
            if len(choices) != 1 or choices[0].finish_reason != "stop":
                return incomplete()
            message = choices[0].message
            parsed = message.parsed
            if getattr(message, "refusal", None) or parsed is None:
                return incomplete()
            if gemini_native:
                parsing = "passed"
                stage = "output_schema"
            else:
                envelope = GeminiJSONEnvelope.model_validate(parsed)
                stage = "inner_json"
                # Malformed JSON is never repaired. The optional legacy policy
                # can supply only an unambiguous question classification.
                payload = json.loads(envelope.result_json)
                parsing = "passed"
                stage = "output_schema"
                try:
                    parsed = schema.model_validate_json(envelope.result_json)
                except ValidationError as exc:
                    if not repair_question_kind:
                        raise
                    from .research import repair_missing_question_kind
                    parsed, repair_paths = repair_missing_question_kind(payload, schema, exc)
        else:
            response = client.responses.parse(model=model.strip(), input=messages,
                text_format=schema, max_output_tokens=max_output_tokens, store=False)
            parsed = response.output_parsed
            if getattr(response, "status", "completed") != "completed" or parsed is None:
                return incomplete()
            parsing = "passed"
            stage = "output_schema"
        # Revalidate mappings even for injected legacy/base model instances;
        # the new note extends the original report contract without changing
        # historical schema-replay fixtures or allowing unvalidated instances.
        output = schema.model_validate(parsed.model_dump() if isinstance(parsed, BaseModel) else parsed)
        schema_result = "passed"
        metadata = diagnostics("completed")
        return StructuredResponse(output_parsed=output, status="completed", provider=provider,
            model=model.strip(), usage=_usage(response, provider),
            latency_seconds=metadata["latency_seconds"], diagnostics=metadata)
    except ProviderError:
        raise
    except Exception as exc:
        from openai import ContentFilterFinishReasonError, LengthFinishReasonError
        if isinstance(exc, LengthFinishReasonError):
            # The SDK retains the completion (including usage) on this error.
            # Keep numeric metadata without exposing its partial model text.
            response = getattr(exc, "completion", None)
            return incomplete()
        if isinstance(exc, ContentFilterFinishReasonError):
            return incomplete()
        issues, truncated = [], False
        if isinstance(exc, ValidationError):
            issues, truncated = _schema_issue_details(exc, schema)
            if gemini_native and stage == "native_output":
                # SDK validation occurs before it returns the completion. A
                # malformed JSON document differs from a decoded wrong shape.
                if any(issue["type"] == "json_invalid" for issue in issues):
                    parsing = "failed"
                    stage = "native_json"
                else:
                    parsing = "passed"
                    stage = "output_schema"
            if stage == "output_schema":
                schema_result = "failed"
            else:
                parsing = "failed"
        elif isinstance(exc, json.JSONDecodeError):
            parsing = "failed"
            issues = [{"path": "$", "type": "json_invalid"}]
        # Suppress raw SDK exception chains too: they may contain keys or text.
        safe_message = _safe_error(exc, provider)
        if isinstance(exc, json.JSONDecodeError) and stage == "inner_json":
            safe_message = (f"{ 'Gemini' if provider == 'gemini' else 'OpenAI' } returned malformed JSON inside its response envelope. "
                "Local schema and source checks were not run; no AI report was accepted. "
                "No automatic retry or provider fallback was made.")
        raise ProviderError(safe_message, diagnostics=diagnostics(
            "rejected" if isinstance(exc, (ValidationError, json.JSONDecodeError)) else "request_error",
            exc=exc, issues=issues, truncated=truncated)) from None
