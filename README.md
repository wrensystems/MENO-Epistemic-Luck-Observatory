# MENO: Epistemic Luck Observatory

[Research report (PDF)](publication/report/MENO_Research_Report.pdf) ·
[Presentation (PDF)](publication/slides/MENO_Presentation.pdf) ·
[Editable presentation](publication/slides/MENO_Presentation.pptx)

A local research instrument for separating **actual truth**, **information-relative
support**, **evidential-route integrity**, and **bounded counterfactual robustness**
in language-model responses to finite synthetic causal worlds.

MENO asks whether a model can distinguish a conclusion that is warranted by its
available evidence from a conclusion that merely happens to be true. It does not
measure internal belief, consciousness or philosophical knowledge.

Independent researcher: **Louis Wren Hernandez David**. Prepared November 16, 2026.
Python **3.11+**, standard library only at runtime. No package installation,
API credentials, cloud account, external downloads or network access is needed
for the offline workflow. Git is optional for recording provenance.

An additional compact check blocks network connections while generating and
exporting a fresh scripted campaign:

```console
python -B tools/offline_smoke.py
```

## Run an offline demonstration

Run these commands from this folder, using a new campaign/export path each time:

```console
python --version
python -B -m unittest discover -s tests -v
python -B -m meno create runs/demo --config examples/offline-demo.json
python -B -m meno plan runs/demo
python -B -m meno run runs/demo
python -B -m meno verify runs/demo
python -B -m meno analyze runs/demo
python -B -m meno export runs/demo exports/demo
python -B exports/demo/reproduce.py
```

On systems where Python 3 is named `python3`, substitute that command. The example
freezes one matched block and nine trials: three worlds, each with an initial,
exact-facts and structured-audit response. It uses a **scripted mock transport**,
costs zero, and creates **synthetic software evidence, not model-performance data**.
Its scores must not be presented as reproducing the live study's results.

The final command independently rechecks the newly generated demo's hashes, parses
its archived responses, recomputes scores and compares block statistics. A
`VERIFIED` message concerns this new synthetic archive, not the historical live run.
Expected status: `synthetic`, nine completed trials, no missing responses.

Inspect the same campaign through a read-only local interface:

```console
python -B -m meno serve runs/demo --port 8792
```

Open http://127.0.0.1:8792 and stop with Ctrl+C. It binds only to loopback. The four
views cover overview, individual cases, comparisons and incidents/lineage. The
model perspective excludes hidden states, investigator role labels and oracle
scores from its separate projection. This is an inspection aid, not access control
against the investigator. Do not deploy it as an authenticated shared service.

## Scientific design

Eight named generator families cover defective sensors, dependent corroboration, stale
evidence, causal reversal, false-premise rescue, environmental luck, conditional
evidence and independent repair. Matched supported-true (S), lucky-true (L) and
false-twin (F) worlds are enriched constructions, not natural population draws.
Exact enumeration uses rational probabilities. Oracle calculations and declared
single-variable counterfactual witnesses are bounded certificates, not universal
epistemic safety.

Campaign C compares same-information interventions in Regime I. Exact facts and
structured audit each receive the same frozen initial answer and the same facts,
never one another's answer. Only their instructions differ; the audit arm is not
an independent checker or an additional evidence source. The primary balanced
decision score is `B=(P+N)/2`: coherent supported-case
publication and lucky-case withholding/verification. Missing/invalid outputs earn
zero indicators in the planned-denominator endpoint. Responses are averaged within
independent blocks before paired bootstrap analysis. Truth, cited support,
publication coherence and route validity remain distinct measures.

Other implemented campaigns support instrument controls, initial observability,
information acquisition and generalization. Adaptive verification is reserved and
not implemented as an experiment. Examples beyond the quickstart are in `examples/`.
Use `python -m meno --help` for campaign and suite commands.

The eight names designate generator families, not proof of eight independent
epistemic mechanisms. In particular, the sensor and independent-repair families
share structure. The separate repair intervention was not tested in the reported
same-information live suite; its implementation is not evidence of a measured
repair benefit.

## Data availability and reproducibility boundary

The historical report describes 16 planned blocks, 14 launched/completed blocks,
126 accepted responses out of 144 planned requests, and a budget stop at USD
6.94651 additional observed cost. Reported completed-block B was 1.0 in all three
conditions; audit minus facts was 0.0. These are **reported historical results**,
not observations generated or independently re-scored during this release.

**The original raw 126 responses, invocation journals, frozen campaign/suite
archives and standalone historical replay export were not present in the supplied
source snapshot and are not included here.** Consequently this public package
supports instrument verification, deterministic world construction and fresh
synthetic replay, but not independent raw-response reproduction of the live
numerical findings. Selected response excerpts in the manuscript are not a
substitute for the full raw corpus. No data access or release date is promised.

The public `data/reported_suite_summary.json` transcribes the checked-in report's
aggregate settings, all 16 planned seeds/ledger rows, costs and reported ceiling
scores. It is explicitly **report-derived**, not the original manifest or raw data.
Its executable accounting check verifies the deterministic schedule, 14 completed
rows, 126 requests, Decimal cost sum, reservation, next launch gate and aggregate
means without network access:

```console
python -B tools/verify_reported_summary.py
```

This checks internal accounting of reported numbers, not response-level scoring
or provider authenticity. If the original checked-in manuscript bytes are available,
`--source-report PATH` additionally verifies its SHA-256 and exact ledger transcription.

The accompanying publication files under `publication/` report
the historical study. See [data availability](data/README.md),
[technical reproducibility](docs/technical/REPRODUCIBILITY.md),
[prospective protocol](docs/technical/PROTOCOL.md) and
[release disclosure](RELEASE_DISCLOSURE.md).

## New live collection

Offline is the default. A live model configuration requires a frozen protocol,
explicit provider/model/settings, one attempt per trial, reviewed token prices,
token ceilings and sufficient campaign/per-model budgets. Plan before execution.
Live execution additionally requires `--live` and credentials supplied securely
through the process environment. A key or command-line flag does not constitute
researcher approval. No paid calls were made to prepare this release.

Provider compatibility and listed model aliases/rates are historical implementation
details, not guarantees of present or future account availability. Review them
before any new expenditure. A fresh live run is a new experiment, not deterministic
replay; world seeds do not seed provider generation. Uncertain attempts stop
collection and retain reservations. Do not bypass source guards or edit old evidence.
Disclosure-reviewed local export is separate from permission to publish data.

## Code and licensing

`meno/` supplies the public CLI. `research_lab/` contains the MENO scientific
instrument and only the generic execution, storage, analysis and provider modules
it needs. `tests/` includes applicable instrument and dependency tests plus public
entrypoint regression tests. The separate private research platform, deployment
configuration, unrelated studies, credential-store scripts and Git history are
excluded. See technical documentation for archival internal identifiers.

The generic engine, provider adapters and storage infrastructure, along with
earlier study scaffolding, were reused from preexisting work. This standalone
package is not a claim that all its infrastructure was first created during the
research sprint. Precise first-creation dates are not established by this release.

**License unspecified.** No license file was present in the source snapshot. This
release does not grant an open-source license or silently add reuse permissions.
Contact the author to clarify licensing before redistribution or reuse beyond
applicable legal permissions.

To rebuild the file-hash inventory and ZIP after adding publication artifacts:

```console
python -B tools/build_bundle.py --out ../MENO_Code.zip
```

The output ZIP must be outside this folder. Rebuilding does not run experiments,
publish files or change repository visibility.

