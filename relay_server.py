import asyncio
from tcp.tcp_server import TcpServer
from logger import get_logger

logger = get_logger(__name__)

class RelayServer:
    def __init__(self, secret_key, host, port, read_buffer, send_buffer):
        self.secret_key = secret_key
        self.host = host
        self.port = port
        
        # Queues for handling messages
        self.read_buffer = read_buffer
        self.send_buffer = send_buffer
        
        # TCP Server Instance
        self.tcp_server = TcpServer(
            secret_key=self.secret_key,
            host=self.host,
            port=self.port,
            read_buffer=self.read_buffer,
            send_buffer=self.send_buffer
        )

    async def start(self):
        """
        Starts the RelayServer by initializing and running the TCP server.
        """
        try:
            logger.info(f"Starting RelayServer on {self.host}:{self.port}")
            await self.tcp_server.start()
        except Exception as e:
            logger.error(f"Failed to start RelayServer on {self.host}:{self.port}: {e}")

    async def run(self):
        """
        Runs both the TCP server and message relaying in parallel.
        """
        await asyncio.gather(
            self.start(),
        )
