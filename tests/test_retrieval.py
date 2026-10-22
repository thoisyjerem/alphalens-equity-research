"""Topic retrieval uses labelled synthetic prose, never invented financial data."""
from dataclasses import asdict

import pytest

from alphalens.filings import FilingExcerpt, extract_filing_excerpts
from alphalens.retrieval import RetrievedPassage, select_filing_passages


BACKGROUND = "Synthetic background describes the business without specific investment evidence. " * 100
MDNA_TOPICS = (
    "Synthetic test: capital expenditures and additions to property and equipment support infrastructure. "
    "Synthetic test: operating activities and cash from operations inform cash flows and liquidity. "
    "Synthetic test: depreciation and useful lives affect amortization assumptions. "
    "Synthetic test: operating leases, finance leases and purchase commitments require scrutiny. "
    "Synthetic test: Intelligent Cloud and Azure are segment drivers. "
    "Synthetic test: OpenAI partnership and Copilot developments need scrutiny. "
    "Synthetic test: gross margin, operating margin and cost of revenue inform operating income. "
)
RISK_TOPICS = (
    "Synthetic test: competition and competitive pricing include open source alternatives. "
    "Synthetic test: GPU supply, power, energy and datacenter capacity may constrain operations. "
)


def document(mdna=MDNA_TOPICS, risks=RISK_TOPICS):
    return f"""<html><body>
      <h2>ITEM 1A. RISK FACTORS</h2><p>{BACKGROUND}</p><p>{risks}</p>
      <h2>ITEM 1B. UNRESOLVED STAFF COMMENTS</h2><p>Excluded closing section.</p>
      <h2>ITEM 7. MANAGEMENT'S DISCUSSION AND ANALYSIS</h2><p>{BACKGROUND}</p><p>{mdna}</p>
      <h2>ITEM 7A. QUANTITATIVE AND QUALITATIVE DISCLOSURES ABOUT MARKET RISK</h2>
      <p>Excluded following section.</p></body></html>"""


def test_selects_relevant_late_disclosures_missed_by_head_truncation():
    html = document()
    old = extract_filing_excerpts(html)
    assert "capital expenditures" not in old["7"].text
    assert "GPU supply" not in old["1A"].text
    selected = select_filing_passages(html)
    text = " ".join(passage.text for passage in selected)
    for phrase in ("capital expenditures", "cash from operations", "depreciation", "finance leases",
                   "Intelligent Cloud", "OpenAI partnership", "gross margin", "competitive pricing", "GPU supply"):
        assert phrase in text
    assert all(passage.section_start > 6000 for passage in selected)


def test_passages_are_exact_bounded_nonoverlapping_section_substrings():
    html = document()
    sections = extract_filing_excerpts(html, max_chars=2_000_000)
    selected = select_filing_passages(html, max_passage_chars=500)
    assert selected
    for index, passage in enumerate(selected):
        assert isinstance(passage, RetrievedPassage)
        assert len(passage.text) <= 500
        assert passage.text == sections[passage.item].text[passage.section_start:passage.section_end]
        assert passage.original_chars == sections[passage.item].original_chars
        assert passage.selection_method == "deterministic_topic_windows_v1"
        assert passage.section_end - passage.section_start == len(passage.text)
        for other in selected[index + 1:]:
            if other.item == passage.item:
                assert passage.section_end <= other.section_start


def test_topic_selection_and_metadata_are_deterministic_and_serializable():
    html = document()
    first = select_filing_passages(html)
    second = select_filing_passages(html)
    assert first == second
    assert [asdict(passage) for passage in first] == [asdict(passage) for passage in second]
    topics = set(topic for passage in first for topic in passage.topics)
    assert topics == {"capital_intensity", "cash_generation", "depreciation", "leases_commitments",
                      "segment_drivers", "business_developments", "profitability", "competition", "capacity_constraints"}


def test_count_and_total_character_budget_are_enforced():
    selected = select_filing_passages(document(), max_passages=2, max_passage_chars=500,
                                     max_total_chars=700)
    assert 1 <= len(selected) <= 2
    assert sum(len(passage.text) for passage in selected) <= 700


def test_topic_filter_restricts_selection_without_relabelling_unrelated_text():
    selected = select_filing_passages(document(), topics=("depreciation",))
    assert selected
    assert all(passage.item == "7" and passage.topics == ("depreciation",) for passage in selected)
    assert all("depreciation" in passage.text or "amortization" in passage.text for passage in selected)


def test_duplicate_requested_topics_do_not_duplicate_passages():
    assert select_filing_passages(document(), topics=("depreciation", "depreciation")) == \
        select_filing_passages(document(), topics=("depreciation",))


def test_absent_topic_and_unverified_sections_do_not_use_whole_document_fallback():
    assert select_filing_passages("<p>Capital expenditures, depreciation and finance leases.</p>") == []
    assert select_filing_passages(document(mdna="No matched topic in this synthetic disclosure."),
                                   topics=("depreciation",)) == []
    unclosed = "<h2>ITEM 7. MANAGEMENT'S DISCUSSION AND ANALYSIS</h2><p>" + MDNA_TOPICS * 2 + "</p>"
    assert select_filing_passages(unclosed) == []


def test_hidden_content_is_never_retrieval_evidence():
    html = document(mdna="No selected topic here." +
                    "<script>depreciation useful lives finance leases</script>" +
                    "<div hidden>depreciation and amortization</div>")
    assert select_filing_passages(html, topics=("depreciation",)) == []


def test_oversized_sentence_is_bounded_with_explicit_boundary_flag():
    prose = ("Synthetic depreciation and useful lives require analysis " * 50).strip() + "."
    selected = select_filing_passages(document(mdna=prose), topics=("depreciation",),
                                     max_passage_chars=300, max_total_chars=1000)
    assert selected
    assert all(len(passage.text) <= 300 and passage.boundary_truncated for passage in selected)
    assert all(not passage.section_truncated for passage in selected)


def test_section_truncation_is_separate_from_sentence_boundary_cut(monkeypatch):
    text = "Depreciation and useful lives are described in this synthetic sentence. " * 4
    monkeypatch.setattr("alphalens.retrieval.extract_filing_excerpts", lambda *args, **kwargs: {
        "7": FilingExcerpt("7", "Management discussion", text, truncated=True,
                           original_chars=len(text) + 1000)})
    selected = select_filing_passages("Unused markup", topics=("depreciation",))
    assert selected and all(passage.section_truncated for passage in selected)
    assert all(not passage.boundary_truncated for passage in selected)


@pytest.mark.parametrize("name,value", [
    ("max_passages", 0), ("max_passages", 65), ("max_passages", True),
    ("max_passages", 1.5), ("max_passage_chars", 127), ("max_passage_chars", 1801),
    ("max_passage_chars", True), ("max_total_chars", 0), ("max_total_chars", 100001),
    ("max_total_chars", True),
])
def test_invalid_resource_limits_are_rejected(name, value):
    with pytest.raises(ValueError, match=name):
        select_filing_passages(document(), **{name: value})


@pytest.mark.parametrize("topics", [(), ("unrecognized_topic",), "depreciation"])
def test_invalid_topic_selection_is_rejected(topics):
    with pytest.raises(ValueError, match="topics"):
        select_filing_passages(document(), topics=topics)


def test_total_budget_cannot_silently_exclude_every_maximum_sized_window():
    with pytest.raises(ValueError, match="at least"):
        select_filing_passages(document(), max_total_chars=400, max_passage_chars=500)
