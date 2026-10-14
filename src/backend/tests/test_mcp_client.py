"""Smoke test: run the Cogito MCP server over stdio and call its tools."""

import asyncio
import os

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


async def main() -> None:
    # The SDK's stdio client only inherits a whitelist of env vars, so the
    # MongoDB URI must be passed explicitly via `env`.
    env = {
        **os.environ,
        "MONGODB_URI": "mongodb://localhost:27018/cogito?replicaSet=rs0&directConnection=true",
    }
    py = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".venv", "bin", "python")
    params = StdioServerParameters(
        command=py,
        args=[
            "-c",
            f"import sys; sys.path.insert(0,'{os.path.join(REPO, 'src', 'mcp_cogito')}');"
            "from server import mcp; mcp.run(transport='stdio')",
        ],
        cwd=os.path.join(REPO, "src", "backend"),
        env=env,
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("TOOLS:", [t.name for t in tools.tools])
            res = await session.call_tool(
                "ask_question", {"question": "What is the late delivery penalty?"}
            )
            print("ASK RESULT TYPE:", res.content[0].type)
            text = res.content[0].text
            print(text[:400])


if __name__ == "__main__":
    asyncio.run(main())