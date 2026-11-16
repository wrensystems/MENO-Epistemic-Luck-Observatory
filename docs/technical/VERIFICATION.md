# Release verification record

Verified in the supplied Linux environment, Python 3.12. This is not a claim of
fresh Windows/macOS deployment or a replay of the missing historical raw dataset.

## Public entrypoint

Three new regression tests were first run against the missing public entrypoint:
all three failed as expected. After adding the thin wrapper, all three passed.
They exercise public help, handled invalid paths, create/plan/run/verify/status,
local export and independent replay of a new nine-trial scripted campaign.

## Full released test suite

Command: `python -B -m unittest discover -s tests -v`.

Initial standalone-package result: **105 tests passed**, 17.219 seconds, exit code 0.
Coverage includes world/oracle golden fixtures, visibility and factual parity,
response scoring, block inference, budget boundaries, durable records, source
guards, interrupted/uncertain outcomes, no automatic MENO retries, suite coverage,
campaign/suite replay, local read-only Observatory and offline provider contracts.

An initial packaging run failed to import `test_openai` because the minimal
allowlist omitted generic CLI helpers used by that existing test module. The
generic `cli.py` and its `publication.py` dependency were then included unchanged;
the complete run above passed. No scientific test was removed or weakened.

## Network-blocked smoke check

Command: `python -B tools/offline_smoke.py`.

Result: exit code 0, nine completed synthetic trials, USD 0 observed cost;
generation/export occurred with socket connections blocked. A separate read-only
replay process printed `VERIFIED: archived requests, response rescoring and block
analysis replay; not provider authenticity`. Temporary synthetic archives were
discarded at completion. No credentials or paid generations were used.

The ZIP was separately extracted to a fresh temporary directory. All 47
then-inventoried files matched their SHA-256 values; public help and the same
network-blocked smoke/replay command also succeeded from the extracted copy.

## Packaging boundaries

All scientific source files except the two display/CLI-label changes are retained
byte-for-byte. `SOURCE_PROVENANCE.json` provides original/package SHA-256 values.
`SHA256.json` inventories delivered files except itself; it must be regenerated if
publication artifacts are subsequently inserted. The ZIP builder validates the
ZIP CRC and excludes credentials, Git history, bytecode, private runs and exports.

All packaged original Python modules were additionally checked against the Git
blob SHA-1 values supplied for the source snapshot. The retained scientific code
matched. Three excluded historical planning/specification Markdown documents in
the supplied text snapshot did not match their tree hashes; none is distributed
or used by the instrument. The release does not claim byte-for-byte completeness
of the broader private repository snapshot.

Tests establish software behavior and internal consistency. They do not validate
provider authenticity, establish independent human replication or recover absent
raw responses. No Git repository was created/pushed and no visibility was changed.

## Report-derived accounting extension

Two additional regression tests cover the checked-in report transcription and
reject eight mutations: changed block cost, world seed, family order, launch gate,
unlaunched attempt count, aggregate request count, frozen regime and per-block B.
Both tests passed in 0.823 seconds after a demonstrated missing-verifier failure.

`python -B tools/verify_reported_summary.py --source-report ORIGINAL_MANUSCRIPT.md`
passed using the original checked-in report bytes. It verified the report SHA-256,
all 16 exact ledger transcriptions, seeded order and seeds, 14 completed rows,
126 attempts, USD 6.94651 cost, USD 3.13344 reservation and USD 10.07995 next gate.
The same accounting check works without the optional original manuscript file.
This is reported-number accounting, not a raw-response or original-manifest replay.

## Final integrated package

After adding the accounting extension and final report/presentation artifacts,
the full released suite was rerun against the frozen source tree: **107 tests
passed in 15.978 seconds**, exit code 0. The network-blocked nine-trial synthetic
smoke/export/replay and report-derived accounting verifier both passed again.
The earlier 107-test count quoted in the manuscript describes the historical
private experiment code; this fresh count concerns the separately packaged code.

The final research PDF has seven pages (five main-text pages), a 202-word abstract,
and the required ethics appendix. All pages were visually inspected, including
the native equation and ledger. The presentation has twelve slides with editable
native tables/chart and speaker notes. Its PPTX passed structural, layout, font
and import-roundtrip checks; both PPTX renders and PDF pages were inspected.
No native desktop PowerPoint or fresh Windows/macOS run was performed.
