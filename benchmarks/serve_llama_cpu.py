"""Launch one pinned llama.cpp CPU service with explicit resource limits.

The operator supplies a previously converted model and verified runtime. This
does not download weights, expose a public endpoint, or start a GPU backend.
"""

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import socket
import subprocess
import time


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            result.update(block)
    return result.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--library-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--port", type=int, default=18844)
    parser.add_argument("--wall-seconds", type=int, default=2400)
    args = parser.parse_args()
    if not 1 <= args.threads <= 4 or not 1 <= args.wall_seconds <= 2400:
        parser.error("Use 1-4 compute threads and at most 2400 service seconds")
    args.output.mkdir(parents=True)
    manifest = json.loads(args.manifest.read_text())
    if (
        digest(args.server) != manifest["server_sha256"]
        or digest(args.model) != manifest["model_sha256"]
    ):
        raise ValueError(
            "Server or derived model hash does not match the pinned manifest"
        )
    for root, files in (
        (args.library_dir, manifest["runtime_libraries"]),
        (args.server.parent, manifest.get("server_bundle", {})),
    ):
        for relative, expected in files.items():
            path = Path(relative)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("Runtime library paths must be relative")
            if digest(root / path) != expected:
                raise ValueError("Task-local runtime library hash mismatch")
    meminfo = dict(
        line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines()
    )
    available = int(meminfo["MemAvailable"].split()[0]) * 1024
    cpus, load = len(os.sched_getaffinity(0)), os.getloadavg()
    if available < 64 * 1024**3 or load[0] > cpus - args.threads:
        raise RuntimeError("Insufficient CPU or memory headroom; model was not loaded")
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", args.port)) == 0:
            raise RuntimeError("The task-specific loopback port is occupied")
    os.nice(max(0, 19 - os.getpriority(os.PRIO_PROCESS, 0)))
    resource.setrlimit(resource.RLIMIT_AS, (48 * 1024**3, 48 * 1024**3))
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("LLAMA_ARG_", "GGML_")) and key != "LD_PRELOAD"
    }
    environment.update(
        CUDA_VISIBLE_DEVICES="",
        OMP_NUM_THREADS=str(args.threads),
        OPENBLAS_NUM_THREADS=str(args.threads),
        MKL_NUM_THREADS=str(args.threads),
        LD_LIBRARY_PATH=str(args.library_dir.resolve())
        + ":"
        + str(args.server.parent.resolve()),
    )
    argv = [
        str(args.server.resolve()),
        "--model",
        str(args.model.resolve()),
        "--alias",
        "agentlab-qwen3-4b",
        "--host",
        "127.0.0.1",
        "--port",
        str(args.port),
        "--device",
        "none",
        "--n-gpu-layers",
        "0",
        "--threads",
        str(args.threads),
        "--threads-batch",
        str(args.threads),
        "--threads-http",
        "1",
        "--parallel",
        "1",
        "--ctx-size",
        "32768",
        "--n-predict",
        "1536",
        "--timeout",
        "180",
        "--temp",
        "0",
        "--seed",
        "42",
        "--jinja",
        "--reasoning-format",
        "none",
        "--chat-template-kwargs",
        '{"enable_thinking":false}',
        "--no-context-shift",
        "--cache-prompt",
        "--no-webui",
        "--no-slots",
    ]

    def stop(signum, frame):
        raise SystemExit(128 + signum)

    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, stop)
    started = time.monotonic()
    with (args.output / "server.log").open("wb") as log:
        process = subprocess.Popen(
            argv, env=environment, stdout=log, stderr=log, start_new_session=True
        )
        reason, forced, peak_rss = None, False, 0
        try:
            record = {
                "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "launcher_pid": os.getpid(),
                "pid": process.pid,
                "pid_start_ticks": Path(f"/proc/{process.pid}/stat")
                .read_text()
                .rsplit(")", 1)[1]
                .split()[19],
                "argv": argv,
                "available_memory_bytes": available,
                "cpus": cpus,
                "load": load,
                "device": "cpu",
                "threads": args.threads,
                "nice": os.getpriority(os.PRIO_PROCESS, 0),
                "address_space_limit_gib": 48,
                "peak_rss_limit_gib": 36,
                "service_wall_seconds": args.wall_seconds,
                "timeout_semantics": "native HTTP read/write limit; worker request timeout is separate",
                "manifest": manifest,
                "launcher_source_sha256": digest(Path(__file__)),
            }
            (args.output / "service.json").write_text(
                json.dumps(record, indent=2) + "\n"
            )
            while process.poll() is None:
                if time.monotonic() - started > args.wall_seconds:
                    reason = "service_wall_limit"
                    break
                try:
                    status = dict(
                        line.split(":", 1)
                        for line in Path(f"/proc/{process.pid}/status")
                        .read_text()
                        .splitlines()
                        if ":" in line
                    )
                    rss = int(status.get("VmRSS", "0 kB").split()[0]) * 1024
                    peak_rss = max(peak_rss, rss)
                    if peak_rss > 36 * 1024**3:
                        reason = "rss_limit"
                        break
                except FileNotFoundError:
                    pass
                time.sleep(0.5)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    forced = True
                    os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            (args.output / "shutdown.json").write_text(
                json.dumps(
                    {
                        "returncode": process.returncode,
                        "guard_reason": reason,
                        "forced_cleanup": forced,
                        "peak_sampled_rss_bytes": peak_rss,
                    },
                    indent=2,
                )
                + "\n"
            )
    return process.returncode


if __name__ == "__main__":
    raise SystemExit(main())
