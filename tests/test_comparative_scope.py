"""Bound historical acceleration checks to the metric actually being described."""
import json
from pathlib import Path

import pytest

from alphalens.providers import GeminiJSONEnvelope
from alphalens.quality import load_source_catalog
from alphalens.research import Claim, FinancialCitation, _comparative_issues


ROOT = Path(__file__).resolve().parents[1]


def catalog():
    return load_source_catalog(ROOT / "fixtures/gemini_http400/brief.request.json")


def claim(text, book, metrics, years=(2025, 2026)):
    citations = []
    for metric in metrics:
        for year in years:
            key = f"{year}:{metric}"
            source = book[key]
            citations.append(FinancialCitation(source_id=key, **{field: source[field] for field in
                ("value", "unit", "fiscal_year", "period_start", "period_end")}))
    return Claim(text=text, kind="inference", financial_citations=citations)


def test_actual_saved_accelerated_investment_does_not_assert_cash_flow_acceleration():
    saved = json.loads((ROOT / "fixtures/gemini_compact_limitations_failure/COMPLETE_RESPONSE.json")
                       .read_text(encoding="utf-8"))
    envelope = GeminiJSONEnvelope.model_validate_json(saved["choices"][0]["message"]["content"])
    sentence = json.loads(envelope.result_json)["findings"][0]["interpretation"]
    assert "reflecting accelerated investment" in sentence
    book = catalog()
    # Only this sentence's mechanical comparison is tested: its proposed cause
    # still requires analyst review, independently of correct period references.
    candidate = claim(sentence, book, ("operating_cash_flow", "capital_expenditure"))
    assert _comparative_issues(candidate, book) == []


@pytest.mark.parametrize("subject", ["Revenue", "Operating cash flow"])
@pytest.mark.parametrize("wording", ["{subject} growth accelerated during the latest annual period.",
    "Accelerating growth in {subject} warrants further research.",
    "{subject} has sharply accelerated during the latest annual period."])
def test_actual_metric_acceleration_still_requires_three_comparable_annuals(subject, wording):
    book = catalog()
    metric = "revenue" if subject == "Revenue" else "operating_cash_flow"
    sentence = wording.format(subject=subject)
    two_period = claim(sentence, book, (metric,))
    assert any("requires 3 consecutive annual periods" in issue
               for issue in _comparative_issues(two_period, book))
    # Synthetic positive-base sequences isolate grammar and interval checking;
    # these values are not presented as Microsoft financial results.
    for year, value in zip((2024, 2025, 2026), (100, 110, 140)):
        book[f"{year}:{metric}"]["value"] = value
    three_period = claim(sentence, book, (metric,), (2024, 2025, 2026))
    assert _comparative_issues(three_period, book) == []


@pytest.mark.parametrize("metric, subject", [("revenue", "Revenue"),
    ("operating_cash_flow", "Operating cash flow")])
def test_actual_declines_and_deceleration_still_cannot_contradict_data(metric, subject):
    book = catalog()
    for year, value in zip((2024, 2025, 2026), (100, 110, 140)):
        book[f"{year}:{metric}"]["value"] = value
    wrong_direction = claim(f"{subject} declined during the latest annual period.", book, (metric,))
    assert any("Comparative direction" in issue for issue in _comparative_issues(wrong_direction, book))
    wrong_acceleration = claim(f"{subject} growth decelerated during the latest annual period.",
                              book, (metric,), (2024, 2025, 2026))
    assert any("Comparative acceleration" in issue
               for issue in _comparative_issues(wrong_acceleration, book))


def test_unrelated_acceleration_does_not_excuse_wrong_cash_flow_direction():
    book = catalog()
    candidate = claim("Operating cash flow declined, reflecting accelerated investment in infrastructure.",
                      book, ("operating_cash_flow",))
    issues = _comparative_issues(candidate, book)
    assert any("Comparative direction" in issue for issue in issues)
    assert not any("requires 3" in issue for issue in issues)


def test_investment_acceleration_cannot_mask_contradictory_metric_deceleration():
    book = catalog()
    for year, value in zip((2024, 2025, 2026), (100, 110, 140)):
        book[f"{year}:revenue"]["value"] = value
    candidate = claim("Revenue growth decelerated, despite accelerated investment in infrastructure.",
                      book, ("revenue",), (2024, 2025, 2026))
    assert any("Comparative acceleration" in issue for issue in _comparative_issues(candidate, book))
