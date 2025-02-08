import asyncio
import sys
from game_engine import GameEngine

async def main(arguments):
    secret_key, host, port = arguments
    print("Starting game engine")
    game_engine = GameEngine(secret_key, host, port)
    await game_engine.start()


if __name__ == '__main__':
    if len(sys.argv) != 4:
        sys.exit(1)

    if sys.platform.lower() in ["win32", "nt"]:
        from asyncio import set_event_loop_policy, WindowsSelectorEventLoopPolicy
        set_event_loop_policy(WindowsSelectorEventLoopPolicy())

    asyncio.run(main(sys.argv[1:]))