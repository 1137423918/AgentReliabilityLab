"""Offline diagnostics for already parsed tool calls, without semantic grading.

Requires the jsonschema/referencing versions in extras/mcp-agent/uv.lock.
No coercion, tool execution, network retrieval, defaults or answer comparison.
Diagnostics contain counts and keyword names, never argument values.
"""

from __future__ import annotations

from collections import Counter
import math
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from referencing import Registry
from referencing.exceptions import NoSuchResource, Unresolvable

DIALECT = "https://json-schema.org/draft/2020-12/schema"


def _deny_retrieval(uri: str):
    raise NoSuchResource(ref=uri)


def _json_domain(value: Any, active: set[int] | None = None) -> bool:
    """Exclude Python-only instances and non-finite JSON extensions."""
    if value is None or type(value) in (bool, int, str):
        return True
    if type(value) is float:
        return math.isfinite(value)
    if type(value) not in (dict, list):
        return False
    active = set() if active is None else active
    if id(value) in active:
        return False
    active.add(id(value))
    try:
        if isinstance(value, dict):
            return all(type(k) is str and _json_domain(v, active) for k, v in value.items())
        return all(_json_domain(v, active) for v in value)
    finally:
        active.remove(id(value))


class Contract:
    """One declared schema interpreted under fixed Draft 2020-12 semantics.

    Syntactic eligibility does not guarantee that all references resolve for
    every instance. A reference needed at validation time is unassessable if
    absent from the local document; remote resources are never fetched.
    """

    def __init__(self, schema: Any):
        self.validator = None
        self.status = "schema_eligible"
        self.schema_error_keywords: list[str] = []
        if not isinstance(schema, (dict, bool)) or not _json_domain(schema):
            self.status = "schema_invalid"
            return
        if isinstance(schema, dict):
            dialect = schema.get("$schema", DIALECT)
            if not isinstance(dialect, str) or dialect.rstrip("#") != DIALECT:
                self.status = "unsupported_dialect"
                return
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError as exc:
            self.status = "schema_invalid"
            self.schema_error_keywords = [str(exc.validator)]
            return
        self.validator = Draft202012Validator(
            schema, registry=Registry(retrieve=_deny_retrieval), format_checker=None
        )

    def assess(self, arguments: Any) -> dict:
        if type(arguments) is not dict:
            return {"status": "arguments_not_object", "violations": {}}
        if not _json_domain(arguments):
            return {"status": "arguments_not_json", "violations": {}}
        if self.validator is None:
            return {"status": self.status, "violations": {}}
        try:
            errors = list(self.validator.iter_errors(arguments))
        except Unresolvable:
            return {"status": "reference_unassessable", "violations": {}}
        violations = dict(sorted(Counter(str(e.validator) for e in errors).items()))
        return {"status": "schema_violations" if errors else "schema_valid", "violations": violations}


def contracts_for_tools(tools: list[dict], projection=None) -> dict[str, list[Contract]]:
    """Keep duplicate names rather than silently overwriting a contract."""
    contracts: dict[str, list[Contract]] = {}
    for tool in tools:
        name = tool.get("name")
        if not isinstance(name, str):
            continue
        schema = tool.get("parameters")
        if projection is not None:
            schema = projection(schema)
        contracts.setdefault(name, []).append(Contract(schema))
    return contracts


def diagnose_calls(calls: Any, contracts: dict[str, list[Contract]]) -> dict:
    """Do not reparse raw text or collapse falsey arguments into an empty dict.

    The presence of `parameters` takes precedence over `arguments`, including
    when parameters is null or empty. There are no nested OpenAI envelopes in
    this parsed-call interface. Case validity requires at least one call.
    """
    if type(calls) is not list:
        return {"status": "calls_not_list", "call_count": None, "calls": []}
    rows = []
    for call in calls:
        if type(call) is not dict or not isinstance(call.get("name"), str) or not call["name"]:
            row = {"status": "call_envelope_invalid", "violations": {}}
        else:
            matches = contracts.get(call["name"], [])
            if not matches:
                row = {"status": "unknown_tool", "violations": {}}
            elif len(matches) != 1:
                row = {"status": "ambiguous_tool", "violations": {}}
            elif "parameters" not in call and "arguments" not in call:
                row = {"status": "arguments_missing", "violations": {}}
            else:
                arguments = call["parameters"] if "parameters" in call else call["arguments"]
                row = matches[0].assess(arguments)
        rows.append(row)
    status = "all_calls_schema_valid" if rows and all(r["status"] == "schema_valid" for r in rows) else "not_all_calls_schema_valid"
    if not rows:
        status = "no_parsed_calls"
    return {"status": status, "call_count": len(calls), "calls": rows}
