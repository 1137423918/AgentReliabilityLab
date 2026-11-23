"""Private append-only wire evidence; recover a verified prefix after process death.

Checksums detect accidental damage, not a malicious owner. This log does not
resume an agent, replay tools, or prove that a request reached its server.
"""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat

MAX_BYTES = 8 * 1024**2
MAX_EVENTS = 192
MAX_FRAME_BYTES = 1024**2
ZERO = "0" * 64


class WireJournalError(ValueError):
    pass


def packed(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def _identity(owner, journal_id):
    if (
        not isinstance(owner, str)
        or not re.fullmatch(r"[a-f0-9]{64}", owner)
        or not isinstance(journal_id, str)
        or not re.fullmatch(r"[a-f0-9]{32}", journal_id)
    ):
        raise WireJournalError("Invalid wire journal identity")


def _limits(events, size):
    if (
        type(events) is not int
        or not 1 <= events <= MAX_EVENTS
        or type(size) is not int
        or not 1024 <= size <= MAX_BYTES
    ):
        raise WireJournalError("Invalid wire journal bounds")


def _event(event):
    common = {"channel", "kind", "body_base64", "body_bytes", "body_sha256"}
    if not isinstance(event, dict) or event.get("channel") not in {"mcp", "model"}:
        raise WireJournalError("Invalid wire event channel")
    if event.get("kind") == "client_request_attempt":
        expected = common | {"path", "method", "protocol_version"}
        if (
            not isinstance(event.get("path"), str)
            or not isinstance(event.get("method"), str)
            or not 1 <= len(event["path"]) <= 2048
            or not 1 <= len(event["method"]) <= 16
            or event.get("protocol_version") is not None
            and not isinstance(event["protocol_version"], str)
        ):
            raise WireJournalError("Invalid request metadata")
    elif event.get("kind") == "client_response":
        expected = common | {"status", "request_body_sha256"}
        if (
            type(event.get("status")) is not int
            or not 100 <= event["status"] <= 599
            or not isinstance(event.get("request_body_sha256"), str)
            or not re.fullmatch(r"[a-f0-9]{64}", event["request_body_sha256"])
        ):
            raise WireJournalError("Invalid response metadata")
    else:
        raise WireJournalError("Invalid wire event kind")
    if (
        set(event) != expected
        or not isinstance(event["body_base64"], str)
        or len(event["body_base64"]) > MAX_FRAME_BYTES
    ):
        raise WireJournalError("Unexpected wire fields or oversized body")
    raw = base64.b64decode(event["body_base64"], validate=True)
    if (
        type(event["body_bytes"]) is not int
        or event["body_bytes"] != len(raw)
        or hashlib.sha256(raw).hexdigest() != event["body_sha256"]
    ):
        raise WireJournalError("Wire body length or digest does not match")


class DurableWireEvents:
    """Create once in an admitted private state directory; never reopen for writing."""

    def __init__(
        self, path, owner, journal_id, *, max_events=MAX_EVENTS, max_bytes=MAX_BYTES
    ):
        _identity(owner, journal_id)
        _limits(max_events, max_bytes)
        self.path = Path(path)
        self.max_events, self.max_bytes = max_events, max_bytes
        self.events = []
        self.failed = False
        self.error_type = None
        self._next = 0
        self._previous = ZERO
        self._bytes = 0
        self._fd = os.open(
            self.path,
            os.O_WRONLY
            | os.O_APPEND
            | os.O_CREAT
            | os.O_EXCL
            | os.O_NOFOLLOW
            | os.O_CLOEXEC,
            0o600,
        )
        try:
            self._write_record(
                {
                    "type": "identity",
                    "version": 1,
                    "owner_sha256": owner,
                    "journal_id": journal_id,
                    "max_events": max_events,
                    "max_bytes": max_bytes,
                }
            )
            parent = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(parent)
            finally:
                os.close(parent)
        except BaseException:
            self.close()
            raise

    def _write_record(self, record):
        frame = {
            "sequence": self._next,
            "previous_sha256": self._previous,
            "record": record,
        }
        checksum = hashlib.sha256(packed(frame)).hexdigest()
        data = packed({**frame, "sha256": checksum}) + b"\n"
        if len(data) > MAX_FRAME_BYTES or self._bytes + len(data) > self.max_bytes:
            raise WireJournalError("Wire evidence byte limit exhausted")
        view = memoryview(data)
        while view:
            written = os.write(self._fd, view)
            if written <= 0:
                raise OSError("Wire journal write made no progress")
            view = view[written:]
        os.fsync(self._fd)
        self._next += 1
        self._previous = checksum
        self._bytes += len(data)

    def append(self, event):
        if self._fd is None or self.failed:
            raise WireJournalError(
                "Wire journal is closed or has a prior write failure"
            )
        try:
            if len(self.events) >= self.max_events:
                raise WireJournalError("Invalid wire event or event count exhausted")
            _event(event)
            saved = json.loads(packed(event))
            self._write_record({"type": "event", "event": saved})
            self.events.append(saved)
        except Exception as exc:
            self.failed, self.error_type = True, type(exc).__name__
            raise

    def close(self):
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def status(self):
        return {
            "file": self.path.name,
            "events_committed": len(self.events),
            "write_failed": self.failed,
            "write_error_type": self.error_type,
            "last_sequence": self._next - 1,
            "last_frame_sha256": self._previous,
            "committed_bytes": self._bytes,
            "closed": self._fd is None,
        }


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise WireJournalError("Duplicate frame key")
        result[key] = value
    return result


def read_wire_journal(path, owner, journal_id):
    """Read only. A torn final line is reported, never truncated or replayed.

    A newline-terminated corrupt frame rejects the file. A valid prefix does
    not assert workflow completion or that any unrecorded action did not occur.
    """
    _identity(owner, journal_id)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
            raise WireJournalError("Wire journal must be a bounded regular file")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(MAX_BYTES + 1)
    finally:
        os.close(fd)
    if len(data) > MAX_BYTES:
        raise WireJournalError("Wire journal exceeds its size bound")
    end = data.rfind(b"\n") + 1
    previous, events, identity = ZERO, [], None
    for sequence, line in enumerate(data[:end].splitlines()):
        if len(line) + 1 > MAX_FRAME_BYTES:
            raise WireJournalError("Wire frame exceeds its size bound")
        try:
            frame = json.loads(line, object_pairs_hook=_pairs)
            checksum = frame.pop("sha256")
            if (
                set(frame) != {"sequence", "previous_sha256", "record"}
                or type(frame["sequence"]) is not int
                or frame["sequence"] != sequence
                or frame["previous_sha256"] != previous
                or checksum != hashlib.sha256(packed(frame)).hexdigest()
            ):
                raise WireJournalError("Wire frame identity or checksum changed")
            record = frame["record"]
            if sequence == 0:
                if (
                    set(record)
                    != {
                        "type",
                        "version",
                        "owner_sha256",
                        "journal_id",
                        "max_events",
                        "max_bytes",
                    }
                    or record["type"] != "identity"
                    or type(record["version"]) is not int
                    or record["version"] != 1
                    or record["owner_sha256"] != owner
                    or record["journal_id"] != journal_id
                ):
                    raise WireJournalError(
                        "Wire journal belongs to a different attempt budget"
                    )
                _limits(record["max_events"], record["max_bytes"])
                identity = record
            else:
                if (
                    set(record) != {"type", "event"}
                    or record["type"] != "event"
                    or not isinstance(record["event"], dict)
                ):
                    raise WireJournalError("Invalid wire event record")
                _event(record["event"])
                events.append(record["event"])
            previous = checksum
        except (KeyError, ValueError, TypeError, AttributeError) as exc:
            raise WireJournalError("Missing or inconsistent wire frame") from exc
    if (
        identity is None
        or len(events) > identity["max_events"]
        or len(data) > identity["max_bytes"]
    ):
        raise WireJournalError("Missing identity or wire evidence bounds exceeded")
    return {
        "identity": identity,
        "events": events,
        "valid_bytes": end,
        "tail_bytes": len(data) - end,
        "last_frame_sha256": previous,
        "file_sha256": hashlib.sha256(data).hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--journal-id", required=True)
    args = parser.parse_args()
    result = read_wire_journal(args.path, args.owner, args.journal_id)
    # Raw bodies can contain audit capabilities; the CLI emits only metadata.
    fields = {
        "channel",
        "kind",
        "method",
        "path",
        "status",
        "body_bytes",
        "body_sha256",
        "request_body_sha256",
    }
    result["events"] = [
        {k: v for k, v in event.items() if k in fields} for event in result["events"]
    ]
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
