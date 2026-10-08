"""Real ADK execution with scripted model responses and no model API calls."""
from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.agents.run_config import RunConfig
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import InMemoryRunner
from google.genai import types

from payment_tools import BoundPaymentTools


class ScriptedModel(BaseLlm):
    calls: list[dict]
    position: int = 0

    async def generate_content_async(self, llm_request: LlmRequest,
                                     stream: bool = False):
        if self.position < len(self.calls):
            call = self.calls[self.position]
            self.position += 1
            part = types.Part(function_call=types.FunctionCall(
                id=f"script-{self.position}", name=call["tool"],
                args=call.get("args", {})))
        else:
            part = types.Part(text="Script complete. Use the recorded tool results.")
        yield LlmResponse(content=types.Content(role="model", parts=[part]))


async def run_tools(adapter: BoundPaymentTools, calls: list[dict], *,
                    agent_name: str, session_id: str) -> dict:
    agent = LlmAgent(
        name=agent_name,
        model=ScriptedModel(model="haltseal-scripted-no-network", calls=calls),
        instruction="Use the bound tools. HOLD/REFUSE stop new sends. ACCEPT is not settlement.",
        tools=adapter.tools())
    runner = InMemoryRunner(agent=agent, app_name="haltseal_adk_example")
    try:
        await runner.session_service.create_session(
            app_name=runner.app_name, user_id="synthetic-user", session_id=session_id)
        results = []
        async for event in runner.run_async(
                user_id="synthetic-user", session_id=session_id,
                new_message=types.Content(role="user", parts=[types.Part(text="Run the scripted exercise.")]),
                run_config=RunConfig(max_llm_calls=len(calls) + 1)):
            for response in event.get_function_responses():
                results.append({"tool": response.name, "result": response.response})
        if len(results) != len(calls):
            raise RuntimeError("ADK did not execute every scripted tool call")
        return {"agent": agent_name, "adk_session": session_id, "tool_results": results}
    finally:
        await runner.close()
