"""One-shot index provisioning (run before starting the API/worker)."""

import asyncio
import logging

from app import db

logging.basicConfig(level=logging.INFO)


async def main() -> None:
    await db.ensure_indexes()
    await db.probe_search()
    print("search mode:", db.search_mode_sync())


if __name__ == "__main__":
    asyncio.run(main())