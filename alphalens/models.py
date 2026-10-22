"""Small, serialisable research data models shared by the app and extractors."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SourceFact:
    concept: str
    unit: str
    value: float
    start: Optional[str]
    end: str
    accession: str
    filed: str
    form: str
    url: str


@dataclass
class MetricValue:
    value: Optional[float]
    unit: str
    sources: list[SourceFact] = field(default_factory=list)
    reason: str = ""


@dataclass
class AnnualPeriod:
    fiscal_year: int
    start: str
    end: str
    metrics: dict[str, MetricValue] = field(default_factory=dict)


@dataclass
class ResearchResult:
    ticker: str
    name: str
    cik: str
    periods: list[AnnualPeriod]
    mode: str
    retrieved_at: str
    warnings: list[str] = field(default_factory=list)
    filings: list[dict] = field(default_factory=list)
