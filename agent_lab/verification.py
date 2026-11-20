"""Keep verification processes tied to their worker's lifetime on Unix."""

import argparse
import json
import os
import select
import signal
import subprocess
import sys
import time
from pathlib import Path


class VerificationError(RuntimeError):
    """The supervisor failed before a verification result could be recorded."""


def run_command(
    argv, *, cwd: Path, environment: dict, stream, timeout: float, lock_fd: int
):
    owner_read, owner_write = os.pipe()
    result_read, result_write = os.pipe()
    supervisor = None
    try:
        supervisor = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "agent_lab.verification",
                "--owner-fd",
                str(owner_read),
                "--result-fd",
                str(result_write),
                "--timeout",
                str(timeout),
                "--",
                *argv,
            ],
            cwd=cwd,
            env=environment,
            stdout=stream,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            pass_fds=(owner_read, result_write, lock_fd),
        )
        os.close(owner_read)
        owner_read = -1
        os.close(result_write)
        result_write = -1
        code = supervisor.wait()
        if code:
            raise VerificationError("Verification supervisor failed; inspect its log.")
        result = json.loads(os.read(result_read, 4096))
        return result["returncode"], result["timed_out"]
    finally:
        # EOF tells the supervisor that this owner is gone, including on SIGKILL.
        os.close(owner_write)
        if supervisor is not None:
            supervisor.wait()
        for descriptor in (owner_read, result_read, result_write):
            if descriptor >= 0:
                os.close(descriptor)


def supervise(argv: list[str], owner_fd: int, timeout: float) -> dict:
    process = subprocess.Popen(argv, start_new_session=True, close_fds=True)
    timed_out = False
    try:
        deadline = time.monotonic() + timeout
        while process.poll() is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            if select.select([owner_fd], [], [], min(remaining, 0.1))[0]:
                if not os.read(owner_fd, 1):
                    break
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
    return {"returncode": process.returncode, "timed_out": timed_out}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner-fd", type=int, required=True)
    parser.add_argument("--result-fd", type=int, required=True)
    parser.add_argument("--timeout", type=float, required=True)
    parser.add_argument("argv", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    result = supervise(args.argv[1:], args.owner_fd, args.timeout)
    try:
        os.write(args.result_fd, json.dumps(result).encode("utf-8"))
    except BrokenPipeError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
