"""
Eval harness for the mcp-socrata-readonly MCP server.

Spawns the real server over stdio, connects a real MCP client session to it,
and drives Claude through a standard tool-use loop against the live tool
schemas. Grades each case on which tools Claude chose to call (and whether
those calls errored), not on exact data values, since the underlying Socrata
data changes over time.

Usage:
    ANTHROPIC_API_KEY=... python evals/run_evals.py
    ANTHROPIC_API_KEY=... python evals/run_evals.py --model claude-sonnet-5 --case search_by_address
"""
import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from anthropic import Anthropic
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from evals.dataset import EVAL_CASES, EvalCase  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DEFAULT_MODEL = os.environ.get("ANTHROPIC_EVAL_MODEL", "claude-sonnet-5")
MAX_TURNS = 6


@dataclass
class CaseResult:
    name: str
    passed: bool
    called_tools: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    final_text: str = ""


def mcp_tools_to_anthropic(tools) -> List[Dict[str, Any]]:
    return [
        {
            "name": t.name,
            "description": t.description or "",
            "input_schema": t.inputSchema,
        }
        for t in tools
    ]


async def run_case(session: ClientSession, anthropic_tools, client: Anthropic, model: str, case: EvalCase) -> CaseResult:
    context = {}
    if case.setup:
        context = await case.setup(session)
    prompt = case.prompt.format(**context)

    messages = [{"role": "user", "content": prompt}]
    called_tools: List[str] = []
    tool_errors: List[str] = []
    final_text = ""

    for _ in range(MAX_TURNS):
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            tools=anthropic_tools,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if not tool_uses:
            final_text = "".join(b.text for b in response.content if b.type == "text")
            break

        tool_results = []
        for tu in tool_uses:
            called_tools.append(tu.name)
            result = await session.call_tool(tu.name, tu.input)
            text = "".join(getattr(c, "text", "") for c in result.content)
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict) and "error" in parsed:
                    tool_errors.append(f"{tu.name}: {parsed['error']}")
            except (json.JSONDecodeError, TypeError):
                pass
            tool_results.append(
                {"type": "tool_result", "tool_use_id": tu.id, "content": text}
            )
        messages.append({"role": "user", "content": tool_results})

        if response.stop_reason != "tool_use":
            final_text = "".join(b.text for b in response.content if b.type == "text")
            break
    else:
        final_text = "(max turns reached without a final answer)"

    reasons = []
    passed = True

    missing = [t for t in case.expected_tools if t not in called_tools]
    if missing:
        passed = False
        reasons.append(f"expected tool(s) not called: {missing}")

    forbidden_hit = [t for t in case.forbidden_tools if t in called_tools]
    if forbidden_hit:
        passed = False
        reasons.append(f"forbidden tool(s) called: {forbidden_hit}")

    if case.must_not_error and tool_errors:
        passed = False
        reasons.append(f"tool call(s) returned errors: {tool_errors}")

    return CaseResult(
        name=case.name,
        passed=passed,
        called_tools=called_tools,
        reasons=reasons,
        final_text=final_text,
    )


async def main_async(args):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY is not set.", file=sys.stderr)
        sys.exit(1)

    cases = EVAL_CASES
    if args.case:
        cases = [c for c in cases if c.name == args.case]
        if not cases:
            print(f"No eval case named '{args.case}'", file=sys.stderr)
            sys.exit(1)

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(Path(__file__).resolve().parent.parent / "main.py")],
    )
    anthropic_client = Anthropic()

    results: List[CaseResult] = []
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools_response = await session.list_tools()
            anthropic_tools = mcp_tools_to_anthropic(tools_response.tools)

            for case in cases:
                print(f"--- {case.name} ---")
                try:
                    result = await run_case(session, anthropic_tools, anthropic_client, args.model, case)
                except Exception as e:
                    result = CaseResult(name=case.name, passed=False, reasons=[f"exception: {e!r}"])
                results.append(result)
                status = "PASS" if result.passed else "FAIL"
                print(f"  {status} | tools called: {result.called_tools}")
                for reason in result.reasons:
                    print(f"    - {reason}")

    passed_count = sum(1 for r in results if r.passed)
    print(f"\n{passed_count}/{len(results)} eval cases passed")
    sys.exit(0 if passed_count == len(results) else 1)


def main():
    parser = argparse.ArgumentParser(description="Run MCP tool-use evals for mcp-socrata-readonly")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Anthropic model id to drive the eval")
    parser.add_argument("--case", default=None, help="Run only the named eval case")
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
