import json
import asyncio
from tcp.tcp_client import TcpClient

from logger import get_logger

logger = get_logger(__name__)

class EvalClient:
    def __init__(self, secret_key, host, port, eval_client_read_buffer, eval_client_send_buffer):
        self.secret_key = secret_key
        self.tcp_client = TcpClient(secret_key, host, port, True)
        self.eval_client_read_buffer = eval_client_read_buffer
        self.eval_client_send_buffer = eval_client_send_buffer
    
    async def run(self):
        await self.tcp_client.run()
        await asyncio.gather(
            self.send(),
            self.read()
        )

    async def send(self):
        while True:
            try:
                message = await self.eval_client_send_buffer.get()
                logger.info(f"Sending message from eval_client: {message}")
                await self.tcp_client.send_message(message)
            except Exception as e:
                logger.error(f"Exception in Eval Client send: {e}")
                raise

    async def read(self):
        try:
            while True:
                success, message = await self.tcp_client.receive_message()
                if not success:
                    logger.warning(f"An error occurred while reading in eval_client")
                    break
                message = message.decode()
                await self.eval_client_read_buffer.put(message)
        except Exception as e:
            logger.error(f"Exception in Eval Client read: {e}")
            raise
        finally:
            await self.tcp_client.close_connection()
            