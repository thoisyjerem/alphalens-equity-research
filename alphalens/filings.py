"""Conservative, local extraction of two bounded 10-K narrative excerpts.

This module does not fetch documents, calculate financial figures or summarize
text. A section must have recognizable visible Item/title headings and a closing
Item heading. Missing or ambiguous boundaries produce an explicit N/A reason.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
import re

from bs4 import BeautifulSoup, Comment, Declaration, Doctype, NavigableString, ProcessingInstruction, Tag


@dataclass(frozen=True)
class FilingExcerpt:
    item: str
    title: str
    text: str
    reason: str = ""
    truncated: bool = False
    original_chars: int = 0


_SECTIONS = {
    "1A": (
        "Risk factors",
        r"\bITEM\s*1\s*A\b\s*[.\-–—:]?\s*RISK\s+FACTORS\b",
        r"\bITEM\s*1\s*B\b\s*[.\-–—:]?\s*UNRESOLVED\s+STAFF\s+COMMENTS\b",
        "Item 1B — Unresolved staff comments",
    ),
    "7": (
        "Management's discussion and analysis",
        r"\bITEM\s*7\b\s*[.\-–—:]?\s*MANAGEMENT[’']?S\s+DISCUSSION\s+AND\s+ANALYSIS\b",
        r"\bITEM\s*7\s*A\b\s*[.\-–—:]?\s*QUANTITATIVE\s+AND\s+QUALITATIVE\s+DISCLOSURES\s+ABOUT\s+MARKET\s+RISK\b",
        "Item 7A — Quantitative and qualitative disclosures about market risk",
    ),
}
_HIDDEN_STYLE = re.compile(r"(?:display\s*:\s*none|visibility\s*:\s*hidden)", re.I)
_BLOCKS = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "td", "th", "li", "section", "article", "pre"}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _visible_document(html: str | bytes):
    if isinstance(html, bytes):
        # A downloaded filing may be saved as UTF-8 while retaining an original
        # XML ASCII declaration. Valid UTF-8 bytes should not lose apostrophes.
        try:
            html = html.decode("utf-8-sig")
        except UnicodeDecodeError:
            pass  # Let BeautifulSoup detect a genuinely different encoding.
    soup = BeautifulSoup(html, "html.parser")
    # Hidden inline XBRL metadata can contain duplicate facts and references.
    # Parent removal invalidates descendants, so guard decomposed nodes.
    for element in list(soup.find_all(True)):
        if element.name is None or element.attrs is None:
            continue
        name = element.name.lower()
        if (name in {"script", "style", "noscript", "template"}
                or name.endswith(":hidden") or name == "ix:header"
                or element.has_attr("hidden")
                or str(element.get("aria-hidden", "")).lower() == "true"
                or _HIDDEN_STYLE.search(str(element.get("style", "")))):
            element.decompose()
    pieces, starts, nodes = [], [], []
    position = 0
    previous_raw, previous_block = "", None
    pending_space = False
    for node in soup.find_all(string=True):
        if (not isinstance(node, NavigableString)
                or isinstance(node, (Comment, Declaration, Doctype, ProcessingInstruction))):
            continue
        raw = str(node)
        value = _normalize(raw)
        if not value:
            pending_space = pending_space or bool(raw)
            continue
        block = next((parent for parent in node.parents if parent.name in _BLOCKS), node.parent)
        separated = bool(pieces) and (
            pending_space or raw[0].isspace() or previous_raw[-1].isspace()
            or block is not previous_block
        )
        if separated:
            pieces.append(" ")
            position += 1
        starts.append(position)
        nodes.append(node)
        pieces.append(value)
        position += len(value)
        previous_raw, previous_block, pending_space = raw, block, False
    return "".join(pieces), starts, nodes


def _heading_positions(text: str, starts: list[int], nodes: list[NavigableString], pattern: str):
    positions = []
    for match in re.finditer(pattern, text, flags=re.I):
        # Require the complete Item/title to begin a short DOM element. This
        # excludes prose such as "see Item 7A. Quantitative ..." while allowing
        # headings split across spans or adjacent table cells.
        node_index = bisect_right(starts, match.start()) - 1
        if node_index < 0:
            continue
        matched = re.sub(r"\s+", "", match.group()).casefold()
        parent = nodes[node_index].parent
        while isinstance(parent, Tag) and parent.name not in {"body", "html", "[document]"}:
            candidate = _normalize(parent.get_text("", strip=False))
            if len(candidate) > 450:
                break
            if re.sub(r"\s+", "", candidate).casefold().startswith(matched):
                positions.append((match.start(), match.end()))
                break
            parent = parent.parent
    return positions


def extract_filing_excerpts(
    html: str | bytes,
    max_chars: int = 6000,
    min_section_chars: int = 200,
) -> dict[str, FilingExcerpt]:
    """Return visible, bounded Item 1A/7 excerpts, or specific N/A explanations.

    This is an intentionally conservative heading parser, not a universal SEC
    document parser. It never treats a table of contents or a whole document as
    a missing section. Truncation is disclosed separately from original length.
    Source URL, accession and retrieval metadata belong to the calling service.
    """
    if not isinstance(max_chars, int) or isinstance(max_chars, bool) or max_chars < 1:
        raise ValueError("max_chars must be a positive integer")
    if (not isinstance(min_section_chars, int) or isinstance(min_section_chars, bool)
            or min_section_chars < 1):
        raise ValueError("min_section_chars must be a positive integer")
    if not isinstance(html, (str, bytes)):
        raise TypeError("html must be a string or bytes")
    text, offsets, nodes = _visible_document(html)
    output = {}
    for item, (title, start_pattern, end_pattern, end_title) in _SECTIONS.items():
        beginning = _heading_positions(text, offsets, nodes, start_pattern)
        ending = _heading_positions(text, offsets, nodes, end_pattern)
        candidates = []
        for start, _ in beginning:
            end = next((position for position, _ in ending if position > start), None)
            if end is None:
                continue
            # If a TOC entry has no matching TOC boundary, it must not swallow
            # the entire filing up to the real section's boundary.
            if any(start < repeated < end for repeated, _ in beginning):
                continue
            candidate = _normalize(text[start:end])
            if len(candidate) >= min_section_chars:
                candidates.append(candidate)
        if not beginning:
            reason = f"N/A — recognizable visible Item {item} {title} heading was not found."
        elif not ending:
            reason = f"N/A — {end_title} closing heading was not found; the section boundary cannot be verified."
        elif not candidates:
            reason = f"N/A — no substantial bounded Item {item} section was found; table-of-contents entries and short heading matches are excluded."
        else:
            selected = max(candidates, key=len)
            output[item] = FilingExcerpt(
                item=item, title=title, text=selected[:max_chars],
                truncated=len(selected) > max_chars, original_chars=len(selected),
            )
            continue
        output[item] = FilingExcerpt(item=item, title=title, text="", reason=reason)
    return output
