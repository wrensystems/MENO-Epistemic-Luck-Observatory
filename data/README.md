# Data availability

This directory intentionally contains **no claimed raw research dataset**.

`reported_suite_summary.json` is a machine-readable transcription of the checked-in
manuscript's reported settings, all 16 planned ledger rows (14 complete), counts,
token usage, costs and common ceiling scores. It records the source manuscript's
SHA-256 and source commit. It is **not** the original frozen suite manifest, raw
response corpus or an independent re-scoring of model responses.

Run `python -B tools/verify_reported_summary.py` from the package root to check
Decimal accounting, request/block counts, all seeds and randomized family order,
launch gates, the reported budget stop and aggregate score arithmetic. The tool
can additionally check the original manuscript bytes and ledger with
`--source-report PATH`. These checks cannot authenticate the reported observations.

The source snapshot includes a manuscript, planned-block ledger and selected
response excerpts. It does not include the authoritative original suite/campaign
archives, the 126 full raw model responses, journals or historical replay export.
Those unavailable materials cannot be reconstructed faithfully from the report.

Three activities must be kept separate:

1. **Instrument replication:** available source/tests reproduce deterministic world
   construction, oracle calculations, scoring rules and mock workflow behavior.
2. **New synthetic archive replay:** the quickstart creates new scripted responses
   and independently re-scores its own export without network access.
3. **Historical live-result reproduction:** not possible from this package alone,
   because the full frozen evidence and its original matching source are absent.

Any summary or ledger accompanying the manuscript is report-derived secondary
material, not raw observations or independent verification. Selected quotations
are examples only. The release makes no promise that the complete private evidence
will become available and does not imply that it has been inspected in this environment.

