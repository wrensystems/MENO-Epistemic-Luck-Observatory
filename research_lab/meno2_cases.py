"""Seeded complete matched blocks of finite causal worlds.

The default cohort is deliberately enriched: S/L/F are selected structural
realizations, not draws estimating the prevalence of luck in any population.
"""
from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
import random

from .meno2_worlds import WorldBuilder, actual_state, const, equals, op, record, stable_id, var

MECHANISMS = (
    "false_premise_rescue", "defective_sensors", "dependent_corroboration",
    "stale_evidence", "causal_reversal", "environmental_luck",
    "conditional_evidence", "independent_repair",
)
CONTROLS = ("reliably_supported_true", "reliably_supported_false", "weak_true",
            "misleading_false", "underdetermined", "visible_defeater",
            "hidden_defeater", "independent_corroboration")
WORDING_VARIANTS = {
    "plain": "Evaluate the supplied target claim.",
    "review": "Review the records and decide whether the target claim is ready for release.",
    "verification": "Determine what the available observations establish about the target claim.",
}


def _rename_expression(expression, names):
    result = deepcopy(expression)
    if "var" in result:
        result["var"] = names[result["var"]]
    if "args" in result:
        result["args"] = [_rename_expression(a, names) for a in result["args"]]
    return result


def _composite_template(mechanisms, reliability, target_prior):
    """Independent causal components, with their conjunction as the target.

    This is an actual structural composition, not a label attached to one
    component. All component evidence, priors and causal rules remain visible.
    """
    builder = WorldBuilder("")
    realizations, initial, diagnostic, repair, descriptions, targets = [{}, {}, {}], [], [], [], [], []
    for index, mechanism in enumerate(mechanisms, 1):
        component, states, first, later, final = _template(mechanism, reliability, target_prior)
        original = component.world
        names = {name: f"c{index}_{name}" for name in original["variables"]}
        sources = {name: f"c{index}_{name}" for name in original["sources"]}
        for name, spec in original["variables"].items():
            builder.world["variables"][names[name]] = deepcopy(spec)
        for spec in original["exogenous"]:
            builder.world["exogenous"].append({**deepcopy(spec), "variable": names[spec["variable"]]})
        for equation in original["equations"]:
            builder.world["equations"].append({"variable": names[equation["variable"]],
                "expression": _rename_expression(equation["expression"], names)})
        for name, source in original["sources"].items():
            renamed = deepcopy(source)
            renamed["valid_when"] = _rename_expression(source["valid_when"], names)
            renamed["parents"] = [{"source": sources[p["source"]],
                "when": _rename_expression(p.get("when", const(1)), names)} for p in source["parents"]]
            builder.world["sources"][sources[name]] = renamed
        for item in original["admissible_interventions"]:
            builder.world["admissible_interventions"].append({**deepcopy(item), "variable": names[item["variable"]]})
        for new_state, original_state in zip(realizations, states):
            new_state.update({names[name]: value for name, value in original_state.items()})
        for destination, group in ((initial, first), (diagnostic, later), (repair, final)):
            destination.extend((names[v], sources[s], f"Component {index}: {text}") for v, s, text in group)
        descriptions.append(f"Component {index}: {original['target_text']}")
        targets.append(var(names["Y"]))
    builder.world["target_text"] = "All component targets hold. " + " ".join(descriptions)
    builder.equation("Y", op("and", *targets), description="Conjunction of all component targets")
    return builder, realizations, initial, diagnostic, repair


def _template(mechanism: str, reliability: str, target_prior: str):
    """Return a causal model, independently specified matched states and records."""
    if "+" in mechanism:
        return _composite_template(mechanism.split("+"), reliability, target_prior)
    if mechanism in ("defective_sensors", "independent_repair"):
        b = WorldBuilder("At least one of chambers A and B contains a crystal.")
        b.exogenous("A", target_prior, description="Chamber A has a crystal")
        b.exogenous("B", "0.1", description="Chamber B has a crystal")
        b.exogenous("H", reliability, description="Chamber A sensor is healthy")
        b.equation("S", op("if", var("H"), var("A"), const(1)), description="Chamber A display")
        b.equation("Y", op("or", var("A"), var("B")), description="Target")
        b.source("q1", "Chamber A sensor; if defective it is stuck positive", equals("H", 1))
        b.source("q2", "Independent exact chamber A inspection")
        b.source("q3", "Independent exact chamber B inspection")
        states = [{"A": 1, "B": 0, "H": 1}, {"A": 0, "B": 1, "H": 0},
                  {"A": 0, "B": 0, "H": 0}]
        initial = [("S", "q1", "Chamber A display")]
        diagnostic = [("A", "q2", "Independent chamber A inspection")]
        repair = [("B", "q3", "Independent chamber B inspection")]
        if mechanism == "independent_repair":
            b.equation("V", var("Y"), description="Independent complete inventory verdict")
            b.source("q4", "Exact complete inventory, physically independent of the display")
            repair = [("V", "q4", "Independent complete inventory verdict")]
    elif mechanism == "false_premise_rescue":
        b = WorldBuilder("The selected entrant carries a blue token.")
        b.exogenous("Winner", target_prior, domain=["south", "north"], description="Selected entrant")
        b.exogenous("SouthToken", "0.1", description="South entrant has a blue token")
        b.exogenous("RegistryOK", reliability, description="Selection registry is reliable")
        b.equation("NorthToken", const(1), description="North entrant has a blue token")
        b.equation("Report", op("if", var("RegistryOK"), var("Winner"), const("north")),
                   domain=["south", "north"], description="Registry's selected entrant")
        b.equation("Y", op("if", equals("Winner", "north"), var("NorthToken"), var("SouthToken")))
        b.source("q1", "Selection registry", equals("RegistryOK", 1))
        b.source("q2", "Independent exact selection ledger")
        b.source("q3", "Independent inspection of the south entrant's token")
        states = [{"Winner": "north", "SouthToken": 0, "RegistryOK": 1},
                  {"Winner": "south", "SouthToken": 1, "RegistryOK": 0},
                  {"Winner": "south", "SouthToken": 0, "RegistryOK": 0}]
        initial = [("Report", "q1", "Registry reports selected entrant")]
        diagnostic = [("Winner", "q2", "Independent ledger identifies selected entrant")]
        repair = [("SouthToken", "q3", "South entrant token inspection")]
    elif mechanism == "dependent_corroboration":
        b = WorldBuilder("The sealed parcel contains the marked component.")
        b.exogenous("T", target_prior, description="Parcel contains the marked component")
        b.exogenous("H", reliability, description="First reader is healthy")
        b.exogenous("J", reliability, description="Independent second reader is healthy")
        b.exogenous("Copy", "0.9", description="Second report copies the first reader")
        b.equation("X", op("if", var("H"), var("T"), const(1)), description="First report")
        b.equation("Independent", op("if", var("J"), var("T"), const(1)))
        b.equation("Z", op("if", var("Copy"), var("X"), var("Independent")), description="Second report")
        b.equation("Y", var("T"))
        b.source("q1", "First reader", equals("H", 1))
        b.source("q2", "Second report; can copy the first or use its own reader",
                 op("or", equals("Copy", 1), equals("J", 1)),
                 [{"source": "q1", "when": equals("Copy", 1)}])
        b.source("q3", "Independent wiring and first-reader diagnostic")
        b.source("q4", "Independent exact parcel inspection")
        states = [{"T": 1, "H": 1, "J": 1, "Copy": 0},
                  {"T": 1, "H": 0, "J": 1, "Copy": 1},
                  {"T": 0, "H": 0, "J": 1, "Copy": 1}]
        initial = [("X", "q1", "First reader report"), ("Z", "q2", "Second reader report")]
        diagnostic = [("Copy", "q3", "Wiring inspection: second report copies first"),
                      ("H", "q3", "First-reader diagnostic: healthy")]
        repair = [("T", "q4", "Independent parcel inspection")]
    elif mechanism == "stale_evidence":
        b = WorldBuilder("The container currently contains a green tile.")
        b.exogenous("Current", target_prior, description="Present container state")
        b.exogenous("Past", target_prior, description="Earlier state, independent after replacement")
        b.exogenous("Fresh", reliability, description="Record comes from the current container")
        b.equation("R", op("if", var("Fresh"), var("Current"), var("Past")), description="Archived reading")
        b.equation("Time", op("if", var("Fresh"), const("current"), const("previous")),
                   domain=["previous", "current"], description="Record timestamp")
        b.equation("Y", var("Current"))
        b.source("q1", "Archived inspection; previous containers were independently replaced", equals("Fresh", 1))
        b.source("q2", "Exact timestamp provenance inspection")
        b.source("q3", "Independent current-container inspection")
        states = [{"Current": 1, "Past": 0, "Fresh": 1},
                  {"Current": 1, "Past": 1, "Fresh": 0},
                  {"Current": 0, "Past": 1, "Fresh": 0}]
        initial = [("R", "q1", "Archived inspection reading")]
        diagnostic = [("Time", "q2", "Inspection timestamp relative to replacement")]
        repair = [("Current", "q3", "Current-container inspection")]
    elif mechanism == "causal_reversal":
        b = WorldBuilder("The primary mechanism is active.")
        b.exogenous("T", target_prior, description="Primary mechanism active")
        b.exogenous("Alternative", str(1 - Fraction(reliability)), description="Alternate cause of indicator")
        b.equation("Effect", op("or", var("T"), var("Alternative")), description="Shared effect indicator")
        b.equation("Y", var("T"))
        b.source("q1", "Effect indicator; it can be produced by either cause", equals("Alternative", 0))
        b.source("q2", "Independent exact alternate-cause inspection")
        b.source("q3", "Independent direct inspection of the primary mechanism")
        states = [{"T": 1, "Alternative": 0}, {"T": 1, "Alternative": 1},
                  {"T": 0, "Alternative": 1}]
        initial = [("Effect", "q1", "Shared effect indicator")]
        diagnostic = [("Alternative", "q2", "Alternate-cause inspection")]
        repair = [("T", "q3", "Direct primary-mechanism inspection")]
    elif mechanism == "environmental_luck":
        b = WorldBuilder("The encountered facade belongs to a real storage building.")
        b.exogenous("Real", target_prior, description="Encountered facade is a real building")
        b.exogenous("Normal", reliability, description="Environment has discriminating visual cues")
        b.exogenous("DecoyCue", "0.5", description="Non-discriminating cue in the replica environment")
        b.equation("Appearance", op("if", var("Normal"), var("Real"), var("DecoyCue")))
        b.equation("Y", var("Real"))
        b.source("q1", "Visual facade cue, discriminating only in the ordinary environment", equals("Normal", 1))
        b.source("q2", "Independent environmental provenance inspection")
        b.source("q3", "Independent interior inspection")
        states = [{"Real": 1, "Normal": 1, "DecoyCue": 0},
                  {"Real": 1, "Normal": 0, "DecoyCue": 1},
                  {"Real": 0, "Normal": 0, "DecoyCue": 1}]
        initial = [("Appearance", "q1", "Building-like facade cue")]
        diagnostic = [("Normal", "q2", "Environment inspection: ordinary cue-generating environment")]
        repair = [("Real", "q3", "Interior inspection establishes real storage building")]
    elif mechanism == "conditional_evidence":
        b = WorldBuilder("The output compartment contains a stamped piece.")
        b.exogenous("Input", target_prior, description="Input trigger is on")
        b.exogenous("Rule", reliability, description="Routing assumption is enabled")
        b.exogenous("Fallback", "0.1", description="Fallback route independently supplies a stamped piece")
        b.equation("Y", op("if", var("Rule"), var("Input"), var("Fallback")))
        b.source("q1", "Exact input-trigger observation; entails output only when routing is enabled", equals("Rule", 1))
        b.source("q2", "Independent routing-configuration inspection")
        b.source("q3", "Independent output-compartment inspection")
        states = [{"Input": 1, "Rule": 1, "Fallback": 0},
                  {"Input": 1, "Rule": 0, "Fallback": 1},
                  {"Input": 1, "Rule": 0, "Fallback": 0}]
        initial = [("Input", "q1", "Input trigger observation")]
        diagnostic = [("Rule", "q2", "Routing configuration: enabled")]
        repair = [("Y", "q3", "Independent output inspection")]
    else:
        raise ValueError(f"unknown mechanism: {mechanism}")
    return b, states, initial, diagnostic, repair


def _records(specs, state, start):
    return [record(f"e{start + index}", f"{label}: {state[name]}", name, state[name], source)
            for index, (name, source, label) in enumerate(specs)]


def _block(mechanism, regime, *, seed, index, reliability, target_prior, cohort,
           source_complexity=1, independent_repeat_count=0, wording_variant="plain"):
    builder, realizations, initial, diagnostic, repair = _template(mechanism, reliability, target_prior)
    # Additional reports are explicitly copied, preserving causal dependence.
    # Independent corroboration instead gets new exogenous fault variables.
    origin_variable, origin_source, _ = initial[0]
    previous_variable, previous_source = origin_variable, origin_source
    for depth in range(1, source_complexity):
        variable, source = f"Forwarded{depth}", f"forwarded{depth}"
        builder.equation(variable, var(previous_variable), domain=builder.world["variables"][previous_variable]["domain"],
                         description=f"Report forwarded through {depth} relay(s)")
        builder.source(source, "Exact forwarding of the preceding report", const(1),
                       [{"source": previous_source, "when": const(1)}])
        initial.append((variable, source, f"Forwarding relay {depth} report"))
        previous_variable, previous_source = variable, source
    for repeat in range(1, independent_repeat_count + 1):
        fault, variable, source = f"CheckHealthy{repeat}", f"CheckReport{repeat}", f"independent{repeat}"
        builder.exogenous(fault, reliability, description="Independent whole-target verifier is healthy")
        builder.equation(variable, op("if", var(fault), var("Y"), const(1)),
                         description="Independent whole-target verdict; stuck positive if defective")
        builder.source(source, "Independent whole-target verifier with its own fault distribution", equals(fault, 1))
        for role_index, state in enumerate(realizations):
            state[fault] = 0 if role_index == 2 else 1
        initial.append((variable, source, f"Independent verifier {repeat} report"))
    block_key = {"seed": seed, "index": index, "mechanism": mechanism, "regime": regime,
                 "reliability": str(reliability), "target_prior": str(target_prior),
                 "source_complexity": source_complexity, "independent_repeat_count": independent_repeat_count,
                 "wording_variant": wording_variant}
    block_id = stable_id(block_key, "block")
    cases = []
    for role, realization in zip(("S", "L", "F"), realizations):
        world = builder.realize(realization)
        state = actual_state(world)
        observed = _records(initial, state, 1)
        diagnosed = _records(diagnostic, state, len(initial) + 1)
        repaired = _records(repair, state, len(initial) + len(diagnostic) + 1)
        gettier_structure = role == "L" and any(part in (
            "false_premise_rescue", "defective_sensors", "conditional_evidence", "independent_repair")
            for part in mechanism.split("+"))
        cases.append({"id": stable_id({"block": block_id, "realization": realization}, "case"),
            "role": role, "world": world,
            "initial_evidence": observed + (diagnosed if regime == "I" else []),
            "diagnostic_evidence": diagnosed, "repair_evidence": repaired,
            "structure_labels": {"actual_truth": bool(state["Y"]),
                "gettier_structured_opportunity": gettier_structure,
                "structural_category": "false_premise_with_independent_truth" if gettier_structure else
                    "environmental_luck" if role == "L" and mechanism == "environmental_luck" else
                    "broader_epistemic_deficiency" if role == "L" else "comparison",
                "defeater_visibility": "initial" if regime == "I" else "initially_hidden"},
            "regime": regime, "presentation": WORDING_VARIANTS[wording_variant]})
    return {"id": block_id, "mechanism": mechanism, "regime": regime,
            "case_class": "diagnostically_distinguishable" if regime == "I" else "observationally_identical",
            "eligible": True, "cohort": cohort, "cases": cases,
            "generation": {**block_key, "sampling": "deliberately selected matched structural realizations"}}


def crystal_fixture(regime: str = "II") -> dict:
    """The exact 1001/1010 centerpiece, with the specified S/L/F states."""
    if regime not in ("I", "II"):
        raise ValueError("regime must be I or II")
    return _block("defective_sensors", regime, seed=0, index=0, reliability="0.99",
                  target_prior="0.5", cohort="validation_fixture")


def _controls(block_id: str, regime: str) -> list[dict]:
    base = crystal_fixture("II")
    supported, lucky, false = base["cases"]
    specifications = [
        ("reliably_supported_true", supported, "Y", 1),
        ("reliably_supported_false", false, "Y", 0),
        ("weak_true", lucky, "H", 0),
        ("misleading_false", false, None, None),
        ("underdetermined", lucky, "H", 0),
        ("visible_defeater", lucky, "A", 0),
        ("hidden_defeater", lucky, None, None),
    ]
    result = []
    for name, original, variable, value in specifications:
        case = deepcopy(original)
        if name == "underdetermined":
            independent_builder = WorldBuilder("The selected disk has a central mark.")
            independent_builder.exogenous("T", "0.5", description="Disk has a central mark")
            independent_builder.exogenous("N", "0.5", description="Independent orientation marker")
            independent_builder.equation("Y", var("T"))
            independent_builder.source("q_control", "Exact independent orientation marker observation")
            case["world"] = independent_builder.realize({"T": 1, "N": 1})
            variable, value = "N", 1
        case["world"]["sources"]["q_control"] = {"description": "Independent exact control inspection",
            "valid_when": const(1), "parents": [], "validity_meaning": "appropriate independent observation"}
        if variable is not None:
            observation = record("e5", f"Independent inspection of {variable}: {value}", variable, value, "q_control")
            case["initial_evidence"] = ([*case["initial_evidence"], observation]
                if name == "visible_defeater" else [observation])
        case["diagnostic_evidence"] = []
        case["repair_evidence"] = []
        case["id"] = stable_id({"block": block_id, "control": name}, "case")
        case["role"], case["control_type"], case["regime"] = "control", name, regime
        case["structure_labels"] = {"actual_truth": bool(actual_state(case["world"])["Y"]),
                                      "gettier_structured_opportunity": False, "structural_category": "control"}
        case["world"]["id"] = stable_id({k: v for k, v in case["world"].items() if k != "id"})
        result.append(case)
    independent = _block("dependent_corroboration", "II", seed=0, index=0,
                          reliability="0.99", target_prior="0.5", cohort="validation_fixture")["cases"][0]
    independent["initial_evidence"].append(independent["diagnostic_evidence"][0])
    independent["diagnostic_evidence"] = []
    independent["repair_evidence"] = []
    independent["id"] = stable_id({"block": block_id, "control": "independent_corroboration"}, "case")
    independent["role"], independent["control_type"], independent["regime"] = "control", "independent_corroboration", regime
    result.append(independent)
    return result


def generate_blocks(seed: int, count: int, regime: str = "I", mechanisms=None, **options) -> list[dict]:
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError("count must be a nonnegative integer")
    if regime not in ("I", "II"):
        raise ValueError("regime must be I or II")
    allowed = {"reliability", "target_prior", "include_controls", "case_class", "cohort",
               "source_complexity", "independent_repeat_count", "wording_variant"}
    unknown = set(options) - allowed
    if unknown:
        raise ValueError(f"unsupported generation options: {sorted(unknown)}")
    cohort = options.get("cohort", "enriched_stress")
    if cohort not in ("enriched_stress", "validation_fixture"):
        raise ValueError("matched generation is enriched; a naturally sampled cohort cannot be relabeled from matched states")
    expected_class = "diagnostically_distinguishable" if regime == "I" else "observationally_identical"
    if options.get("case_class", expected_class) != expected_class:
        raise ValueError("requested case class conflicts with the regime's visibility boundary")
    families = list(MECHANISMS if mechanisms is None else mechanisms)
    if (not families or any(not isinstance(m, str) or any(part not in MECHANISMS for part in m.split("+"))
                           or len(m.split("+")) != len(set(m.split("+"))) for m in families)
            or len(families) != len(set(families))):
        raise ValueError("mechanisms must be a nonempty distinct selection of known mechanism names")
    for name, minimum in (("source_complexity", 1), ("independent_repeat_count", 0)):
        value = options.get(name, minimum)
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise ValueError(f"{name} must be an integer at least {minimum}")
    if options.get("wording_variant", "plain") not in WORDING_VARIANTS:
        raise ValueError(f"wording_variant must be one of {list(WORDING_VARIANTS)}")
    rng = random.Random(seed)
    rng.shuffle(families)
    blocks = []
    for index in range(count):
        # Independent grid draws create actual within-family causal variation,
        # not merely new IDs on the same world. Explicit settings fix that
        # dimension for controlled studies and the immutable crystal fixture.
        reliability = str(options["reliability"]) if "reliability" in options else str(Fraction(rng.randint(990000, 999900), 1000000))
        target_prior = str(options["target_prior"]) if "target_prior" in options else str(Fraction(rng.randint(200000, 800000), 1000000))
        block = _block(families[index % len(families)], regime, seed=seed, index=index,
            reliability=reliability, target_prior=target_prior, cohort=cohort,
            source_complexity=options.get("source_complexity", 1),
            independent_repeat_count=options.get("independent_repeat_count", 0),
            wording_variant=options.get("wording_variant", "plain"))
        block["generation"]["parameter_sampling"] = {
            "reliability": "fixed" if "reliability" in options else "uniform integer grid 990000..999900 divided by 1000000, inclusive",
            "target_prior": "fixed" if "target_prior" in options else "uniform integer grid 200000..800000 divided by 1000000, inclusive",
            "draw_dependence": "independent pseudorandom parameter draws across blocks; mechanisms balanced by seeded cycle",
            "realization_sampling": "enriched matched S/L/F states, never natural prevalence draws"}
        if options.get("include_controls", False):
            block["cases"].extend(_controls(block["id"], regime))
        # Eligibility is pre-response, evidence-relative, and threshold-specific.
        # validate_block checks the actual policy again when freezing a campaign.
        from .meno2_oracle import assess
        from .meno2_render import evidence_for
        primary = [assess(case["world"], evidence_for(case, "exact_facts", regime))
                   for case in block["cases"] if case["role"] in ("S", "L")]
        block["eligible"] = primary[0]["publication_warranted"] and not primary[1]["publication_warranted"]
        block["eligibility_threshold"] = "19/20"
        blocks.append(block)
    return blocks


def validate_block(block: dict, threshold="0.95") -> dict:
    """Validate construction before responses; return the actual eligibility."""
    from .meno2_oracle import assess
    from .meno2_render import evidence_for, render_initial
    cases = block["cases"]
    roles = {case["role"]: case for case in cases if case["role"] != "control"}
    if len(roles) != 3 or set(roles) != {"S", "L", "F"} or len(cases) != 3 + sum(c["role"] == "control" for c in cases):
        raise ValueError("a matched block requires exactly one S, L and F")
    if len({c["id"] for c in cases}) != len(cases):
        raise ValueError("duplicate case identity in block")
    summaries = {}
    for role, case in roles.items():
        if case["regime"] != block["regime"]:
            raise ValueError("case/block regime mismatch")
        result = assess(case["world"], evidence_for(case, "exact_facts", block["regime"]), threshold=threshold)
        if result["truth"] != (role != "F"):
            raise ValueError(f"incorrect realized truth for role {role}")
        summaries[role] = result
    if block["case_class"] == "observationally_identical":
        if len({render_initial(case, threshold) for case in roles.values()}) != 1:
            raise ValueError("observational twins expose different initial information")
    eligible = summaries["S"]["publication_warranted"] and not summaries["L"]["publication_warranted"]
    return {"valid": True, "eligible": eligible, "threshold_exact": str(Fraction(str(threshold))),
            "probabilities": {role: item["probability_exact"] for role, item in summaries.items()}}
