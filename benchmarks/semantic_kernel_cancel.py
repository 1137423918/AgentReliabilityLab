"""Reproduce Semantic Kernel cancellation cleanup with a real runtime and bounded child.

No model or external service is used. A timeout is classified as a callback hang only after both actual agent-waiting
and cleanup-entry markers were emitted. The owned child is always reaped.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

CHILD = r"""
import asyncio,faulthandler,json
from dataclasses import dataclass
from pathlib import Path
import semantic_kernel
from semantic_kernel.agents.runtime.core.agent_id import CoreAgentId as AgentId
from semantic_kernel.agents.runtime.core.cancellation_token import CancellationToken
from semantic_kernel.agents.runtime.core.message_context import MessageContext
from semantic_kernel.agents.runtime.core.routed_agent import RoutedAgent,message_handler
from semantic_kernel.agents.runtime.in_process.in_process_runtime import InProcessRuntime

@dataclass
class Request:
    pass

async def main():
    expected=Path(__import__('os').environ['SK_SUBJECT_SOURCE']).resolve()
    assert Path(semantic_kernel.__file__).resolve()==expected/'__init__.py'
    entered=asyncio.Event();cancelled=asyncio.Event();cleanup=[]
    class WaitingAgent(RoutedAgent):
        def __init__(self):super().__init__('Cancellable controlled work')
        @message_handler
        async def wait_for_work(self,message:Request,ctx:MessageContext)->Request:
            future=asyncio.get_running_loop().create_future()
            ctx.cancellation_token.link_future(future)
            entered.set()
            try:
                await future
            except asyncio.CancelledError:
                cancelled.set()
                raise
            return Request()
    token=CancellationToken()
    def on_cancel():
        print(json.dumps({'stage':'cleanup_entered'}),flush=True)
        faulthandler.dump_traceback_later(2)
        cleanup.append(token.is_cancelled())
        faulthandler.cancel_dump_traceback_later()
        print(json.dumps({'stage':'cleanup_returned','observed_cancelled':cleanup[-1]}),flush=True)
    token.add_callback(on_cancel)
    runtime=InProcessRuntime()
    await WaitingAgent.register(runtime,'waiting',WaitingAgent)
    runtime.start()
    response=asyncio.create_task(runtime.send_message(Request(),AgentId('waiting','default'),cancellation_token=token))
    await asyncio.wait_for(entered.wait(),5)
    print(json.dumps({'stage':'agent_waiting'}),flush=True)
    token.cancel()
    try:
        await asyncio.wait_for(response,5)
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError('Expected pending request cancellation')
    await asyncio.wait_for(cancelled.wait(),5)
    await runtime.stop_when_idle()
    await runtime.close()
    assert cleanup==[True]
    token.cancel()
    assert cleanup==[True]
    print(json.dumps({'stage':'complete','cleanup_calls':len(cleanup),'agent_cancelled':cancelled.is_set(),'request_cancelled':response.cancelled()}),flush=True)

asyncio.run(main())
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    args = parser.parse_args()
    repo, output = args.repo.resolve(), args.output.resolve()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    source = repo / "python"
    token = source / "semantic_kernel/agents/runtime/core/cancellation_token.py"
    environment = {
        **os.environ,
        "PYTHONPATH": str(source),
        "SK_SUBJECT_SOURCE": str(source / "semantic_kernel"),
        "OTEL_SDK_DISABLED": "true",
    }
    protocol_path = Path(__file__).with_name("semantic_kernel_cancel_protocol.json")
    protocol = json.loads(protocol_path.read_text())
    assert protocol["callback_trace_delay_seconds"] == 2
    assert protocol["runtime_event_wait_seconds"] == 5
    started = time.monotonic()
    with (output / "stdout.jsonl").open("wb") as stdout, (output / "stderr.log").open("wb") as stderr:
        process = subprocess.Popen(
            [str(args.python.absolute()), "-u", "-c", CHILD],
            env=environment,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
        )
        timed_out = False
        try:
            code = process.wait(timeout=protocol["runtime_child_wall_seconds"])
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
            code = process.wait(timeout=10)
    events = [json.loads(line) for line in (output / "stdout.jsonl").read_text().splitlines() if line.strip()]
    stages = [e["stage"] for e in events]
    complete = code == 0 and "complete" in stages
    observed_hang = (
        timed_out and "agent_waiting" in stages and "cleanup_entered" in stages and "cleanup_returned" not in stages
    )
    report = {
        "scope": "Real Semantic Kernel runtime cancelling one controlled pending request; callback reads its cancellation token; no model, GPU or network service",
        "protocol_sha256": hashlib.sha256(protocol_path.read_bytes()).hexdigest(),
        "base_commit": protocol["base_commit"],
        "source_sha256": hashlib.sha256(token.read_bytes()).hexdigest(),
        "benchmark_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "returncode": code,
        "timed_out": timed_out,
        "callback_hang_observed": observed_hang,
        "completed": complete,
        "duration_seconds": round(time.monotonic() - started, 3),
        "events": events,
        "traceback_sha256": hashlib.sha256((output / "stderr.log").read_bytes()).hexdigest(),
        "timeout_is_not_a_general_performance_metric": True,
    }
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report), flush=True)
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
