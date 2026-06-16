"""MAF agents + sequential workflow (data -> sanity -> narrative) + chat routing.

Both entry points are async generators yielding text deltas; the assistant router
wraps them in SSE. The sequential summary workflow chains the three agents by
feeding each agent's output forward as context and streams the final narrative
agent token-wise.
"""
from typing import AsyncIterator, Optional

from . import prompts, tools
from .config import make_chat_client


def _build_agents():
    from agent_framework import Agent

    client = make_chat_client()
    data_agent = Agent(client=client, name="data_agent",
                       instructions=prompts.DATA_AGENT, tools=tools.DATA_TOOLS)
    sanity_agent = Agent(client=client, name="sanity_agent",
                         instructions=prompts.SANITY_AGENT, tools=tools.SANITY_TOOLS)
    narrative_agent = Agent(client=client, name="narrative_agent",
                            instructions=prompts.NARRATIVE_AGENT, tools=tools.NARRATIVE_TOOLS)
    chat_agent = Agent(client=client, name="assistant",
                       instructions=prompts.DATA_AGENT + prompts.CHAT_ROUTING,
                       tools=tools.ALL_TOOLS)
    return data_agent, sanity_agent, narrative_agent, chat_agent


def _filter_context(filters: Optional[dict]) -> str:
    f = filters or {}
    year, month = f.get("year", 2024), f.get("month", 5)
    sector = f.get("sector", "ALL")
    return (f"Current dashboard filters: year={year}, month={month}, "
            f"sector={sector} (ALL = consolidated Group), period_id={year * 100 + month}.")


async def generate_summary(filters: Optional[dict] = None) -> AsyncIterator[str]:
    """Sequential workflow: data_agent -> sanity_agent -> narrative_agent (streamed)."""
    data_agent, sanity_agent, narrative_agent, _ = _build_agents()
    ctx = _filter_context(filters)

    data_out = await data_agent.run(
        f"{ctx}\nSummarize the period's KPI picture: sales, EBIT and margin, "
        f"SG&A, headcount and NWC, each with vs PY/CF/BP variances.")
    sanity_out = await sanity_agent.run(
        f"{ctx}\nList the open issues for this period and state which block MBR submission.")

    final_prompt = (f"{ctx}\n\nKPI summary from the data analyst:\n{data_out.text}\n\n"
                    f"Sanity-check findings:\n{sanity_out.text}\n\n"
                    f"Write the executive summary now.")
    async for update in narrative_agent.run(final_prompt, stream=True):
        if update.text:
            yield update.text


async def chat(messages: list, filters: Optional[dict] = None) -> AsyncIterator[str]:
    """Routed assistant chat over the full tool set; multi-turn via message history."""
    from agent_framework import Message

    _, _, _, chat_agent = _build_agents()
    history = [Message(role="system", contents=[_filter_context(filters)])]
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if content:
            history.append(Message(role=role, contents=[content]))

    async for update in chat_agent.run(history, stream=True):
        if update.text:
            yield update.text
