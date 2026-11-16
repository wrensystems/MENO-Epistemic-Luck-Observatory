"""Finite, serializable structural causal model vocabulary for MENO.

All observations are deterministic functions of a finite independent exogenous
product distribution. Dependence belongs in structural equations, never in an
implicit assumption that two source reports are independent. No model output is
used to construct or interpret these specifications.
"""
from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
import hashlib
import json

SCHEMA_VERSION = "meno2-scm-1"


def var(name: str) -> dict:
    return {"var": name}


def const(value) -> dict:
    return {"const": value}


def op(operator: str, *args: dict) -> dict:
    return {"op": operator, "args": list(args)}


def equals(name: str, value) -> dict:
    return op("eq", var(name), const(value))


def evaluate(expression: dict, state: dict):
    """Evaluate the small data-only expression language (never eval/exec)."""
    if set(expression) == {"var"}:
        return state[expression["var"]]
    if set(expression) == {"const"}:
        return expression["const"]
    if set(expression) != {"op", "args"}:
        raise ValueError("malformed SCM expression")
    name, args = expression["op"], expression["args"]
    if name == "if" and len(args) == 3:
        return evaluate(args[1] if evaluate(args[0], state) else args[2], state)
    values = [evaluate(arg, state) for arg in args]
    if name == "eq" and len(values) == 2:
        return int(values[0] == values[1])
    if name == "not" and len(values) == 1:
        return int(not values[0])
    if name == "and" and values:
        return int(all(values))
    if name == "or" and values:
        return int(any(values))
    if name == "xor" and len(values) == 2:
        return int(bool(values[0]) != bool(values[1]))
    raise ValueError(f"unsupported SCM operator or arity: {name}")


def references(expression: dict) -> set[str]:
    if "var" in expression:
        return {expression["var"]}
    return set().union(*(references(arg) for arg in expression.get("args", [])))


def state_from(world: dict, exogenous: dict, intervention: dict | None = None) -> dict:
    intervention = intervention or {}
    state = dict(exogenous)
    state.update(intervention)
    for equation in world["equations"]:
        name = equation["variable"]
        if name not in intervention:
            state[name] = evaluate(equation["expression"], state)
        if state[name] not in world["variables"][name]["domain"]:
            raise ValueError(f"equation outside domain: {name}")
    return state


def actual_state(world: dict) -> dict:
    return state_from(world, world["realized_exogenous"])


def validate_world(world: dict) -> None:
    if world.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported finite-world schema")
    variables = world["variables"]
    if not variables or any(not item.get("domain") for item in variables.values()):
        raise ValueError("every variable requires a nonempty finite domain")
    known = set()
    for item in world["exogenous"]:
        name = item["variable"]
        if name in known or name not in variables:
            raise ValueError("duplicate or unknown exogenous variable")
        rows = item["distribution"]
        if [row["value"] for row in rows] != variables[name]["domain"]:
            raise ValueError("distribution must cover domain exactly, in order")
        probabilities = [Fraction(row["probability"]) for row in rows]
        if any(p < 0 for p in probabilities) or sum(probabilities) != 1:
            raise ValueError("invalid exact exogenous distribution")
        known.add(name)
    if set(world["realized_exogenous"]) != known:
        raise ValueError("realization must specify exactly the exogenous variables")
    for equation in world["equations"]:
        name = equation["variable"]
        if name in known or name not in variables:
            raise ValueError("duplicate or unknown structural variable")
        if not references(equation["expression"]) <= known:
            raise ValueError("equations must be in acyclic dependency order")
        known.add(name)
    if known != set(variables) or not references(world["target"]) <= known:
        raise ValueError("undefined variable or target")
    for item in world["exogenous"]:
        value = world["realized_exogenous"][item["variable"]]
        if not any(row["value"] == value and Fraction(row["probability"]) > 0
                   for row in item["distribution"]):
            raise ValueError("realization has zero probability or is outside domain")
    for source in world.get("sources", {}).values():
        if not references(source["valid_when"]) <= known:
            raise ValueError("undefined source-validity variable")
        for parent in source.get("parents", []):
            if parent["source"] not in world["sources"]:
                raise ValueError("unknown provenance parent")
            if not references(parent.get("when", const(1))) <= known:
                raise ValueError("undefined provenance condition")
    for item in world.get("admissible_interventions", []):
        if item["variable"] not in variables or not set(item["values"]) <= set(variables[item["variable"]]["domain"]):
            raise ValueError("invalid intervention domain")
    actual_state(world)


def public_model(world: dict) -> dict:
    """An explicit visibility boundary: never serialize IDs or the realization."""
    return deepcopy({key: world[key] for key in (
        "schema_version", "variables", "exogenous", "equations", "target",
        "target_text", "sources",
    )})


def stable_id(value, prefix: str = "world") -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return f"{prefix}-{hashlib.sha256(raw.encode()).hexdigest()[:20]}"


class WorldBuilder:
    """Small construction helper; inference is entirely in meno2_oracle."""

    def __init__(self, target_text: str):
        self.world = {"schema_version": SCHEMA_VERSION, "variables": {},
                      "exogenous": [], "equations": [], "sources": {},
                      "realized_exogenous": {}, "target": equals("Y", 1),
                      "target_text": target_text, "admissible_interventions": []}

    def exogenous(self, name: str, probability="0.5", *, description="", domain=None):
        domain = [0, 1] if domain is None else domain
        p = Fraction(probability)
        if not 0 < p < 1:
            raise ValueError("construction probabilities must be strictly between zero and one")
        self.world["variables"][name] = {"domain": domain, "description": description}
        self.world["exogenous"].append({"variable": name, "distribution": [
            {"value": domain[0], "probability": str(1 - p)},
            {"value": domain[1], "probability": str(p)}]})
        self.world["admissible_interventions"].append({"variable": name, "values": domain})
        return self

    def equation(self, name: str, expression: dict, *, description="", domain=None):
        self.world["variables"][name] = {"domain": [0, 1] if domain is None else domain,
                                          "description": description}
        self.world["equations"].append({"variable": name, "expression": expression})
        return self

    def source(self, name: str, description: str, valid_when=None, parents=None):
        self.world["sources"][name] = {"description": description,
            "valid_when": const(1) if valid_when is None else valid_when,
            "parents": [] if parents is None else parents,
            "validity_meaning": "appropriate route to target, not merely truthful transcription"}
        return self

    def realize(self, realization: dict) -> dict:
        world = deepcopy(self.world)
        world["realized_exogenous"] = dict(realization)
        world["id"] = stable_id(world)
        validate_world(world)
        return world


def record(identifier: str, text: str, variable: str, value, source: str,
           *, kind: str = "observation") -> dict:
    return {"id": identifier, "text": text, "observation": equals(variable, value),
            "source_id": source, "kind": kind}
