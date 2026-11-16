# Technical reproducibility and archival compatibility

## Scope and source preservation

The retained Python modules use their original `research_lab` import namespace
and `meno2_*.py` filenames. Schema/oracle/renderer version strings such as
`meno2-scm-1`, `meno2-exact-enumeration-1`, `meno2-visible-records-1`,
`meno2-suite-1` and scoring/analysis version `meno2-2` remain unchanged.
These are technical archival identifiers, not public product branding. Renaming
them would alter archive parsing, source hashes or provenance interpretation.

The public command is `python -m meno`; it dispatches to the preserved campaign
CLI and gives its parser the public command label. Scientific imports and generated
archive schemas are unchanged. The generic legacy CLI/publication helpers remain
importable for existing provider-contract tests and code compatibility; no
platform-wide `research_lab.__main__` entrypoint or unrelated study is included.

`SOURCE_PROVENANCE.json` lists copied source paths and SHA-256 hashes for original
and packaged bytes. Any modified display/CLI source is explicitly distinguishable.
The published source commit is a provenance identifier, not a claim that this
minimal package matches all original collection-environment hashes.

## Fresh offline replication

Use Python 3.11+ and run the commands in the root README from the extracted package.
The test runner is `python -B -m unittest discover -s tests -v`; no test framework
installation is needed. Provider unit tests inject offline transports. Observatory
tests use only the loopback interface. No real model endpoint is required.

The quickstart uses only the mock provider. Do not supply `--live` for that example;
the engine rejects a mock/live mismatch. Campaign/output directories must be new.
Expected final status has nine completed trials and `evidence_kind=synthetic`.
The mock's predetermined verification responses intentionally do not replicate
historical model decisions or establish scientific performance.

`create` freezes source, inputs, generated worlds, schedule and protocol. `plan`
discloses request/reservation counts. `run` creates hash-chained durable invocation
records. `verify` and `analyze` inspect without rewriting evidence. `export` creates
a separate local replay candidate; its `reproduce.py` verifies hashes, independently
re-scores responses and compares aggregate analysis. It is not provider-authenticated
provenance and does not prove a privileged user could not rewrite all hashes.

For suites, use `suite-create DIRECTORY --config CONFIG`, `suite-run DIRECTORY`,
`suite-analyze DIRECTORY`, and `suite-export DIRECTORY DESTINATION`. A suite config
contains `configurations`, `cap_usd` and optional `metadata`. Each configuration
describes one independent block with a unique seed and a single model; settings
must match except seed/mechanism. The original prospective live design is retained
in `PROTOCOL.md`; its checklist is historical planning, not release completion status.

## Historical evidence limitations

Historical report numbers are not re-derived here: authoritative raw suite/run
archives and old standalone replay are absent. Full-precision seeds/ledger entries
in the manuscript can support world reconstruction, not recovery of missing model
responses. Alias names and stochastic generation cannot reconstruct prior outputs.

The engine hashes **every `.py` file in its package**. This minimal release omits
unrelated private modules and changes display bytes, so its source inventory differs
from a historical campaign's frozen inventory. Never replace a historical
`source_hashes` field, snapshot, seal or journal to force a match. Fresh collection
must use a fresh campaign. Exact historical replay requires the original sealed
evidence and matching archived code, neither supplied here. Read-only rescoring
with current code, where possible, must be identified as such and is not archival
resume/export compatibility. Existing exports retain their embedded semantics.

## Interpretation safeguards

Keep block versus request denominators, all-planned versus completed summaries,
and source validity versus publication decision separate. The reported degenerate
bootstrap interval at a ceiling does not establish equivalence. Budget-dependent
coverage can depend on difficulty. Structural counterfactual exposure is an oracle
witness paired with actual publication, not an observed counterfactual model answer.
Human participants were not part of this synthetic-world model study.

## Files intentionally excluded

No `.git` history, `.env` files, credential-store scripts, unrelated studies,
participant records, deployment configuration, historical `runs/` or `exports/`,
private operation guides or claimed original raw model corpus is distributed.
No license was supplied in the original snapshot; no replacement license is added.

