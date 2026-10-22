"""Bounded, deterministic topic retrieval within verified SEC filing sections.

No network or model calls occur here. Selected text is copied exactly from the
visible, normalized Item 1A/7 section, with section-relative offsets. Topic
labels describe retrieval intent; they do not verify a statement or imply that
the selected windows contain every relevant company disclosure. The original
filing reader and its head excerpts remain available unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from alphalens.filings import extract_filing_excerpts


@dataclass(frozen=True)
class RetrievedPassage:
    item: str
    title: str
    text: str
    section_start: int
    section_end: int
    original_chars: int
    topics: tuple[str, ...]
    boundary_truncated: bool = False
    section_truncated: bool = False
    selection_method: str = "deterministic_topic_windows_v1"


_TOPICS = {
    "capital_intensity": ("7", {"capital expenditures": 10, "additions to property": 9,
        "property and equipment": 5, "infrastructure": 1, "datacenter": 1}),
    "cash_generation": ("7", {"cash from operations": 10, "operating activities": 9,
        "cash flows": 5, "liquidity": 3, "cash used in investing": 8}),
    "depreciation": ("7", {"depreciation": 10, "useful lives": 12, "amortization": 3}),
    "leases_commitments": ("7", {"finance leases": 12, "finance lease": 12,
        "operating leases": 10, "operating lease": 10, "purchase commitments": 9,
        "lease liabilities": 10, "commitments": 2}),
    "segment_drivers": ("7", {"intelligent cloud": 6, "azure": 6,
        "productivity and business processes": 5, "more personal computing": 5,
        "segment": 2}),
    "business_developments": ("7", {"openai": 12, "partnership": 10,
        "remaining performance obligation": 6, "copilot": 6}),
    "profitability": ("7", {"gross margin": 9, "operating margin": 9,
        "operating income": 5, "cost of revenue": 4}),
    "competition": ("1A", {"competition": 6, "competitive": 5, "competing": 4,
        "open source": 5, "open-source": 5, "pricing": 3}),
    "capacity_constraints": ("1A", {"gpu": 8, "energy": 6, "power": 6,
        "supply": 5, "datacenter": 4, "capacity": 4}),
}


def _score(text: str, item: str, topics: tuple[str, ...]) -> dict[str, int]:
    scores = {}
    for topic in topics:
        target_item, phrases = _TOPICS[topic]
        if item != target_item:
            continue
        score = sum(weight * min(3, len(re.findall(r"\b" + re.escape(phrase) + r"\b", text, re.I)))
                    for phrase, weight in phrases.items())
        if score:
            scores[topic] = score
    return scores


def _windows(text: str, limit: int):
    """Contiguous sentence windows, with disclosed cuts for oversized sentences."""
    starts = [0] + [match.end() for match in re.finditer(r"(?<=[.!?])\s+(?=[A-Z(])", text)]
    spans = [(start, starts[index + 1] if index + 1 < len(starts) else len(text))
             for index, start in enumerate(starts)]
    seen = set()
    for index, (start, sentence_end) in enumerate(spans):
        if sentence_end - start > limit:
            # Long table/prose blocks have no reliable sentence boundaries.
            cursor = start
            while cursor < sentence_end:
                end = min(cursor + limit, sentence_end)
                if end < sentence_end:
                    split = text.rfind(" ", cursor + limit // 2, end)
                    if split > cursor:
                        end = split + 1
                if (cursor, end) not in seen:
                    seen.add((cursor, end))
                    yield cursor, end, True
                cursor = end
            continue
        end = sentence_end
        for _, next_end in spans[index + 1:]:
            if next_end - start > limit:
                break
            end = next_end
        if (start, end) not in seen:
            seen.add((start, end))
            yield start, end, False


def select_filing_passages(html: str | bytes, *, max_passages: int = 12,
                           max_passage_chars: int = 1500, max_total_chars: int = 18000,
                           topics: tuple[str, ...] | None = None) -> list[RetrievedPassage]:
    """Return nonoverlapping source windows covering the requested topics.

    A weighted lexical sweep first seeks a relevant window for each topic,
    then fills the remaining passage/character budget. This deliberately small
    selector has no vector store or inferred facts. It can miss relevant text,
    and an absent topic is not proof that the issuer has made no disclosure.
    Oversized sentences/tables are cut at whitespace and explicitly labelled.
    Missing verified section boundaries yield no passages for that section.
    """
    for name, value, lower, upper in (("max_passages", max_passages, 1, 64),
            ("max_passage_chars", max_passage_chars, 128, 1800),
            ("max_total_chars", max_total_chars, 128, 100000)):
        if isinstance(value, bool) or not isinstance(value, int) or not lower <= value <= upper:
            raise ValueError(f"{name} must be an integer between {lower} and {upper}")
    if max_total_chars < max_passage_chars:
        raise ValueError("max_total_chars must be at least max_passage_chars")
    if isinstance(topics, str):
        raise ValueError("topics must be a collection of supported topic names")
    requested = tuple(_TOPICS) if topics is None else tuple(dict.fromkeys(topics))
    if not requested or any(topic not in _TOPICS for topic in requested):
        raise ValueError("topics must name at least one supported filing research topic")
    sections = extract_filing_excerpts(html, max_chars=2_000_000)
    candidates = []
    for item, section in sections.items():
        if section.reason or not section.text:
            continue
        for start, end, cut in _windows(section.text, max_passage_chars):
            text = section.text[start:end]
            scores = _score(text, item, requested)
            if scores:
                candidates.append((RetrievedPassage(item, section.title, text, start, end,
                                   section.original_chars, tuple(scores), cut, section.truncated), scores))
    chosen = []
    used_chars = 0

    def eligible(candidate):
        passage = candidate[0]
        return (len(chosen) < max_passages and used_chars + len(passage.text) <= max_total_chars
                and all(passage.item != old.item or passage.section_end <= old.section_start
                        or old.section_end <= passage.section_start for old, _ in chosen))

    def ranking(candidate, topic=None):
        passage, scores = candidate
        # Phrase score density prevents a long generic window winning solely
        # because it contains more words. Ties keep the earliest source offset.
        score = scores.get(topic, 0) if topic else sum(scores.values())
        return (score / max(400, len(passage.text)), score,
                -len(passage.text), -passage.section_start)

    # First cover each available requested topic; then add further nonoverlap
    # detail. Every selected topic is a retrieval label, not a verified claim.
    for topic in requested:
        options = [candidate for candidate in candidates if topic in candidate[1] and eligible(candidate)]
        if options:
            candidate = max(options, key=lambda row: ranking(row, topic))
            chosen.append(candidate)
            used_chars += len(candidate[0].text)
    while len(chosen) < max_passages:
        options = [candidate for candidate in candidates if eligible(candidate)]
        if not options:
            break
        candidate = max(options, key=ranking)
        chosen.append(candidate)
        used_chars += len(candidate[0].text)
    return [passage for passage, _ in sorted(chosen, key=lambda row: (row[0].item, row[0].section_start))]
