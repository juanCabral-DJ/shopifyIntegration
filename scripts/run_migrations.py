import asyncio
import sys
from alembic import command
from alembic.config import Config

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

def main() -> None:
    config = Config("alembic.ini")
    command.upgrade(config, "head")


if __name__ == "__main__":
    asyncio.run(asyncio.to_thread(main))
