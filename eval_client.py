import json
import asyncio
from tcp.tcp_client import TcpClient

class EvalClient:
    def __init__(self, secret_key, host, port, eval_client_send_buffer):
        self.secret_key = secret_key
        self.tcp_client = TcpClient(secret_key, host, port)
        self.eval_client_send_buffer = eval_client_send_buffer
    
    async def run(self):
        await self.tcp_client.connect_to_server()
        await self.tcp_client.handshake()
        await asyncio.gather(
            self.send()
        )

    async def send(self):
        while True:
            try:
                message = await self.eval_client_send_buffer.get()
                print(f"Sending message from eval_client: {message}")
                await self.tcp_client.send_message(json.dumps(message))
            except Exception as e:
                print(f"Exception in msg_sender: {e}")
