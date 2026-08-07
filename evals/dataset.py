"""Eval cases for the mcp-socrata-readonly server.

Each EvalCase is a natural-language prompt fed to Claude with the real MCP
tools attached. Grading checks which tools Claude chose to call (not exact
output values, since the underlying Socrata data changes over time).
"""
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional


@dataclass
class EvalCase:
    name: str
    prompt: str
    # Tool call is a pass if the model calls ANY of these tool names at least once.
    expected_tools: List[str]
    # Tool names the model must NOT call for this prompt.
    forbidden_tools: List[str] = field(default_factory=list)
    # If True, every call to an expected tool must return JSON without a top-level "error" key.
    must_not_error: bool = True
    # Optional async setup hook: async (session) -> dict of extra values merged
    # into `context` for use in prompt.format(**context). Runs before the prompt is sent.
    setup: Optional[Callable] = None


async def _setup_real_property_id(session):
    """Fetch a real propid from search_properties so comp_investigator has a valid target."""
    import json

    result = await session.call_tool(
        "search_properties", {"address": "ELDORADO", "limit": 1, "county": "collin"}
    )
    text = result.content[0].text
    records = json.loads(text)
    if isinstance(records, list) and records:
        return {"property_id": records[0]["propid"]}
    return {"property_id": "UNKNOWN"}


EVAL_CASES: List[EvalCase] = [
    EvalCase(
        name="list_states_no_args",
        prompt="What US states does this server currently support data for?",
        expected_tools=["list_supported_locations"],
    ),
    EvalCase(
        name="list_counties_in_state",
        prompt="Which counties in Texas (TX) are supported?",
        expected_tools=["list_supported_locations"],
    ),
    EvalCase(
        name="list_cities_in_county",
        prompt="List the cities and zip codes covered within Collin County.",
        expected_tools=["list_supported_locations"],
    ),
    EvalCase(
        name="discover_datasets",
        prompt="What Socrata datasets are available for Collin county?",
        expected_tools=["discover_county_datasets"],
    ),
    EvalCase(
        name="search_by_address",
        prompt="Search for up to 3 properties on ELDORADO in Collin county.",
        expected_tools=["search_properties"],
    ),
    EvalCase(
        name="search_by_owner_and_zip",
        prompt="Find properties in Collin county owned by someone with last name SMITH in zip code 75002.",
        expected_tools=["search_properties"],
    ),
    EvalCase(
        name="query_near_unsupported",
        prompt="Find properties within 2 miles of '123 Main St, Plano, TX'.",
        expected_tools=["query_properties_near"],
        # This tool intentionally returns a graceful "unavailable" error today;
        # don't fail the eval on that expected response.
        must_not_error=False,
    ),
    EvalCase(
        name="comp_investigator_real_property",
        prompt="Run a comp investigation on property id {property_id} in Collin county and tell me if the appraisal increase looks like an outlier.",
        expected_tools=["comp_investigator"],
        setup=_setup_real_property_id,
    ),
    EvalCase(
        name="no_tool_for_smalltalk",
        prompt="Hi, what can you help me with?",
        expected_tools=[],
        forbidden_tools=[
            "search_properties",
            "get_property_detail",
            "comp_investigator",
            "refresh_cache",
        ],
        must_not_error=False,
    ),
]
