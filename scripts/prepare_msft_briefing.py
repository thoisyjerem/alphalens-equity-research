"""Prepare a focused request and authored SDK rehearsal; NEVER sends a model request.

Default inputs are explicitly offline fixtures. Use --snapshot with a previously
saved genuine SEC research_result/filing_contexts packet for a cached-live plan.
"""
from dataclasses import asdict
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import httpx
from openai import OpenAI
from alphalens.ai import generate_research_brief
from alphalens.focused_briefing import build_briefing_context
from alphalens.gemini_briefing import GeminiBriefingFields, GeminiFindingFields
from alphalens.filings import FilingExcerpt
from alphalens.models import AnnualPeriod, MetricValue, ResearchResult, SourceFact
from alphalens.providers import GEMINI_BASE_URL, read_ai_config
from alphalens.retrieval import RetrievedPassage
from alphalens.research_exports import export_research_json, export_research_markdown
from alphalens.service import load_offline_filing_context, load_research


def load_snapshot(path):
    saved = json.loads(Path(path).read_text(encoding="utf-8"))
    raw = saved["research_result"]
    periods = [AnnualPeriod(**{**p, "metrics": {name: MetricValue(**{**m,
        "sources": [SourceFact(**s) for s in m["sources"]]}) for name, m in p["metrics"].items()}}) for p in raw["periods"]]
    result = ResearchResult(**{**raw, "periods": periods})
    if result.ticker != "MSFT":
        raise ValueError("This prototype preparation is limited to Microsoft.")
    contexts = []
    for context in saved["filing_contexts"]:
        contexts.append({**context, "excerpts": {key: FilingExcerpt(**value) for key, value in context["excerpts"].items()}})
        if "focused_passages" in context:
            contexts[-1]["focused_passages"] = [RetrievedPassage(**{**p, "topics": tuple(p["topics"])}) for p in context["focused_passages"]]
    return result, contexts


def authored_shape(context, contract="focused_v2"):
    """Clearly authored prose for an offline engineering rehearsal only."""
    primary = context.packet["primary_observation_id"]
    ids = context.packet["additional_observation_ids"][:1]
    passage = next(iter(context.packet["passages"]))
    def finding():
        return {"interpretation": "The observed annual relationship may warrant investigation of operating durability and investment timing.",
            "supporting_passage_ids": [passage],
            "alternative_explanation": "Product mix or payment timing could contribute without establishing a permanent economic change.",
            "limitations": ["Consolidated figures do not isolate incremental AI investment economics."]}
    payload = {"executive_interpretation": {"observation_ids": [primary], "supporting_passage_ids": [],
        "interpretation": "Investment intensity may warrant scrutiny of cash returns before drawing conclusions about economic value."},
        "primary_finding": finding(),
        "findings": [{"observation_ids": [key], **finding()} for key in ids],
        "risks": [{"interpretation": "The selected disclosure may identify conditions requiring further analyst investigation.",
            "supporting_passage_ids": [passage], "limitations": "A source reference is not proof of the interpretation's economic significance."}],
        "unanswered_questions": ["What incremental profit and capital would support a defensible assessment of investment returns?",
            "Which utilisation and monetisation evidence would clarify the observed cash-investment relationship?"]}
    if contract == "focused_v3":
        del payload["executive_interpretation"]
    return payload


def prepare(output, snapshot=None, contract="focused_v3"):
    if contract not in {"focused_v2", "focused_v3"}:
        raise ValueError("Choose a supported preparation contract.")
    target = Path(output)
    target.mkdir(parents=True, exist_ok=True)
    result, contexts = (load_snapshot(snapshot) if snapshot else (load_research("MSFT", "offline"), None))
    if contexts is None:
        contexts = [load_offline_filing_context(result)]
    context = build_briefing_context(result, contexts)
    config = read_ai_config()
    if config.provider != "gemini":
        raise ValueError("Select AI_PROVIDER=gemini to prepare this plan; no provider was contacted.")
    if (re.fullmatch(r"(?:models/)?gemini-[A-Za-z0-9._-]{1,100}", config.model) is None
            or config.api_key and config.api_key in config.model):
        raise ValueError("Configured Gemini model identifier is invalid; no configuration value was exported.")
    captured = []
    payload = authored_shape(context, contract)
    wire_schema = GeminiFindingFields if contract == "focused_v3" else GeminiBriefingFields
    def mock(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "AUTHORED-REHEARSAL-NOT-LIVE", "object": "chat.completion",
            "created": 0, "model": config.model, "choices": [{"index": 0, "finish_reason": "stop",
            "message": {"role": "assistant", "content": wire_schema.from_compact(payload).model_dump_json()}}]})
    with httpx.Client(transport=httpx.MockTransport(mock)) as http:
        with OpenAI(api_key="offline-preparation-only", base_url=GEMINI_BASE_URL, max_retries=0, http_client=http) as client:
            report = generate_research_brief(result, "offline-preparation-only", config.model,
                filing_contexts=contexts, client=client, provider="gemini", contract=contract)
    assert len(captured) == 1 and report.verification.unsupported_count == 0
    report.warnings.insert(0, "AUTHORED OFFLINE REHEARSAL - NOT A LIVE MODEL RESPONSE. Provider metadata and latency describe a local SDK mock; no external API request was made.")
    request = captured[0]
    def save(name, data):
        text = json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False)
        # Authentication never enters saved JSON; guard against accidental echo.
        if config.api_key:
            text = text.replace(config.api_key, "[REDACTED CREDENTIAL]")
        (target / name).write_text(text, encoding="utf-8")
    save("MODEL_REQUEST.json", request)
    save("FOCUSED_CONTEXT.json", context.packet)
    save("SOURCE_CATALOG.json", context.evidence)
    save("FINANCIAL_OBSERVATIONS.json", context.observations)
    save("FINANCIAL_ANALYSIS.json", context.analysis)
    save("AUTHORED_MODEL_RESPONSE.json", {"label": "Authored mock, not actual Gemini output",
        "output": report.transport_output, "compact_payload": report.model_interpretation})
    save("AUTHORED_REPORT.json", {**json.loads(export_research_json(report)),
        "evaluation_mode": "authored_offline_rehearsal", "live_request_executed": False})
    (target / "AUTHORED_REPORT.md").write_text("AUTHORED OFFLINE REHEARSAL — NOT A LIVE MODEL REPORT\n\n" +
        export_research_markdown(report), encoding="utf-8")
    plan = {"authorised": False, "requires_explicit_user_approval": True, "new_live_requests": 0,
        "proposed_requests": 1, "feature": "Microsoft focused AI Research Briefing",
        "provider": config.provider, "model": config.model, "key_recognised": config.configured,
        "tier": "Owner-confirmed Free Tier with billing disabled; cannot be inferred from API key",
        "endpoint": GEMINI_BASE_URL + "chat/completions", "automatic_retries": False,
        "paid_fallback": False, "billing_changes": False, "max_output_tokens": request["max_tokens"],
        "data_mode": result.mode, "snapshot_retrieved_at": result.retrieved_at,
        "request_sha256": hashlib.sha256(json.dumps(request, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        "request_characters": len(json.dumps(request, ensure_ascii=False)),
        "context_characters": len(json.dumps(context.packet, ensure_ascii=False)), "actual_input_tokens": None,
        "observation_ids": list(context.observations), "passage_ids": list(context.packet["passages"]),
        "contract": report.contract, "transport": "native_flat_json", "primary_observation_id": context.packet["primary_observation_id"],
        "offline_rehearsal": "Passed original financial/source checks and strict compact schema with authored response; NOT live model quality proof",
        "validation_sequence": ["Validate native flat JSON fields", "Map field layout without adding content", "Validate compact Pydantic contract", "Resolve exact observation and passage IDs",
            "Assemble financial citations, periods and quotations in Python", "Run numerical, comparative, provenance and overclaim checks",
            "Save original response, report, usage and latency", "Analyst reviews meaning, alternatives and usefulness"],
        "stop_conditions": ["Any HTTP or local validation failure: save response and stop; no retry or thesis request"]}
    save("LIVE_REQUEST_PLAN.json", plan)
    return plan


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(ROOT / "outputs/focused_briefing_preparation"))
    parser.add_argument("--snapshot")
    parser.add_argument("--contract", choices=("focused_v2", "focused_v3"), default="focused_v3")
    args = parser.parse_args()
    p = prepare(args.output, args.snapshot, args.contract)
    print(json.dumps({key: p[key] for key in ("authorised", "new_live_requests", "provider", "model", "key_recognised",
        "data_mode", "request_characters", "context_characters", "automatic_retries", "paid_fallback")}, indent=2))
