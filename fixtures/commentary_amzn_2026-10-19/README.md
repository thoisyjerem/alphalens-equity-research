# Amazon commentary regression fixture

This is a **test-only cached SEC snapshot**, extracted locally on 19 October 2026 from existing official SEC response caches. No network or model request was made to create it. It does not expand the dashboard’s Microsoft-only offline coverage.

`AMZN_SNAPSHOT.json` retains the original selected accounting concepts, units, annual periods, values, accession numbers, filing dates and SEC document links. `MANIFEST.json` records the original cache timestamps and hashes. Every selected source component was matched against its actual cached company-facts record before saving.

Reconstructing the snapshot with its original `live` mode reproduces the source fingerprint in the failed Amazon commentary audit of 19 October at 13:16:35 UTC. The test snapshot itself is labelled `offline`; this is not a fresh SEC download. The rejected model’s prose was not recorded, so the exact triggering word remains unknown.

The supported extractor returns cash capex and free cash flow as N/A for this evidence. These were not inferred from other tags. Only the supported revenue/operating-income development is selected for bound commentary. Model responses in the companion tests are authored simulations, not Gemini output.
