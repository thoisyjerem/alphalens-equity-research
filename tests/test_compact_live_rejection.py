"""Replay the actual single approved compact briefing; no live requests or repair."""
from copy import deepcopy
import json
from pathlib import Path

from pydantic import ValidationError
import pytest

from alphalens.focused_briefing import BriefingInterpretation, assemble_briefing, build_briefing_context
from alphalens.providers import GeminiJSONEnvelope
from alphalens.service import load_offline_filing_context, load_research


def rejected_response():
    path = Path(__file__).resolve().parents[1] / "fixtures/gemini_compact_limitations_failure/COMPLETE_RESPONSE.json"
    complete = json.loads(path.read_text(encoding="utf-8"))
    envelope = GeminiJSONEnvelope.model_validate_json(complete["choices"][0]["message"]["content"])
    return json.loads(envelope.result_json)


def test_actual_compact_response_rejects_all_three_list_valued_limitations():
    payload = rejected_response()
    original = deepcopy(payload)
    with pytest.raises(ValidationError) as caught:
        BriefingInterpretation.model_validate(payload)
    assert {(tuple(issue["loc"]), issue["type"]) for issue in caught.value.errors()} == {
        (("findings", 0, "limitations"), "string_type"),
        (("findings", 1, "limitations"), "string_type"),
        (("risks", 0, "limitations"), "string_type"),
    }
    assert payload == original  # No silent joining, defaults or substantive repair.


def test_fixing_only_limitations_types_cannot_bypass_missing_cash_divergence():
    payload = rejected_response()
    # Explicit counterfactual test only. The real rejected output is never rewritten
    # or accepted. Isolate the next guard using authored type-correct placeholder text.
    for row in payload["findings"] + payload["risks"]:
        row["limitations"] = "This authored counterfactual isolates a later validation guard."
    parsed = BriefingInterpretation.model_validate(payload)
    result = load_research("MSFT", "offline")
    context = build_briefing_context(result, [load_offline_filing_context(result)])
    assert "2026:cash_flow_divergence" in context.observations
    with pytest.raises(ValueError, match="cash-flow divergence was omitted"):
        assemble_briefing(parsed, context)
