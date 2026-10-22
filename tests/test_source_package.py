"""Shareable source retains offline replay dependencies, not local secrets."""
import shutil
import subprocess
import sys
from uuid import uuid4
import zipfile

from scripts.package_source import BUNDLES, ROOT, ROOT_FILES, build_archive, source_paths


def test_packaged_source_replays_real_bundle_and_excludes_unlisted_local_files(tmp_path):
    source = tmp_path / "source"
    for path in source_paths(ROOT):
        target = source / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    sentinel = "private-local-value-" + uuid4().hex
    for relative in (".env", ".streamlit/secrets.toml", ".cache/private.json",
                     "outputs/unrelated/research.json", "fixtures/.env"):
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(sentinel, encoding="utf-8")
    optional = source / "outputs/msft_findings_live_2026-10-18"
    optional.mkdir(parents=True, exist_ok=True)
    (optional / "REVIEW_NOTES.md").write_text("Explicit optional public review.", encoding="utf-8")
    (optional / "local_private_notes.md").write_text(sentinel, encoding="utf-8")
    archive_path = build_archive(source, tmp_path / "AlphaLens_source.zip")
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        assert set(ROOT_FILES) <= names
        assert "docs/DEVELOPMENT_HISTORY.md" in names
        assert "outputs/msft_findings_live_2026-10-18/REVIEW_NOTES.md" in names
        for directory in ("msft_flat_live_2026-10-17", "msft_recovery_live_2026-10-18"):
            assert {f"outputs/{directory}/{name}" for name in BUNDLES[directory]} <= names
        assert all(sentinel.encode() not in archive.read(name) for name in names)
        assert all("__pycache__" not in name and not name.endswith(".pyc") for name in names)
        extracted = tmp_path / "extracted"
        archive.extractall(extracted)
    # Use installed dependencies, but import the archive's source and public
    # replay records. Any actual network attempt is an explicit test failure.
    code = """
import httpx
import requests
def forbidden(*args, **kwargs):
    raise AssertionError('Packaged saved replay attempted network access')
httpx.HTTPTransport.handle_request = forbidden
requests.Session.request = forbidden
from alphalens.saved_research import load_saved_briefing
from alphalens.research_exports import export_research_json
report = load_saved_briefing('outputs/msft_flat_live_2026-10-17')
assert report.verification.unsupported_count == 0
assert report.contract == 'focused_v2'
assert 'raw_model_output' in export_research_json(report)
print('PACKAGED_OFFLINE_REPLAY_PASSED')
"""
    result = subprocess.run([sys.executable, "-c", code], cwd=extracted,
                            capture_output=True, text=True, timeout=60, check=False)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "PACKAGED_OFFLINE_REPLAY_PASSED"
