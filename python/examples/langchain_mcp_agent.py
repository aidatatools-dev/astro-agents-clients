"""A LangChain / LangGraph agent with the Astro Agents MCP tools, plus paid finance data through the REST client.

    pip install langchain-mcp-adapters langgraph "langchain[anthropic]"
    pip install "astro-agents @ git+https://github.com/aidatatools-dev/astro-agents-clients#subdirectory=python"
    export ANTHROPIC_API_KEY=...            # or any chat model LangChain supports
    export ASTRO_CREDITS_TOKEN=astc_...     # prepaid credits for the paid routes
    python langchain_mcp_agent.py

MCP (https://astro-agent.dev/mcp, streamable HTTP, no auth) lets the agent discover the 22 tools and call the
free ones (astro_catalog, verify_result_hash; one free call on the $0.01-0.02 tools). MCP cannot carry a
payment, so a paid tool answers with the REST call to make: the agent gets the same data from the REST client
below, tool-wrapped, paid from ASTRO_CREDITS_TOKEN. Data for your own analysis, never a signal or forecast.
"""
import asyncio
import json

from langchain_core.tools import tool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent

from astro_agents import Client

astro = Client()   # ASTRO_CREDITS_TOKEN


@tool
def astro_event_calendar_paid(start: str, end: str, include: list[str] | None = None) -> str:
    """Exact UTC times of eclipses, planetary stations (Mercury retrograde...), ingresses and lunations between two
    dates (YYYY-MM-DD), from NASA/JPL DE440, with unix timestamps for backtests. $0.25 per call (prepaid credits)."""
    df = astro.events(start, end, include=include or ["eclipse", "station", "ingress", "lunation"])
    return df.reset_index().to_json(orient="records", date_format="iso")


@tool
def sky_analogues_paid(reference: str, direction: str = "past", bodies: list[str] | None = None) -> str:
    """Dates whose planetary positions best match a reference moment (UTC, e.g. 2026-10-29T00:00Z), ranked by a
    stated angular distance (degrees). $0.25 per call (prepaid credits)."""
    df = astro.analogues(reference, direction=direction, bodies=bodies or ["jupiter", "saturn", "uranus"],
                         min_separation_days=3650, top_n=5)
    return json.dumps({"matches": df[["time", "score"]].astype(str).to_dict("records"),
                       "result_sha256": df.attrs["result_sha256"]})


async def main() -> None:
    mcp = MultiServerMCPClient({"astro": {"url": "https://astro-agent.dev/mcp", "transport": "streamable_http"}})
    tools = await mcp.get_tools() + [astro_event_calendar_paid, sky_analogues_paid]
    agent = create_react_agent("anthropic:claude-sonnet-5-5", tools)
    question = ("List the eclipses and Mercury stations between 2026-11-01 and 2027-03-31 with their exact UTC "
                "times, then say which past dates had a Jupiter-Saturn-Uranus sky most like 2026-10-29.")
    out = await agent.ainvoke({"messages": [{"role": "user", "content": question}]})
    print(out["messages"][-1].content)


if __name__ == "__main__":
    asyncio.run(main())
