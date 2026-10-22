# Genuine offline SEC snapshot

These files are real, complete SEC responses captured on 16 October 2026 using
an identified request and the user's own SEC contact configuration. They are
retained byte-for-byte; no facts, dates, concepts, filings or values were added.
The contact identifier and API keys are not included.

The application must explicitly label this snapshot **offline demonstration**.
It is a fixed copy, never a substitute for successful live retrieval. Microsoft's
latest three completed annual fiscal periods present in this snapshot end on
30 June 2024, 2025 and 2026. Apple and Amazon have verified SEC ticker mappings
but do not have checked-in financial fixtures.

`manifest.json` records original URLs, capture timestamps, SHA-256 hashes and
limitations. `sources/` retains Microsoft's official FY2024 and FY2025 annual
report HTML for an independent cross-check of historical statement rows.
`tests/test_fixture_integrity.py` reconciles SEC facts to those source tables,
including the distinction between positive XBRL cash-capex payments and negative
cash-flow statement outflows. The reports are independent cross-checks, not a
manually constructed replacement for SEC facts.

To refresh fixtures, first retrieve the official SEC endpoints with a legitimate
`SEC_USER_AGENT` and conservative rate limits. Stage exact raw responses under
`work/sec_raw/`, then run `python work/package_sec_fixtures.py` and all tests.
Review changes to snapshot dates, filing metadata, source rows and hashes.
