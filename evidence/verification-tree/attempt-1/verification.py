"""Keep verification processes tied to their worker's lifetime on Unix."""

import argparse
import ctypes
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


def enable_child_reaping() -> None:
    """Only call in the isolated Linux supervisor, before starting a verifier."""
    # An adopted child cannot reuse its PID until this process reaps it. Keep
    # SIGCHLD at its default so no inherited auto-reaping policy breaks that.
    signal.signal(signal.SIGCHLD, signal.SIG_DFL)
    children = Path(f"/proc/self/task/{os.getpid()}/children")
    children.read_text()  # Fail before launch when procfs is unavailable.
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


def reap_children() -> None:
    """Stop and reap adopted descendants, including new sessions/double forks."""
    children = Path(f"/proc/self/task/{os.getpid()}/children")
    while True:
        for pid in map(int, children.read_text().split()):
            try:
                waited, _ = os.waitpid(pid, os.WNOHANG)
                if waited == 0:
                    # This is our unreaped direct child, not an arbitrary PID
                    # from a system-wide process snapshot.
                    os.kill(pid, signal.SIGKILL)
            except ChildProcessError:
                continue
        try:
            while os.waitpid(-1, os.WNOHANG)[0]:
                pass
        except ChildProcessError:
            return
        # A killed parent can expose more adopted children. Keep the worker
        # lock until they are reaped, even during an uninterruptible OS wait.
        time.sleep(0.01)


def supervise(
    argv: list[str], owner_fd: int, timeout: float, *, reap_descendants: bool = False
) -> dict:
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
        if reap_descendants:
            process.kill()
            process.wait()
            reap_children()
        else:
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
    linux = sys.platform.startswith("linux")
    if linux:
        enable_child_reaping()
    result = supervise(
        args.argv[1:], args.owner_fd, args.timeout, reap_descendants=linux
    )
    try:
        os.write(args.result_fd, json.dumps(result).encode("utf-8"))
    except BrokenPipeError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
