import asyncio

from logger import get_logger

logger = get_logger(__name__)

class TcpServer:
    def __init__(self, secret_key, host, port, read_buffer, send_buffer, timeout=60):
        self.secret_key = secret_key
        self.host = host
        self.port = port
        self.read_buffer = read_buffer
        self.send_buffer = send_buffer
        self.timeout = timeout
        self.clients = set()

    async def start(self):
        try:
            tcp_server = await asyncio.start_server(self.on_client_connect, self.host, self.port)
            async with tcp_server:
                await tcp_server.serve_forever()

        except Exception as e:
            logger.error(f"TCP Server on (host, port): ({self.host}, {self.port}) failed to start.")
        
    async def on_client_connect(self, reader, writer):
        success, message = await self.receive_message(reader)
        host_name = writer.get_extra_info('peername')
        if not success:
            logger.warning(f"Client from {host_name} was not able to connect. Closing connection...")
            await self.close_connection(writer)
            return

        try:
            message = message.decode()
            if message != "hello":
                logger.warning(f"Incorrect handshake packet from {host_name}. Got {message} instead")
                await self.close_connection(writer)
                return
            self.add_client(writer)
            logger.info(f"Successfully received handshake packet from {host_name}")

            await asyncio.gather(
                asyncio.create_task(self.read_task(reader, writer)),
                asyncio.create_task(self.write_task(writer))
            )

        except Exception as e:
            logger.error(f"Exception on TCP server: {e}")
    
    def add_client(self, writer):
        """
        Adds writer as a unique identifier for open client sockets
        """
        self.clients.add(writer)
        return
        
    
    def remove_client(self, writer):
        """
        Removes writer as a unique identifier for open client sockets
        """
        self.clients.discard(writer)
        return

    async def receive_message(self, reader) -> tuple[bool, str]:
        """
        Returns success and message received from tcp client or server
        """
        success, message = False, None
        try:
            while True:
                data = b''
                while not data.endswith(b'_'):
                    literal = await reader.read(1)
                    if not literal:
                        logger.warning(f"Client disconnected unexpectedly")
                        return success, message
                    data += literal
                    
                if len(data) == 0:
                    logger.warning(f"Packet is empty - Client disconnected from server")
                    return success, message
                
                data = data.decode("utf-8")
                length = int(data[:-1])
                success = True
                message = await reader.readexactly(length)

                return success, message
            
        except asyncio.TimeoutError:
            logger.error("Timeout while waiting for message.")
            return success, message
        except asyncio.IncompleteReadError:
            logger.error("Incomplete read error. Connection may have been lost.")
            return success, message
        except ValueError as v:
            logger.error(f"Invalid message format received: {v}")
            return success, message
        except Exception as e:
            logger.error(f"Error receiving message: {e}")
            return success, message
    
    async def send_message(self, writer, message):
        try:
            if isinstance(message, str):
                message = message.encode('utf-8')
            elif isinstance(message, bytearray):
                message = bytes(message)
            writer.write(f"{len(message)}_".encode() + message)
            await writer.drain()
            logger.info(f"Sent message to client {writer.get_extra_info('peername')}")
        
        except Exception as e:
            logger.error(f"Exception when sending packet to client: {writer.get_extra_info('peername')}, Exception: {e}")

    async def read_task(self, reader, writer):
        try:
            while True:
                success, message = await self.receive_message(reader)
                if not success:
                    logger.warning(f"Error in reading packet from client: {writer.get_extra_info('peername')}")
                    break
                # Binary message from relay node
                await self.read_buffer.put(message)
        except Exception as e:
            logger.error(f"Exception in reading message from client: {writer.get_extra_info('peername')}")
        finally:
            await self.close_connection(writer)


    async def write_task(self, writer):
        while True:
            try:
                message = await self.send_buffer.get()
                await self.send_message(writer, message)
            except Exception as e:
                logger.error(f"Not able to start write task in TCP server")

    async def close_connection(self, writer):
        host_name = writer.get_extra_info('peername')
        try:
            if not writer.is_closing():
                writer.close()
                await writer.wait_closed()
            self.remove_client(writer)
            logger.info(f"Successfully disconnected client: {host_name}")
        
        except Exception as e:
            logger.error(f"Failed to close client connection from: {host_name}")