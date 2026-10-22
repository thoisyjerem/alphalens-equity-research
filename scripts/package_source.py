"""Package the reviewed portfolio source and reproducible research records.

Historical scratch outputs, local credentials, caches and release archives are
excluded. Recorded financial/model evidence is retained for the regression suite.
"""
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = (
    "app.py", "README.md", "EVALUATION.md", "DEMO.md", "EXPLAIN_THE_CODE.md",
    "ALPHALENS_V1_1_EVALUATION.md", "requirements.txt", "requirements.lock.txt",
    "pyproject.toml", ".gitignore", ".gitattributes", ".env.example", "setup.ps1", "run.ps1", "test.ps1",
)
OUTPUT_REPORTS = ()
RESEARCH_BUNDLE_FILES = (
    "SOURCE_CATALOG.json", "FINANCIAL_ANALYSIS.json", "FINANCIAL_OBSERVATIONS.json",
    "FOCUSED_CONTEXT.json", "TRANSPORT_OUTPUT.json", "MODEL_INTERPRETATION.json",
    "ASSEMBLED_REPORT.json", "VALIDATION.json", "REQUEST_LEDGER.json", "RESEARCH_BRIEFING.json",
    "RESEARCH_BRIEFING.md", "DEMO_MANIFEST.json", "COMPLETE_RESPONSE.json", "MODEL_REQUEST.json",
    "ANALYST_REVIEW.md", "REVIEW_NOTES.md", "INDEPENDENT_CHECKS.json",
)
BUNDLES = {
    "msft_flat_live_2026-10-17": RESEARCH_BUNDLE_FILES,
    "msft_recovery_live_2026-10-18": (
        "COMPLETE_RESPONSE.json", "SOURCE_CATALOG.json", "REJECTED_ASSEMBLED_REPORT.json",
        "ANALYST_REVIEW.md", "FAILURE.json", "VALIDATION_DIAGNOSTIC.json", "REQUEST_LEDGER.json",
        "MODEL_REQUEST.json", "FOCUSED_CONTEXT.json", "FINANCIAL_ANALYSIS.json", "FINANCIAL_OBSERVATIONS.json",
    ),
    "msft_findings_live_2026-10-18": (*RESEARCH_BUNDLE_FILES,
        "MICROSOFT_RESEARCH_NOTE.md", "MECHANICAL_EVALUATION.json", "MECHANICAL_EVALUATION.md"),
    "offline_jhi_review_2026-10-20": (
        "INDEPENDENT_RESEARCH_REVIEW.md", "SUPPLEMENTARY_REVIEWER_CALCULATIONS.json",
        "INDEPENDENT_VERIFICATION.json",
    ),
    "v1_1_2026-10-21": (
        "BASELINE_TESTS.xml", "INTEGRATION_TESTS.xml", "FINAL_TESTS.xml", "PACKAGE_TEST.xml",
        "MICROSOFT_REVIEW.md", "RUBRIC.json", "MICROSOFT_REASONING.json", "ANALYTICAL_REVIEW.json",
        "MICROSOFT_NOTE.md", "MICROSOFT_AUDIT.json", "FINAL_VERIFICATION.json",
        "visa/company_tickers.json", "visa/visa_submissions.json", "visa/visa_companyfacts.json",
        "visa/visa_latest_10k.html", "visa/PROVENANCE.json", "visa/FILING_PROVENANCE.json",
        "visa/REVIEW_PASSAGES.json", "visa/VALIDATION.json", "visa/VISA_EVIDENCE_REPORT.md",
        "visa/FINANCIAL_EVIDENCE.json", "visa/FINANCIAL_SNAPSHOT.json", "visa/FINANCIALS.csv",
    ),
    "publication_2026-10-21": ("TEST_RESULTS.xml", "CLEAN_COPY_TEST_RESULTS.xml", "VERIFICATION.json"),
}


def source_paths(root: Path) -> list[Path]:
    """Resolve the package inventory without reading local secrets."""
    root = Path(root)
    paths = {root / name for name in ROOT_FILES}
    for folder in ("alphalens", "scripts", "tests"):
        paths.update(path for path in (root / folder).rglob("*.py")
                     if path.is_file() and "__pycache__" not in path.parts)
    for folder, suffixes in (("fixtures", {".json", ".md", ".html"}), ("docs", {".md", ".png"})):
        paths.update(path for path in (root / folder).rglob("*")
                     if path.is_file() and path.suffix in suffixes)
    paths.add(root / ".streamlit/config.toml")
    paths.update(root / "outputs" / name for name in OUTPUT_REPORTS)
    for directory, names in BUNDLES.items():
        paths.update(root / "outputs" / directory / name for name in names)
    return sorted(path for path in paths if path.is_file())


def build_archive(root: Path = ROOT, target: Path | None = None) -> Path:
    root = Path(root)
    target = Path(target) if target is not None else root / "outputs/AlphaLens_source.zip"
    paths = source_paths(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            archive.write(path, path.relative_to(root).as_posix())
    with zipfile.ZipFile(target) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names))
        assert ".env" not in names and ".streamlit/secrets.toml" not in names
        assert not any(name.startswith((".venv/", "work/", ".cache/")) for name in names)
        assert archive.testzip() is None
    return target


if __name__ == "__main__":
    target = build_archive()
    with zipfile.ZipFile(target) as archive:
        count = len(archive.namelist())
    print(f"Created {target.name}: {count} files; local configuration and caches excluded")
