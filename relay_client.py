import asyncio
from tcp.tcp_client import TcpClient
from logger import get_logger

logger = get_logger(__name__)

class RelayClient:
    def __init__(self, secret_key, host, port, relay_client_read_buffer, relay_client_send_buffer):
        self.secret_key = secret_key
        self.tcp_client = TcpClient(secret_key, host, port, False, max_reconnect_attempts=5)
        self.relay_client_read_buffer = relay_client_read_buffer
        self.relay_client_send_buffer = relay_client_send_buffer
    
    async def run(self):
        await self.tcp_client.run()
        await asyncio.gather(
            asyncio.create_task(self.send()),
            asyncio.create_task(self.read())
        )

    async def send(self):
        while True:
            try:
                message = await self.relay_client_send_buffer.get()
                logger.info(f"Sending message to eval_client: {message}")
                await self.tcp_client.send_message(message)
            except Exception as e:
                logger.error(f"Exception in msg_sender: {e}")

    async def read(self):
        try:
            while True:
                success, message = await self.tcp_client.receive_message()
                if not success:
                    logger.info(f"Error in reading packet from server")
                    break
                message = message.decode()
                await self.relay_client_read_buffer.put(message)
        except Exception as e:
            logger.error(f"Exception in Relay Client read: {e}")
            raise
        finally:
            await self.tcp_client.close_connection()
            