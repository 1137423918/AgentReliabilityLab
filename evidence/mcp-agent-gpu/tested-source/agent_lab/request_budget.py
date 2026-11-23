"""Conservative, durable reservations for model HTTP attempts, not token costs."""

import contextlib
import fcntl
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


class RequestBudgetError(ValueError):
    """A missing, inconsistent, unsupported or exhausted request budget."""


class RequestBudgetExhausted(RequestBudgetError):
    """The next serialized request would exceed the declared limits."""


def validate_limits(value):
    keys = {"max_requests", "max_request_bytes", "max_total_request_bytes"}
    if not isinstance(value, dict) or set(value) != keys:
        raise RequestBudgetError("Declare all three model request budget limits.")
    if any(type(v) is not int or v < 1 for v in value.values()):
        raise RequestBudgetError(
            "Model request budget limits must be positive integers."
        )
    if value["max_requests"] > 10000 or value["max_request_bytes"] > 64 * 1024**2:
        raise RequestBudgetError(
            "Model request budget exceeds supported journal/body bounds."
        )
    return dict(value)


def task_limits(task):
    model = task.get("model", {})
    enabled = "model_request_budget_v1" in task.get("required_features", [])
    declared = "request_budget" in model
    if enabled != declared:
        raise RequestBudgetError(
            "Declare model_request_budget_v1 and request_budget together."
        )
    if not enabled:
        return None
    if model.get("mode") != "local-openai":
        raise RequestBudgetError("Model request budgets require local-openai mode.")
    return validate_limits(model["request_budget"])


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def atomic_save(path, value):
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            os.chmod(temporary, 0o600)
            json.dump(value, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


class RequestBudget:
    """One private journal shared by all attempts in a maintenance/repair run.

    Atomic rename + fsync completes before transport is allowed to send. Unknown
    in-flight, failed and timed-out requests remain charged. Checksums detect
    accidental changes; this is not a journal authenticated against a hostile
    owner who can rewrite both journal and manifest.
    """

    def __init__(
        self, directory, owner_sha256, limits, journal_id=None, *, create=False
    ):
        self.directory = Path(directory)
        self.path = self.directory / "model-requests.json"
        self.limits = validate_limits(limits)
        self.owner = owner_sha256
        self.journal_id = journal_id
        with self.lock():
            if self.path.is_symlink():
                raise RequestBudgetError("Model request journal cannot be a symlink.")
            if not self.path.exists():
                if not create:
                    raise RequestBudgetError(
                        "Model request journal is missing; budget cannot reset."
                    )
                self.journal_id = uuid4().hex
                self.write([])
            state = self.read()
            self.journal_id = state["identity"]["journal_id"]

    @contextlib.contextmanager
    def lock(self):
        descriptor = os.open(
            self.directory / "model-requests.lock",
            os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW,
            0o600,
        )
        with os.fdopen(descriptor, "a") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)

    @property
    def identity(self):
        return {
            "journal_id": self.journal_id,
            "owner_sha256": self.owner,
            "limits": self.limits,
        }

    def read(self):
        try:
            if self.path.is_symlink() or self.path.stat().st_size > 16 * 1024**2:
                raise ValueError("Invalid journal file")
            state = json.loads(self.path.read_text())
            if (
                set(state) != {"version", "identity", "reservations", "checksum"}
                or type(state["version"]) is not int
                or state["version"] != 1
            ):
                raise ValueError("Invalid journal version")
            payload = {k: v for k, v in state.items() if k != "checksum"}
            if digest(payload) != state["checksum"]:
                raise ValueError("Invalid journal checksum")
            identity = state["identity"]
            if (
                set(identity) != {"journal_id", "owner_sha256", "limits"}
                or identity["owner_sha256"] != self.owner
                or identity["limits"] != self.limits
                or not isinstance(identity["journal_id"], str)
                or len(identity["journal_id"]) != 32
                or any(c not in "0123456789abcdef" for c in identity["journal_id"])
                or (
                    self.journal_id is not None
                    and identity["journal_id"] != self.journal_id
                )
            ):
                raise ValueError("Journal owner or policy changed")
            entries = state["reservations"]
            if (
                not isinstance(entries, list)
                or len(entries) > self.limits["max_requests"]
            ):
                raise ValueError("Invalid journal entries")
            for i, entry in enumerate(entries, 1):
                if (
                    set(entry)
                    != {
                        "sequence",
                        "request_body_sha256",
                        "request_body_bytes",
                        "reserved_at",
                        "path",
                        "transport_observation",
                        "http_status",
                    }
                    or type(entry["sequence"]) is not int
                    or entry["sequence"] != i
                    or type(entry["request_body_bytes"]) is not int
                    or not 1
                    <= entry["request_body_bytes"]
                    <= self.limits["max_request_bytes"]
                    or not isinstance(entry["request_body_sha256"], str)
                    or len(entry["request_body_sha256"]) != 64
                    or any(
                        c not in "0123456789abcdef"
                        for c in entry["request_body_sha256"]
                    )
                    or not isinstance(entry["reserved_at"], str)
                    or not isinstance(entry["path"], str)
                    or entry["transport_observation"]
                    not in ("reserved", "headers_received", "transport_error")
                    or (
                        (entry["transport_observation"] == "headers_received")
                        != (entry["http_status"] is not None)
                    )
                    or (
                        entry["http_status"] is not None
                        and (
                            type(entry["http_status"]) is not int
                            or not 100 <= entry["http_status"] <= 599
                        )
                    )
                ):
                    raise ValueError("Invalid reservation")
            if (
                sum(e["request_body_bytes"] for e in entries)
                > self.limits["max_total_request_bytes"]
            ):
                raise ValueError("Invalid total request size")
            return state
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise RequestBudgetError(
                "Model request journal is missing or inconsistent; refusing reset."
            ) from error

    def write(self, entries):
        payload = {"version": 1, "identity": self.identity, "reservations": entries}
        atomic_save(self.path, {**payload, "checksum": digest(payload)})

    def reserve(self, body, path):
        with self.lock():
            entries = self.read()["reservations"]
            if (
                len(entries) >= self.limits["max_requests"]
                or not 1 <= len(body) <= self.limits["max_request_bytes"]
                or sum(e["request_body_bytes"] for e in entries) + len(body)
                > self.limits["max_total_request_bytes"]
            ):
                raise RequestBudgetExhausted(
                    "Persistent model request budget exhausted before network send."
                )
            sequence = len(entries) + 1
            entries.append(
                {
                    "sequence": sequence,
                    "request_body_sha256": hashlib.sha256(body).hexdigest(),
                    "request_body_bytes": len(body),
                    "reserved_at": datetime.now(timezone.utc).isoformat(),
                    "path": path,
                    "transport_observation": "reserved",
                    "http_status": None,
                }
            )
            self.write(entries)
            return sequence

    def observe(self, sequence, status=None):
        with self.lock():
            entries = self.read()["reservations"]
            entry = entries[sequence - 1]
            if entry["transport_observation"] != "reserved":
                raise RequestBudgetError(
                    "Model request observation was already recorded."
                )
            entry.update(
                transport_observation="headers_received"
                if status is not None
                else "transport_error",
                http_status=status,
            )
            self.write(entries)

    def summary(self):
        with self.lock():
            entries = self.read()["reservations"]
            return {
                **self.identity,
                "reserved_requests": len(entries),
                "reserved_request_body_bytes": sum(
                    e["request_body_bytes"] for e in entries
                ),
                "unobserved_reservations": sum(
                    e["transport_observation"] == "reserved" for e in entries
                ),
            }


def make_http_client(budget):
    """Guard the final serialized JSON body at the actual sync transport boundary."""
    import httpx

    class BudgetTransport(httpx.BaseTransport):
        def __init__(self):
            self.inner = httpx.HTTPTransport(retries=0)

        def handle_request(self, request):
            if (
                request.url.host not in ("127.0.0.1", "localhost", "::1")
                or request.url.scheme not in ("http", "https")
                or request.method != "POST"
                or not request.url.path.endswith("/chat/completions")
            ):
                raise RequestBudgetError(
                    "Budgeted transport supports only loopback chat completions."
                )
            sequence = budget.reserve(request.read(), request.url.path)
            try:
                response = self.inner.handle_request(request)
            except Exception:
                budget.observe(sequence)
                raise
            try:
                budget.observe(sequence, response.status_code)
            except Exception:
                response.close()
                raise
            return response

        def close(self):
            self.inner.close()

    return httpx.Client(
        transport=BudgetTransport(), follow_redirects=False, trust_env=False
    )
