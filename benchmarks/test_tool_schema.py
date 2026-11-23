"""Semantic boundary controls; run on an authorized server, not model tests."""

import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_lab.tool_schema import Contract, contracts_for_tools, diagnose_calls  # noqa: E402


class ContractControls(unittest.TestCase):
    def test_missing_required_and_no_mutation(self):
        schema = {"type": "object", "properties": {"x": {"type": "integer", "default": 4}}, "required": ["x"]}
        before = copy.deepcopy(schema)
        args = {}
        result = Contract(schema).assess(args)
        self.assertEqual(result, {"status": "schema_violations", "violations": {"required": 1}})
        self.assertEqual(schema, before)
        self.assertEqual(args, {})

    def test_bool_is_not_integer_but_integral_float_is(self):
        contract = Contract({"properties": {"x": {"type": "integer"}}})
        self.assertEqual(contract.assess({"x": True})["violations"], {"type": 1})
        self.assertEqual(contract.assess({"x": 2.0})["status"], "schema_valid")

    def test_nested_array_enum_and_numeric_constraints(self):
        contract = Contract({"properties": {"rows": {"type": "array", "items": {"type": "object", "properties": {"mode": {"enum": ["read"]}, "n": {"type": "number", "minimum": 0}}, "required": ["mode"]}}}})
        self.assertEqual(contract.assess({"rows": [{"mode": "write", "n": -1}, {}]})["violations"], {"enum": 1, "minimum": 1, "required": 1})

    def test_optional_and_additional_properties_default_allow(self):
        self.assertEqual(Contract({"properties": {"x": {"type": "string"}}}).assess({"other": 1})["status"], "schema_valid")
        self.assertEqual(Contract({"additionalProperties": False}).assess({"other": 1})["violations"], {"additionalProperties": 1})

    def test_format_is_annotation_without_checker(self):
        self.assertEqual(Contract({"properties": {"x": {"format": "email"}}}).assess({"x": "not an email"})["status"], "schema_valid")

    def test_invalid_alias_schema_and_unsupported_dialect(self):
        self.assertEqual(Contract({"type": "dict"}).status, "schema_invalid")
        self.assertEqual(Contract({"$schema": "http://json-schema.org/draft-07/schema#"}).status, "unsupported_dialect")
        self.assertEqual(Contract(None).status, "schema_invalid")

    def test_local_reference_and_remote_reference_never_network(self):
        local = {"$defs": {"positive": {"type": "integer", "minimum": 1}}, "properties": {"x": {"$ref": "#/$defs/positive"}}}
        self.assertEqual(Contract(local).assess({"x": 0})["violations"], {"minimum": 1})
        with patch("socket.socket", side_effect=AssertionError("network forbidden")):
            remote = Contract({"$ref": "https://example.invalid/private-schema"})
            self.assertEqual(remote.assess({})["status"], "reference_unassessable")

    def test_json_domain_rejects_python_extensions(self):
        contract = Contract({})
        for args in [{"x": float("nan")}, {"x": float("inf")}, {1: "x"}, {"x": (1, 2)}]:
            with self.subTest(args=str(type(args))):
                self.assertEqual(contract.assess(args)["status"], "arguments_not_json")
        self.assertEqual(contract.assess([])["status"], "arguments_not_object")

    def test_combinators_and_boolean_schemas(self):
        self.assertEqual(Contract(False).assess({})["status"], "schema_violations")
        self.assertEqual(Contract(True).assess({})["status"], "schema_valid")
        self.assertEqual(Contract({"oneOf": [{"required": ["a"]}, {"required": ["b"]}]}).assess({"a": 1, "b": 2})["violations"], {"oneOf": 1})

    def test_no_vacuous_case_pass_or_unknown_name_success(self):
        contracts = contracts_for_tools([{"name": "f", "parameters": {}}])
        self.assertEqual(diagnose_calls([], contracts)["status"], "no_parsed_calls")
        self.assertEqual(diagnose_calls(None, contracts)["status"], "calls_not_list")
        self.assertEqual(diagnose_calls([{"name": "missing", "parameters": {}}], contracts)["calls"][0]["status"], "unknown_tool")
        self.assertEqual(diagnose_calls([{}], contracts)["calls"][0]["status"], "call_envelope_invalid")

    def test_duplicate_name_not_silently_overwritten(self):
        contracts = contracts_for_tools([{"name": "f", "parameters": {}}]*2)
        self.assertEqual(diagnose_calls([{"name": "f", "parameters": {}}], contracts)["calls"][0]["status"], "ambiguous_tool")

    def test_parameter_presence_precedence_and_falsey_inputs(self):
        contracts = contracts_for_tools([{"name": "f", "parameters": {"required": ["x"]}}])
        cases = [({"parameters": None, "arguments": {"x": 1}}, "arguments_not_object"), ({"parameters": {}, "arguments": {"x": 1}}, "schema_violations"), ({"parameters": False}, "arguments_not_object"), ({}, "arguments_missing"), ({"arguments": {"x": 1}}, "schema_valid")]
        for fields, status in cases:
            call = {"name": "f", **fields}
            before = json.dumps(call, sort_keys=True)
            result = diagnose_calls([call], contracts)
            self.assertEqual(result["calls"][0]["status"], status)
            self.assertEqual(json.dumps(call, sort_keys=True), before)

    def test_schema_failure_is_not_model_violation(self):
        contracts = contracts_for_tools([{"name": "f", "parameters": {"type": "list(str)"}}])
        result = diagnose_calls([{"name": "f", "parameters": {}}], contracts)
        self.assertEqual(result["calls"][0], {"status": "schema_invalid", "violations": {}})


if __name__ == "__main__":
    unittest.main(verbosity=2)
