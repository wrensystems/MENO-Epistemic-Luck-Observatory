"""Independent scientific fixtures, not assertions copied from generator helpers."""
import copy
from fractions import Fraction
from itertools import product
import json
import unittest

from research_lab.meno2_cases import CONTROLS, MECHANISMS, crystal_fixture, generate_blocks, validate_block
from research_lab.meno2_oracle import assess, counterfactual_witnesses, enumerate_states
from research_lab.meno2_render import CONDITIONS, evidence_for, render_continuation, render_initial
from research_lab.meno2_worlds import actual_state, const, equals, record, validate_world


class CrystalWorldTests(unittest.TestCase):
    def setUp(self):
        self.block = crystal_fixture()
        self.s, self.l, self.f = self.block["cases"]

    def test_exact_realizations_and_centerpiece_probabilities(self):
        self.assertEqual([actual_state(c["world"]) for c in self.block["cases"]], [
            {"A": 1, "B": 0, "H": 1, "S": 1, "Y": 1},
            {"A": 0, "B": 1, "H": 0, "S": 1, "Y": 1},
            {"A": 0, "B": 0, "H": 0, "S": 1, "Y": 0}])
        initial = [assess(c["world"], c["initial_evidence"]) for c in self.block["cases"]]
        self.assertEqual([a["probability_exact"] for a in initial], ["1001/1010"] * 3)
        self.assertEqual([a["truth"] for a in initial], [True, True, False])
        self.assertEqual([a["route_valid"] for a in initial], [True, False, False])
        self.assertTrue(all(a["publication_warranted"] for a in initial))
        after = assess(self.l["world"], evidence_for(self.l, "exact_facts", "II"))
        self.assertEqual(after["probability_exact"], "1/10")
        repaired = assess(self.l["world"], evidence_for(self.l, "repair", "II"))
        self.assertEqual(repaired["probability_exact"], "1")
        self.assertTrue(repaired["publication_warranted"])
        self.assertTrue(repaired["valid_support_available"])

    def test_exhaustive_independent_golden_conditionals(self):
        # Hand-coded 8-state truth table, independent of WorldBuilder and evaluate.
        golden = []
        for a, b, h in product((0, 1), repeat=3):
            mass = Fraction(1, 2) * (Fraction(1, 10) if b else Fraction(9, 10))
            mass *= Fraction(99, 100) if h else Fraction(1, 100)
            golden.append(({"A": a, "B": b, "H": h, "S": a if h else 1, "Y": int(a == 1 or b == 1)}, mass))
        enumerated = list(enumerate_states(self.l["world"]))
        self.assertEqual(enumerated, golden)
        # Every partial assignment of A/B/H/S, including impossible events.
        for assignments in product((None, 0, 1), repeat=4):
            observed = {n: value for n, value in zip(("A", "B", "H", "S"), assignments) if value is not None}
            rows = [(s, m) for s, m in golden if all(s[n] == v for n, v in observed.items())]
            denominator = sum((m for _, m in rows), Fraction(0))
            numerator = sum((m for s, m in rows if s["Y"]), Fraction(0))
            expected = str(numerator / denominator) if denominator else None
            evidence = [record(f"g{i}", "golden fixture", name, value, "q2")
                        for i, (name, value) in enumerate(observed.items())]
            result = assess(self.l["world"], evidence)
            with self.subTest(observed=observed):
                self.assertEqual(result["probability_exact"], expected)
                self.assertEqual(result["calculation"]["evidence_mass_exact"], str(denominator))

    def test_counterfactual_preserves_faulty_display(self):
        witnesses = counterfactual_witnesses(self.l["world"], self.l["initial_evidence"])
        witness = next(w for w in witnesses if w["intervention"] == {"B": 0})
        self.assertEqual(witness["state"], {"A": 0, "B": 0, "H": 0, "S": 1, "Y": 0})
        self.assertFalse(witness["truth_after"])
        self.assertFalse(counterfactual_witnesses(self.l["world"], evidence_for(self.l, "repair", "II")))

    def test_logical_support_distinct_from_policy_support(self):
        result = assess(self.l["world"], self.l["initial_evidence"])
        self.assertEqual(result["logical_status"], "underdetermined")
        self.assertEqual(result["support_judgment"], "supported")
        self.assertFalse(assess(self.l["world"], self.l["initial_evidence"], threshold="0.999")["publication_warranted"])

    def test_actual_truth_never_changes_information_relative_probability(self):
        evidence = evidence_for(self.l, "exact_facts", "II")
        lucky = assess(self.l["world"], evidence)
        false = assess(self.f["world"], evidence)
        self.assertEqual(lucky["probability_exact"], false["probability_exact"])
        self.assertNotEqual(lucky["truth"], false["truth"])


class MechanismValidityTests(unittest.TestCase):
    def test_all_mechanisms_have_independently_derived_golden_probabilities(self):
        initial_golden = {
            "false_premise_rescue": "1001/1010", "defective_sensors": "1001/1010",
            "dependent_corroboration": "100000/100901", "stale_evidence": "199/200",
            "causal_reversal": "100/101", "environmental_luck": "199/200",
            "conditional_evidence": "991/1000", "independent_repair": "1001/1010"}
        defeated_golden = {name: "1/2" for name in MECHANISMS}
        defeated_golden.update({name: "1/10" for name in (
            "false_premise_rescue", "defective_sensors", "conditional_evidence", "independent_repair")})
        blocks = generate_blocks(17, 8, "II", reliability="0.99", target_prior="0.5")
        self.assertEqual({b["mechanism"] for b in blocks}, set(MECHANISMS))
        for block in blocks:
            with self.subTest(mechanism=block["mechanism"]):
                self.assertTrue(validate_block(block)["eligible"])
                for case in block["cases"]:
                    self.assertEqual(assess(case["world"], case["initial_evidence"])["probability_exact"],
                                     initial_golden[block["mechanism"]])
                    result = assess(case["world"], evidence_for(case, "exact_facts", "II"))
                    self.assertEqual(result["probability_exact"], "1" if case["role"] == "S" else defeated_golden[block["mechanism"]])
                    if case["role"] == "L":
                        self.assertTrue(result["counterfactual_false_commitment_possible"])
                        repaired = assess(case["world"], evidence_for(case, "repair", "II"))
                        self.assertEqual(repaired["probability_exact"], "1")

    def test_source_dependence_and_independent_alternative(self):
        block = generate_blocks(1, 1, "II", ["dependent_corroboration"])[0]
        supported, lucky, _ = block["cases"]
        result = assess(lucky["world"], lucky["initial_evidence"])
        self.assertEqual(result["provenance"]["dependent_source_pairs"],
                         [{"sources": ["q1", "q2"], "shared_roots": ["q1"]}])
        self.assertFalse(result["route_valid"])
        independent = assess(supported["world"], supported["initial_evidence"])
        self.assertEqual(independent["provenance"]["dependent_source_pairs"], [])
        # An invalid initial report remains invalid; an exact independent route
        # repairs publication support without laundering that old source.
        repaired_evidence = evidence_for(lucky, "repair", "II")
        repaired = assess(lucky["world"], repaired_evidence)
        repair_id = lucky["repair_evidence"][0]["id"]
        self.assertFalse(repaired["route_valid"])
        self.assertIn([repair_id], repaired["alternative_valid_supports"])
        own_basis = assess(lucky["world"], repaired_evidence, [repair_id])
        self.assertTrue(own_basis["route_valid"])
        self.assertTrue(own_basis["route_sufficient"])

    def test_staleness_changes_temporal_route(self):
        block = generate_blocks(0, 1, "II", ["stale_evidence"])[0]
        self.assertEqual([actual_state(c["world"])["Time"] for c in block["cases"]],
                         ["current", "previous", "previous"])
        self.assertFalse(assess(block["cases"][1]["world"], block["cases"][1]["initial_evidence"])["route_valid"])

    def test_controls_cover_required_categories(self):
        block = generate_blocks(0, 1, include_controls=True)[0]
        controls = {c["control_type"]: c for c in block["cases"] if c["role"] == "control"}
        self.assertEqual(set(controls), set(CONTROLS))
        outcomes = {name: assess(c["world"], c["initial_evidence"]) for name, c in controls.items()}
        self.assertEqual(outcomes["reliably_supported_true"]["probability_exact"], "1")
        self.assertEqual(outcomes["reliably_supported_false"]["probability_exact"], "0")
        self.assertEqual(outcomes["underdetermined"]["probability_exact"], "1/2")
        self.assertTrue(outcomes["weak_true"]["truth"])
        self.assertFalse(outcomes["weak_true"]["publication_warranted"])
        self.assertFalse(outcomes["misleading_false"]["truth"])
        self.assertTrue(outcomes["misleading_false"]["publication_warranted"])
        self.assertFalse(outcomes["visible_defeater"]["publication_warranted"])
        self.assertTrue(outcomes["hidden_defeater"]["publication_warranted"])
        self.assertFalse(outcomes["independent_corroboration"]["provenance"]["dependent_source_pairs"])


class VisibilityAndGenerationTests(unittest.TestCase):
    def test_regime_two_initial_twins_identical_regime_one_diagnostic(self):
        for regime in ("I", "II"):
            for block in generate_blocks(22, 8, regime):
                self.assertTrue(validate_block(block)["valid"])
                initial_prompts = [render_initial(c) for c in block["cases"]]
                self.assertEqual(len(set(initial_prompts)), 1 if regime == "II" else 2)

    def test_factual_parity_frozen_parent_and_no_hidden_annotations(self):
        parent = '{"explanation":"literal frozen parent \\n end"}'
        for regime in ("I", "II"):
            for block in generate_blocks(4, 8, regime):
                for case in block["cases"]:
                    facts = render_continuation(case, parent, "exact_facts", regime)
                    audit = render_continuation(case, parent, "structured_audit", regime)
                    self.assertEqual(facts.split("\nAVAILABLE EVIDENCE\n")[1], audit.split("\nAVAILABLE EVIDENCE\n")[1])
                    self.assertEqual(evidence_for(case, "exact_facts", regime), evidence_for(case, "structured_audit", regime))
                    for condition in CONDITIONS:
                        prompt = render_continuation(case, parent, condition, regime)
                        self.assertIn(json.dumps(parent, ensure_ascii=True, separators=(",", ":")), prompt)
                        self.assertNotIn(case["id"], prompt)
                        self.assertNotIn(case["world"]["id"], prompt)
                        self.assertNotIn("realized_exogenous", prompt)
                        self.assertNotIn("structure_labels", prompt)
                    poisoned = copy.deepcopy(case)
                    poisoned["role"] = "SECRET_ROLE"
                    poisoned["structure_labels"] = {"secret": "HIDDEN_LABEL"}
                    for e in poisoned["initial_evidence"]:
                        e["oracle_probability"] = "SECRET_ORACLE"
                    self.assertEqual(render_initial(poisoned), render_initial(case))

    def test_sham_is_conditionally_uninformative_in_every_finite_state(self):
        for regime in ("I", "II"):
            for block in generate_blocks(1, 8, regime):
                for case in block["cases"]:
                    original = assess(case["world"], case["initial_evidence"])
                    sham = assess(case["world"], evidence_for(case, "sham", regime))
                    self.assertEqual(original["probability_exact"], sham["probability_exact"])
                    self.assertEqual(original["calculation"]["evidence_mass_exact"], sham["calculation"]["evidence_mass_exact"])
                    self.assertEqual(original["calculation"]["consistent_states"], sham["calculation"]["consistent_states"])

    def test_reproducible_complete_blocks_and_explicit_cohort(self):
        self.assertEqual(generate_blocks(123, 9), generate_blocks(123, 9))
        self.assertNotEqual(generate_blocks(123, 9), generate_blocks(124, 9))
        self.assertEqual(len({b["id"] for b in generate_blocks(1, 19)}), 19)
        self.assertTrue(all(len(b["cases"]) == 3 for b in generate_blocks(1, 9)))
        with self.assertRaisesRegex(ValueError, "naturally sampled"):
            generate_blocks(1, 1, cohort="natural")
        self.assertEqual(generate_blocks(1, 0), [])

    def test_seed_changes_actual_scientific_parameters_not_only_ids(self):
        blocks = generate_blocks(927, 24, "II", ["defective_sensors"])
        specifications = [json.dumps(c["cases"][0]["world"]["exogenous"], sort_keys=True) for c in blocks]
        self.assertEqual(len(set(specifications)), 24)
        self.assertEqual(blocks, generate_blocks(927, 24, "II", ["defective_sensors"]))
        self.assertNotEqual(specifications[0], json.dumps(generate_blocks(928, 1, "II", ["defective_sensors"])[0]["cases"][0]["world"]["exogenous"], sort_keys=True))

    def test_real_compositions_complexity_and_corroboration(self):
        combined = generate_blocks(4, 1, "II", ["stale_evidence+dependent_corroboration"],
                                   reliability="0.99", target_prior="0.5")[0]
        self.assertTrue(validate_block(combined)["eligible"])
        lucky = combined["cases"][1]
        self.assertEqual(assess(lucky["world"], lucky["initial_evidence"])["probability_exact"],
                         str(Fraction(199, 200) * Fraction(100000, 100901)))
        self.assertEqual(assess(lucky["world"], evidence_for(lucky, "exact_facts", "II"))["probability_exact"], "1/4")
        copied = generate_blocks(4, 1, "II", ["defective_sensors"], reliability="0.99",
                                 target_prior="0.5", source_complexity=4)[0]["cases"][1]
        self.assertEqual(assess(copied["world"], copied["initial_evidence"])["probability_exact"], "1001/1010")
        self.assertEqual(len(copied["initial_evidence"]), 4)
        self.assertEqual(len(assess(copied["world"], copied["initial_evidence"])["provenance"]["dependent_source_pairs"]), 6)
        corroborated = generate_blocks(4, 1, "II", ["defective_sensors"], reliability="0.99",
                                       target_prior="0.5", independent_repeat_count=1)[0]["cases"][1]
        posterior = assess(corroborated["world"], evidence_for(corroborated, "exact_facts", "II"))
        # Independent positive verifier: (.1)/( .1 + .9*.01 ).
        self.assertEqual(posterior["probability_exact"], "100/109")
        self.assertFalse(posterior["publication_warranted"])
        two = generate_blocks(4, 1, "II", ["defective_sensors"], reliability="0.99",
                              target_prior="0.5", independent_repeat_count=2)[0]
        self.assertFalse(two["eligible"])
        self.assertTrue(assess(two["cases"][1]["world"], evidence_for(two["cases"][1], "exact_facts", "II"))["publication_warranted"])
        review = generate_blocks(4, 1, "II", ["defective_sensors"], wording_variant="review")[0]
        plain = generate_blocks(4, 1, "II", ["defective_sensors"], wording_variant="plain")[0]
        self.assertNotEqual(render_initial(review["cases"][0]), render_initial(plain["cases"][0]))
        self.assertEqual(review["cases"][0]["world"]["exogenous"], plain["cases"][0]["world"]["exogenous"])

    def test_available_defeater_prevents_cherry_picked_route_sufficiency(self):
        case = crystal_fixture()["cases"][1]
        result = assess(case["world"], evidence_for(case, "exact_facts", "II"), ["e1"])
        self.assertEqual(result["basis_probability_exact"], "1001/1010")
        self.assertFalse(result["route_sufficient"])
        self.assertFalse(result["valid_support_available"])

    def test_malformed_world_evidence_and_visibility_fail_closed(self):
        case = crystal_fixture()["cases"][1]
        broken = copy.deepcopy(case["world"])
        broken["exogenous"][0]["distribution"][0]["probability"] = "-0.5"
        with self.assertRaises(ValueError):
            validate_world(broken)
        broken = copy.deepcopy(case["world"])
        broken["realized_exogenous"]["A"] = 8
        with self.assertRaises(ValueError):
            validate_world(broken)
        with self.assertRaisesRegex(ValueError, "limit"):
            assess(case["world"], case["initial_evidence"], max_states=7)
        with self.assertRaisesRegex(ValueError, "unique"):
            assess(case["world"], case["initial_evidence"] * 2)
        with self.assertRaises(ValueError):
            evidence_for(case, "exact_facts", "I")
        broken_case = copy.deepcopy(case)
        broken_case["regime"] = "I"
        with self.assertRaisesRegex(ValueError, "previously hidden"):
            evidence_for(broken_case, "structured_audit", "I")
        result = assess(case["world"], case["initial_evidence"], ["unknown"])
        self.assertFalse(result["route_valid"])
        self.assertFalse(result["route_sufficient"])
        self.assertEqual(result["unknown_basis_ids"], ["unknown"])


if __name__ == "__main__":
    unittest.main()
