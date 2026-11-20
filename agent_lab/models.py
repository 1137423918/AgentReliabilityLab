"""A deterministic fault-test model and an explicit local inference adapter."""

import contextlib
import os
from urllib.parse import urlsplit

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from deepagents.profiles import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    register_harness_profile,
)


class ScriptedMaintenanceModel(BaseChatModel):
    """Replay an explicit tool plan using durable messages, not an in-memory index."""

    model_name: str = "agentlab:scripted"
    plan: list[dict] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "agentlab-scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        completed = {m.tool_call_id for m in messages if isinstance(m, ToolMessage)}
        errors = [
            m for m in messages if isinstance(m, ToolMessage) and m.status == "error"
        ]
        if errors:
            raise RuntimeError(
                "Scripted tool plan failed; inspect the private checkpoint."
            )
        for index, step in enumerate(self.plan):
            call_id = f"planned-{index}"
            if call_id not in completed:
                message = AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "id": call_id,
                            "name": step["tool"],
                            "args": step["args"],
                            "type": "tool_call",
                        }
                    ],
                )
                return ChatResult(generations=[ChatGeneration(message=message)])
        return ChatResult(
            generations=[
                ChatGeneration(message=AIMessage(content="Patch prepared for review."))
            ]
        )


def build_model(spec: dict, *, request_budget=None):
    if "request_budget" in spec and request_budget is None:
        raise ValueError("Budgeted models require a manifest-bound request journal.")
    mode = spec.get("mode", "scripted")
    if request_budget is not None and mode != "local-openai":
        raise ValueError("Request budgets require local-openai mode.")
    if mode == "scripted":
        model = ScriptedMaintenanceModel(plan=spec.get("plan", []))
        profile_key = model.model_name
    elif mode == "local-openai":
        # Optional dependency; no cloud fallback or implicit API spend.
        from langchain_openai import ChatOpenAI

        model_class = ChatOpenAI
        client_options = {}
        if request_budget is not None:
            from agent_lab.request_budget import RequestBudgetError, make_http_client

            class BudgetedChatOpenAI(ChatOpenAI):
                def _generate(self, *args, **kwargs):
                    try:
                        return super()._generate(*args, **kwargs)
                    except Exception as error:
                        current = error
                        seen = set()
                        while current is not None and id(current) not in seen:
                            if isinstance(current, RequestBudgetError):
                                raise current from None
                            seen.add(id(current))
                            current = current.__cause__
                        raise

                async def _agenerate(self, *args, **kwargs):
                    raise RequestBudgetError(
                        "Budgeted worker supports synchronous model calls only."
                    )

                async def _astream(self, *args, **kwargs):
                    raise RequestBudgetError(
                        "Budgeted worker supports synchronous model calls only."
                    )
                    yield  # Keep the asynchronous streaming protocol without sending.

            model_class = BudgetedChatOpenAI

        endpoint = os.environ["AGENT_LAB_MODEL_URL"]
        parsed = urlsplit(endpoint)
        if parsed.scheme not in ("http", "https") or parsed.hostname not in (
            "127.0.0.1",
            "localhost",
            "::1",
        ):
            raise ValueError(
                "The local inference adapter requires a loopback endpoint."
            )
        sampling = {
            name: spec[name]
            for name in ("top_p", "presence_penalty", "extra_body")
            if name in spec
        }
        if request_budget is not None:
            client_options["http_client"] = make_http_client(request_budget)
        try:
            model = model_class(
                model=spec["model"],
                base_url=endpoint,
                api_key=os.environ.get("AGENT_LAB_MODEL_KEY", "local"),
                timeout=spec.get("timeout_seconds", 120),
                max_retries=0,
                temperature=spec.get("temperature", 0),
                max_tokens=spec.get("max_output_tokens", 1536),
                seed=spec.get("seed", 42),
                **sampling,
                **client_options,
            )
        except Exception:
            if request_budget is not None:
                client_options["http_client"].close()
            raise
        profile_key = "openai:" + spec["model"]
    else:
        raise ValueError(f"Unknown model mode: {mode}")
    try:
        register_harness_profile(
            profile_key,
            HarnessProfile(
                general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
                excluded_tools=frozenset({"task", "execute", "write_todos"}),
            ),
        )
    except Exception:
        if request_budget is not None:
            model.http_client.close()
        raise
    return model


@contextlib.contextmanager
def model_for_run(spec, request_budget=None):
    model = build_model(spec, request_budget=request_budget)
    try:
        yield model
    finally:
        if request_budget is not None:
            model.http_client.close()
