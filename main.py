import asyncio
import sys
from game_engine import GameEngine
from logger import get_logger

logger = get_logger(__name__)

async def main(arguments):
    port = arguments[0]
    logger.info("Starting game engine")
    game_engine = GameEngine(port)
    await game_engine.run()


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit(1)

    if sys.platform.lower() in ["win32", "nt"]:
        from asyncio import set_event_loop_policy, WindowsSelectorEventLoopPolicy
        set_event_loop_policy(WindowsSelectorEventLoopPolicy())

    asyncio.run(main(sys.argv[1:]))