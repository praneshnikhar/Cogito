"""Smoke test: run the Cogito MCP server over stdio and call its tools."""

import asyncio
import os

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> None:
    # Set in the parent so the spawned server inherits it. Using the venv
    # python directly avoids `uv` re-exec stripping the environment.
    os.environ["MONGODB_URI"] = "mongodb://localhost:27018/cogito?replicaSet=rs0"
    py = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".venv", "bin", "python")
    params = StdioServerParameters(
        command=py,
        args=[
            "-c",
            "import sys; sys.path.insert(0,'/Users/pranesh/coding2/Cogito/src/mcp_cogito');"
            "from server import mcp; mcp.run(transport='stdio')",
        ],
        cwd="/Users/pranesh/coding2/Cogito/src/backend",
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