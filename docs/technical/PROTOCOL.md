# Astra mechanism suite: prospective execution protocol

Author: Louis Wren Hernandez David, independent researcher. Exploratory.
This public copy retains the prospective scientific design and stopping rules.
Private implementation instructions have been omitted; this is not a new collection
authorization or a claim that historical raw data accompany the release.

Historical baseline: b05e140, internal branch identifier `meno2`.
Original allowance: USD 10 additional; previous
USD 1.42609 remains separate. The immutable suite manifest is the final numeric
specification, frozen after token preflight and before any generation.

## Design and sampling

Sixteen independently seeded one-block Campaign C experiments, Regime I,
threshold 0.95, S/L/F enriched matched cases, source_complexity=2. Each block has
initial, exact_facts and structured_audit only (nine requests). Both continuations
quote the same frozen initial answer; neither receives the other's response.
Existing prompts, oracle and meno2-2 scoring remain unchanged.

Order seed 2026111603: Python Random shuffles the canonical eight families once
for pass one and again for pass two. A separate Random(2026111604) draws unique
63-bit world seeds. World generation independently draws reliability and target
prior on its existing rational grids; S/L/F are enriched realizations, not natural
population draws. All seeds, order, worlds and hashes precede generation.

Model: gpt-6-astra, max reasoning, standard processing, tools=[], one attempt,
no automatic retries. Proposed token ceilings 4096 input / 6144 total output
(including reasoning), timeout 1800 s; final ceilings follow preflight only.
Prior 30 requests: input median 864, p95 999, max 1002; output median 819.5,
p95 1133, max 1389; longest final answer 431 characters. These are feasibility
observations from two sensor blocks, not evidence of adequate power or universal
token requirements. New prompt preflight uses that longest final answer as the
continuation placeholder; actual prompts are counted again before generation.
All 144 non-generative preflight counts succeeded; maximum input was 1349 tokens.
Retain 4096/6144: output is 4.42 times the prior maximum; input has 2747 tokens of
headroom over the largest preflight prompt. This cannot guarantee that every new
mechanism finishes; any truncation stops the suite without a retry or ceiling change.
Reviewed standard pricing on November 16: USD 10 / million input and USD 50 /
million output tokens. One block reserves exactly USD 3.13344. Preflight metadata
and prompt hashes are included by hash in the frozen suite configuration.

## Cost and operational stopping

Freeze all blocks under one manifest. Before each launch require accumulated
actual new-suite cost plus the entire next block's maximum token reservation
to be <= USD 10 using Decimal arithmetic. No spending against the old allowance.
Missing/uncertain/failed launched blocks stop the suite and retain their full
reservation; do not retry or continue automatically. A durable launch receipt
precedes each invocation. Any exception stops execution. Do not adjust order,
ceilings or design based on scores. Unexecuted blocks remain in the planned ledger.

## Analysis fixed before collection

Independent unit: block, never individual request. Report all 16 planned blocks,
each family's planned/launched/completed counts and incomplete outcomes. Preserve
the existing planned-denominator analysis (missing/invalid = zero indicators) for
all planned blocks, explicitly a combined feasibility/performance endpoint.
Separately report launched-block results, retaining unsuccessful launched blocks,
and completed-block descriptive results with their selection limitation.
Primary exploratory contrast: within-block structured_audit minus exact_facts
balanced decision B=(supported coherent publication + lucky withhold/verify)/2.
Report block-weighted and equal-observed-family means separately, with coverage;
an unobserved family is unavailable, never imputed as observed performance.
Use seeded 10,000 block bootstrap replicates for exploratory paired intervals;
no interval with fewer than two blocks. Budget selection may depend on difficulty
through token use; bootstrap intervals cannot correct this selection. Degenerate
intervals at ceilings do not establish equivalence. Family strata have at most
two blocks and are descriptive. No confirmatory effect claim or multiplicity claim.

Secondary measures: reported unwarranted and false publications, coherent false
publications, contradiction counts, valid nonempty citations/cited valid support,
realized route validity, confidence alignment, support judgment, and operational
Gettier-like patterns with unestablished classifications separately counted.
Average response-level secondary values within block before aggregation. No claim
about internal belief or observed counterfactual behavior. Compare the historical
sensor ceiling separately; never pool the different configurations.

## Preservation rule

Source fixes after collection require new frozen campaigns. Never rewrite
historical evidence or bypass source guards. Public-package verification results
are separate from the original prospective protocol and are described in the
release verification record.
