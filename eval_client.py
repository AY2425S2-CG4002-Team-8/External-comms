import json
import asyncio
from tcp.tcp_client import TcpClient

class EvalClient:
    def __init__(self, secret_key, host, port, eval_client_read_buffer, eval_client_send_buffer):
        self.secret_key = secret_key
        self.tcp_client = TcpClient(secret_key, host, port, True)
        self.eval_client_read_buffer = eval_client_read_buffer
        self.eval_client_send_buffer = eval_client_send_buffer
    
    async def run(self):
        await self.tcp_client.run()
        await self.tcp_client.handshake()
        await asyncio.gather(
            self.send(),
            self.read()
        )

    async def send(self):
        while True:
            try:
                message = await self.eval_client_send_buffer.get()
                print(f"Sending message from eval_client: {message}")
                await self.tcp_client.send_message(message)
            except Exception as e:
                print(f"Exception in Eval CLient send: {e}")
                raise

    async def read(self):
        try:
            while True:
                success, message = await self.tcp_client.receive_message()
                if not success:
                    print(f"An error occurred while reading in eval_client")
                    continue
                await self.eval_client_read_buffer.put(message)
        except Exception as e:
            print(f"Exception in Eval Client read: {e}")
            raise
