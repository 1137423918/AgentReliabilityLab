"""A deterministic fault-test model and an explicit local inference adapter."""

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


def build_model(spec: dict):
    mode = spec.get("mode", "scripted")
    if mode == "scripted":
        model = ScriptedMaintenanceModel(plan=spec.get("plan", []))
        profile_key = model.model_name
    elif mode == "local-openai":
        # Optional dependency; no cloud fallback or implicit API spend.
        from langchain_openai import ChatOpenAI

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
        model = ChatOpenAI(
            model=spec["model"],
            base_url=endpoint,
            api_key=os.environ.get("AGENT_LAB_MODEL_KEY", "local"),
            timeout=spec.get("timeout_seconds", 120),
            max_retries=0,
            temperature=0,
            max_tokens=spec.get("max_output_tokens", 1536),
            seed=spec.get("seed", 42),
        )
        profile_key = "openai:" + spec["model"]
    else:
        raise ValueError(f"Unknown model mode: {mode}")
    register_harness_profile(
        profile_key,
        HarnessProfile(
            general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
            excluded_tools=frozenset({"task", "execute", "write_todos"}),
        ),
    )
    return model
