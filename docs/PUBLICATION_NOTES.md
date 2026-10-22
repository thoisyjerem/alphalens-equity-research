# Publication provenance and privacy notes

This repository is a reviewed publication copy of an existing local development project. The original local files are preserved.

## Genuine evidence and model output

Original SEC payloads, filing passages, financial facts, generated model text and canonical assembled research reports are copied without alteration. Recorded model output remains distinguishable from subsequent Python calculations and reviewer commentary. No new model request was made to prepare this copy.

## Request-diagnostic privacy derivatives

Only `audit_path` keys were removed recursively from the three historical Microsoft request ledgers and the recovery bundle's failure diagnostic. These keys recorded local diagnostic file locations, not financial evidence or model interpretations. All other fields were retained. Where a demonstration manifest covers a changed ledger, only that ledger's hash entry was updated; all other manifest metadata and hashes were preserved.

The following fingerprints identify the original local ledger bytes and the corresponding publication bytes without exposing private paths.

| Repository record | Original SHA-256 | Publication SHA-256 | Removed fields |
|---|---|---|---:|
| `outputs/msft_flat_live_2026-10-17/REQUEST_LEDGER.json` | `ffe5a1e8d3e40566cbd72737ca925a16b5f4be478bf90155bd57bf40b1520ed8` | `c3a43bd6947c91f75081c3e15c1a20007689923cc542e254c89d83b4232b68f4` | 1 |
| `outputs/msft_recovery_live_2026-10-18/REQUEST_LEDGER.json` | `0a34b6cb23cc6b476200ac8773cd92b862398ce2a566aaa05815495a5961c3f5` | `8ff8d14bb06fa899ea379f7e8641378fa4566849f4763eac126b41b63b26f7f7` | 1 |
| `outputs/msft_findings_live_2026-10-18/REQUEST_LEDGER.json` | `1a5489bcab24be3c1ef87ede9d1ff9b2fe0c209dbb486ddcf58a8b8ec895be98` | `b29f38b8366a7639abd80c110daed14b2422a13bd460c9681d8ded4e02df6853` | 1 |
| `outputs/msft_recovery_live_2026-10-18/FAILURE.json` | `dabe5755649d9533a6082a6b23c71703244ed9f3a7f6e4413f18448080d77ef3` | `2d4eda46eb621cfae4a667cc9cf77b42070f51a06ea1de0b43ea47dcb010475c` | 1 |

## Verification logs

Included JUnit logs are publication copies. Machine hostname attributes were removed, and any development-project absolute Windows prefixes were replaced by `.`. Test counts, outcomes, financial values and recorded execution durations were not edited.

Reviewed XML records: 6, including the separate clean-copy execution result. These engineering results do not establish the correctness of every investment interpretation.

## Independent review metadata

Only `hostname` keys were removed recursively from the explicitly named independent-review JSON records below. No financial facts, model fields, numerical checks or review findings were changed. The original local records remain preserved.

| Repository review record | Original SHA-256 | Publication SHA-256 | Removed fields |
|---|---|---|---:|
| `outputs/v1_1_2026-10-21/FINAL_VERIFICATION.json` | `3fc9513564085baaafb1b9f5c68aab1dd5da2b5c896799cdd12668cd45be224b` | `847da85575d1d1c6b61ba91534fe58f76820c3d7ae49fbac78196d2d2a8b25a7` | 1 |
| `outputs/offline_jhi_review_2026-10-20/INDEPENDENT_VERIFICATION.json` | `c8d225d3abcd2a5a6694b95a0659922eae1cd58290bf21fc01c92888e54df013` | `c8d225d3abcd2a5a6694b95a0659922eae1cd58290bf21fc01c92888e54df013` | 0 |

## Git checkout integrity

`.gitattributes` retains exact bytes for the hashed `outputs/` and `fixtures/` records and PNG images. Source text uses LF line endings. This prevents Windows Git newline conversion from invalidating recorded-evidence fingerprints.

## Exclusions

Credentials, `.env`, virtual environments, caches, local work, unreviewed outputs and large development archives are excluded. Corporate contact details appearing inside original public SEC filings are part of the source records and are not private project configuration.

No open-source licence has been selected. Repository visibility and licensing remain the author's decision.
