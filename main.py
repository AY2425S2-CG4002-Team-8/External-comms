import asyncio
import sys
from eval_client import EvalClient

async def main(args):
    secret_key, host, port = args
    eval_client = EvalClient(secret_key, host, port)
    await eval_client.initiate_eval_client()

if __name__ == '__main__':
    if len(sys.argv) != 4:
        sys.exit(1)
    asyncio.run(main(sys.argv[1:]))