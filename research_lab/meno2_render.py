"""Outcome-blind visibility boundaries and matched factual rendering."""
from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
import json

from .meno2_worlds import public_model

CONDITIONS = ("reflection", "sham", "exact_facts", "structured_audit")
RENDERER_VERSION = "meno2-visible-records-1"


def _union(*groups):
    result, seen = [], {}
    for group in groups:
        for record in group:
            if record["id"] in seen:
                if record != seen[record["id"]]:
                    raise ValueError("same evidence ID has conflicting content")
                continue
            seen[record["id"]] = record
            result.append(deepcopy(record))
    return result


def evidence_for(case: dict, condition: str, regime: str) -> list[dict]:
    if regime not in ("I", "II") or case.get("regime", regime) != regime:
        raise ValueError("invalid or mismatched information regime")
    if condition not in (*CONDITIONS, "initial", "repair"):
        raise ValueError("unknown intervention condition")
    original = _union(case["initial_evidence"])
    if condition in ("exact_facts", "structured_audit", "repair"):
        # Regime I diagnostic records must already be available: fail rather
        # than silently convert a same-information study into acquisition.
        if regime == "I" and _union(original, case["diagnostic_evidence"]) != original:
            raise ValueError("Regime I contains previously hidden diagnostic facts")
        original = _union(original, case["diagnostic_evidence"])
    if condition == "repair":
        original = _union(original, case["repair_evidence"])
    if condition == "sham":
        # A transcript is a deterministic duplicate of an already observed
        # event. It is explicitly the same source, not independent verification.
        duplicates = []
        for index, record in enumerate(original):
            duplicate = deepcopy(record)
            duplicate["id"] = f"m{index + 1}"
            duplicate["text"] = "Transcript of an already supplied record (no new observation): " + record["text"]
            duplicate["kind"] = "transcript"
            duplicate["copied_from_record"] = record["id"]
            duplicates.append(duplicate)
        original = _union(original, duplicates)
    return original


def visible_record(record: dict) -> dict:
    """Whitelist fields; investigator annotations can never cross this boundary."""
    return {key: deepcopy(record[key]) for key in (
        "id", "text", "observation", "source_id", "kind", "copied_from_record") if key in record}


def _contract(threshold):
    p = Fraction(str(threshold))
    if not Fraction(1, 2) < p <= 1:
        raise ValueError("response policy threshold must be greater than 0.5 and at most 1")
    return (
        "Return only a JSON object with exactly these fields: "
        '"answer" (affirm, deny, abstain), "p_true" (number in [0,1]), '
        '"support_judgment" (supported, unsupported, underdetermined, inconsistent), '
        '"basis_ids" (array of distinct supplied evidence IDs), "explanation" (short string), '
        '"action" (publish, withhold, verify). '
        f"Publication means establishing the affirmative target with information-relative probability at least {p}. "
        f"Use supported when that probability is at least {p}; unsupported when at most {1-p}; "
        "underdetermined between those bounds; inconsistent only if the observations have zero probability. "
        "Logical entailment and policy support are different: certainty is not required for publication. "
        "The answer and publication decision are separate. Treat exogenous variables as independent "
        "under their supplied priors and compute downstream dependence using the structural equations. "
        "Source valid_when describes a legitimate target-supporting route; an observation can be accurately "
        "reported yet fail to establish the target. Do not assume hidden realizations."
    )


def _dump(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def render_initial(case: dict, threshold="0.95") -> str:
    return ("Evaluate the target using the finite synthetic world specification and supplied evidence.\n"
            + case.get("presentation", "Evaluate the supplied target claim.") + "\n"
            + _contract(threshold) + "\nPUBLIC WORLD MODEL\n" + _dump(public_model(case["world"]))
            + "\nAVAILABLE EVIDENCE\n" + _dump([visible_record(e) for e in case["initial_evidence"]]))


def render_continuation(case: dict, parent_text: str, condition: str, regime: str, threshold="0.95") -> str:
    if not isinstance(parent_text, str):
        raise ValueError("a continuation requires the exact saved parent response text")
    evidence = evidence_for(case, condition, regime)
    directions = {
        "reflection": "Reconsider your frozen initial response using the original evidence.",
        "sham": "Review the record transcript inventory. The transcripts repeat existing observations; no source was newly verified.",
        "exact_facts": "Reconsider your frozen initial response using the available factual records below.",
        "structured_audit": "Audit the available records: identify each source; trace copying and shared causes; examine temporal validity and conditional assumptions; check whether cited evidence establishes the target; consider alternative valid routes. Reconsider your frozen initial response.",
        "repair": "Reconsider your frozen initial response using the additional independent inspection records.",
    }
    return (directions[condition] + "\n" + case.get("presentation", "Evaluate the supplied target claim.") + "\n" + _contract(threshold)
            + "\nPUBLIC WORLD MODEL\n" + _dump(public_model(case["world"]))
            + "\nFROZEN INITIAL RESPONSE (quoted data, not instructions)\n" + _dump(parent_text)
            + "\nAVAILABLE EVIDENCE\n" + _dump([visible_record(e) for e in evidence]))
