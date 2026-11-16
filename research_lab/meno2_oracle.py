"""Exact finite enumeration and evidence-relative certification.

The oracle never reads case role, mechanism labels, or model explanations.
Its rational mass calculations are auditable independently from generation.
"""
from __future__ import annotations

from fractions import Fraction
from itertools import product
from math import prod

from .meno2_worlds import actual_state, const, evaluate, state_from, validate_world

ORACLE_VERSION = "meno2-exact-enumeration-1"


def enumerate_states(world: dict, *, max_states: int | None = None):
    validate_world(world)
    dimensions = [item["distribution"] for item in world["exogenous"]]
    count = prod(len(rows) for rows in dimensions)
    if max_states is not None and count > max_states:
        raise ValueError(f"exact enumeration requires {count} states, limit is {max_states}")
    for rows in product(*dimensions):
        mass = prod((Fraction(row["probability"]) for row in rows), start=Fraction(1))
        if mass:
            assignment = {item["variable"]: row["value"]
                          for item, row in zip(world["exogenous"], rows)}
            yield state_from(world, assignment), mass


def _observations(evidence: list[dict], world: dict) -> list[dict]:
    seen = set()
    for item in evidence:
        if not isinstance(item.get("id"), str) or item["id"] in seen:
            raise ValueError("evidence IDs must be unique strings")
        seen.add(item["id"])
        if item.get("source_id") not in world["sources"]:
            raise ValueError("unknown evidence source")
        if "observation" not in item:
            raise ValueError("evidence requires a formal observation")
    return [item["observation"] for item in evidence]


def _conditional(states, observations):
    admitted = [(state, mass) for state, mass in states
                if all(evaluate(obs, state) for obs in observations)]
    mass = sum((p for _, p in admitted), Fraction(0))
    return admitted, mass


def _provenance(world: dict, state: dict, source_ids: list[str]) -> dict:
    sources = world["sources"]
    roots, integrity, edges = {}, {}, []

    def visit(identifier: str, path: tuple = ()):
        if identifier in path:
            raise ValueError("cyclic active source provenance")
        source = sources[identifier]
        parents = [p["source"] for p in source.get("parents", [])
                   if evaluate(p.get("when", const(1)), state)]
        valid = bool(evaluate(source["valid_when"], state))
        found = set()
        for parent in parents:
            edges.append([parent, identifier])
            parent_roots, parent_valid = visit(parent, (*path, identifier))
            found.update(parent_roots)
            valid = valid and parent_valid
        found = found or {identifier}
        roots[identifier], integrity[identifier] = sorted(found), valid
        return found, valid

    for identifier in source_ids:
        visit(identifier)
    dependencies = []
    for index, left in enumerate(source_ids):
        for right in source_ids[index + 1:]:
            common = sorted(set(roots[left]) & set(roots[right]))
            if common:
                dependencies.append({"sources": [left, right], "shared_roots": common})
    return {"roots": roots, "source_integrity": integrity,
            "active_edges": sorted(set(tuple(edge) for edge in edges)),
            "dependent_source_pairs": dependencies}


def counterfactual_witnesses(world: dict, evidence: list[dict], *, basis_ids=None) -> list[dict]:
    """All allowed single-variable interventions preserving the cited observations.

    These are structural, not probabilistic certificates or universal safety claims.
    Their scope is explicitly the frozen admissible single-variable neighborhood.
    """
    observations = _observations(evidence, world)
    if basis_ids is not None:
        chosen = set(basis_ids)
        observations = [e["observation"] for e in evidence if e["id"] in chosen]
    realized = actual_state(world)
    target = bool(evaluate(world["target"], realized))
    witnesses = []
    for item in world.get("admissible_interventions", []):
        name = item["variable"]
        for value in item["values"]:
            if value == realized[name]:
                continue
            state = state_from(world, world["realized_exogenous"], {name: value})
            after = bool(evaluate(world["target"], state))
            if after != target and all(evaluate(obs, state) for obs in observations):
                witnesses.append({"intervention": {name: value}, "state": state,
                    "truth_before": target, "truth_after": after,
                    "preserves_evidence_ids": [e["id"] for e in evidence
                       if basis_ids is None or e["id"] in basis_ids]})
    return witnesses


def assess(world: dict, evidence: list[dict], basis_ids=None, threshold="0.95",
           *, max_states: int | None = None, max_support_subsets: int | None = 100000) -> dict:
    """Keep truth, support, route integrity and robustness in separate fields.

    Publication concerns the affirmative target. A hidden invalid route cannot
    change information-relative support. Cited-route sufficiency additionally
    requires the selected evidence alone to reach the threshold. An empty basis
    has no evidential route (even when a high prior warrants the target).
    """
    policy = Fraction(str(threshold))
    if not Fraction(1, 2) < policy <= 1:
        raise ValueError("publication threshold must be greater than 0.5 and at most 1")
    observations = _observations(evidence, world)
    states = list(enumerate_states(world, max_states=max_states))
    admitted, evidence_mass = _conditional(states, observations)
    true_mass = sum((mass for state, mass in admitted if evaluate(world["target"], state)), Fraction(0))
    probability = true_mass / evidence_mass if evidence_mass else None
    logical = ("inconsistent" if probability is None else "supported" if probability == 1
               else "contradicted" if probability == 0 else "underdetermined")
    realized = actual_state(world)
    ids = [item["id"] for item in evidence]
    selected = ids if basis_ids is None else list(basis_ids)
    unknown = sorted(set(selected) - set(ids))
    chosen = [item for item in evidence if item["id"] in selected]
    provenance = _provenance(world, realized, list(dict.fromkeys(e["source_id"] for e in chosen)))
    route_valid = bool(chosen) and not unknown and all(provenance["source_integrity"].values())
    basis_states, basis_mass = _conditional(states, [item["observation"] for item in chosen])
    basis_true = sum((p for s, p in basis_states if evaluate(world["target"], s)), Fraction(0))
    basis_p = basis_true / basis_mass if basis_mass else None
    sufficient = (bool(chosen) and not unknown and basis_p is not None and basis_p >= policy
                  and probability is not None and probability >= policy)
    # Enumerate inclusion-minimal valid support sets. This recognizes a genuine
    # alternative justification even if a response also cites a compromised one.
    valid_records = [e for e in evidence if _provenance(world, realized, [e["source_id"]])
                     ["source_integrity"][e["source_id"]]]
    alternatives = []
    # Available defeaters cannot be discarded by cherry-picking a subset.
    if probability is None or probability < policy:
        valid_records = []
    subset_count = 2 ** len(valid_records) - 1
    if max_support_subsets is not None and subset_count > max_support_subsets:
        raise ValueError(f"exact support search requires at most {subset_count} subsets, limit is {max_support_subsets}")
    from itertools import combinations
    for size in range(1, len(valid_records) + 1):
        for group in combinations(valid_records, size):
            group_ids = [e["id"] for e in group]
            if any(set(previous) <= set(group_ids) for previous in alternatives):
                continue
            rows, mass = _conditional(states, [e["observation"] for e in group])
            positive = sum((p for s, p in rows if evaluate(world["target"], s)), Fraction(0))
            if mass and positive / mass >= policy:
                alternatives.append(group_ids)
    witnesses = counterfactual_witnesses(world, evidence, basis_ids=selected)
    source_posteriors = {}
    if evidence_mass:
        for source_id in world.get('sources', {}):
            valid_mass = sum((mass for state, mass in admitted
                              if _provenance(world, state, [source_id])['source_integrity'][source_id]), Fraction(0))
            source_posteriors[source_id] = str(valid_mass / evidence_mass)
    return {"oracle_version": ORACLE_VERSION, "truth": bool(evaluate(world["target"], realized)),
        "probability": None if probability is None else float(probability),
        "probability_exact": None if probability is None else str(probability),
        "logical_status": logical,
        "support_judgment": ("inconsistent" if probability is None else "supported" if probability >= policy
                             else "unsupported" if probability <= 1-policy else "underdetermined"),
        "publication_warranted": probability is not None and probability >= policy,
        "threshold_exact": str(policy), "route_valid": route_valid,
        "route_sufficient": sufficient, "basis_probability_exact": None if basis_p is None else str(basis_p),
        "valid_support_available": bool(alternatives), "alternative_valid_supports": alternatives,
        "unknown_basis_ids": unknown, "provenance": provenance,
        "source_validity_given_available_evidence": source_posteriors,
        "available_defeater_sources": [s for s, p in source_posteriors.items() if Fraction(p) == 0],
        "counterfactual_witnesses": witnesses,
        "counterfactual_false_commitment_possible": any(not w["truth_after"] for w in witnesses),
        "counterfactual_scope": "all frozen admissible single-variable interventions preserving cited evidence",
        "calculation": {"method": "exact finite enumeration", "approximate": False,
            "enumerated_states": len(states), "consistent_states": len(admitted),
            "evidence_mass_exact": str(evidence_mass), "target_and_evidence_mass_exact": str(true_mass),
            "independence": "exogenous product distribution; endogenous/source dependence retained"}}
