import asyncio
import base64

from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from logger import get_logger

logger = get_logger(__name__)

class TcpClient:
    def __init__(self, secret_key, host, port, require_encryption, base_reconnect_delay=1, max_reconnect_delay=60, max_reconnect_attempts=10):
        self.secret_key = secret_key
        self.host = host
        self.port = port
        self.require_encryption = require_encryption
        self.base_reconnect_delay = base_reconnect_delay
        self.max_reconnect_delay = max_reconnect_delay
        self.max_reconnect_attempts = max_reconnect_attempts
        self.reader = None
        self.writer = None
    
    async def connect(self) -> None:
        """ Opens the connection to desired TCP server """
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
        await self.handshake()

    async def run(self) -> None:
        try:
            await self.connect()
            logger.info(f"Successfully connected to server with (host, port): ({self.host}, {self.port})")
        except Exception as e:
            logger.error(f"Error connecting to server with (host, port): ({self.host}, {self.port}), Attemping reconnection...")
            await self.reconnect()

    def encrypt(self, message) -> bytes:
        """ 
        Encrypts a given message with secret key
        Returns base64 encoded message
        """
        iv = get_random_bytes(AES.block_size)
        cipher = AES.new(self.secret_key.encode('utf-8'), AES.MODE_CBC, iv)
        pad_length = AES.block_size - len(message) % AES.block_size
        message += bytes([pad_length] * pad_length)
        encrypted = cipher.encrypt(message)
        encoded = base64.b64encode(iv + encrypted)

        return encoded
    
    async def handshake(self) -> None:
        """ Sends hello to TCP server to handshake with client """
        try:
            message = "hello"
            await self.send_message(message)
            logger.info(f"Succesfully handshook with server with (host, port): ({self.host}, {self.port}), with message: {message}")
            return
        except Exception as e:
            logger.error(f"Failed to handshake to server with exception: {e}")

    async def receive_message(self) -> tuple[bool, bytes]:
        """
        Asychronously receives s from TCP server
        Returns a success boolean and message bytes received from the TCP server
        """
        success, message = False, None

        # Check if there exists a connection before reading
        if self.reader is None:
            logger.warning("Error: No active connection")
            return success, message
    
        try:
            while True:
                data = b''
                while not data.endswith(b'_'):
                    literal = await self.reader.read(1)
                    if not literal:
                        logger.warning("Client has disconnected from server")
                        await self.reconnect()
                    data += literal
                    
                if len(data) == 0:
                    logger.warning(f"Packet empty - Disconnected from server")
                    return success, message
                
                data = data.decode("utf-8")
                length = int(data[:-1])
                success = True
                # readexactly waits for exactly `length` bytes, else throws an IncompleteReadError
                message = await self.reader.readexactly(length)

                return success, message
            
        except asyncio.TimeoutError:
            logger.error("Timeout while waiting for message.")
            return success, message
        except asyncio.IncompleteReadError:
            logger.error("Incomplete read error. Connection may have been lost.")
            return success, message
        except ValueError:
            logger.error("Invalid message format received.")
            return success, message
        except Exception as e:
            logger.error(f"Error receiving message: {e}")
            return success, message

    async def send_message(self, message) -> None:
        """
        Asychronously sends messages to the TCP server
        Returns None - Sends messages out in bytes
        """
        if self.writer is None:
            logger.warning("No connection has been made to the server to send message")
            return
        try:
            if isinstance(message, str):
                message = message.encode('utf-8')
            elif isinstance(message, bytearray):
                message = bytes(message)
            encrypted_message = self.encrypt(message) if self.require_encryption else message
            self.writer.write(f"{len(encrypted_message)}_".encode() + encrypted_message)
            await self.writer.drain()
            logger.info(f"Succesfully sent message to server with (host, port): ({self.host}, {self.port})")
        except Exception as e:
            logger.error(f"Failed to send encrypted message to server with exception: {e}")

    
    async def reconnect(self) -> None:
        """ Attempt to reconnect to TCP server with exponential backoff """
        current_reconnect_delay = self.base_reconnect_delay
        
        logger.info(f"Attempting reconnection. Gracefully closing connection before attempting exponential backoff")
        await self.close_connection()

        # Attempt connection every after a reconnection delay that exponentially increases to a maximum of 60 seconds
        for attempt in range(self.max_reconnect_attempts):
            try:
                logger.info(f"Attempting to reconnect ({attempt + 1}/{self.max_reconnect_attempts})...")
                await self.connect()
                logger.info("Reconnected successfully.")
                return
            except Exception as e:
                logger.error(f"TCP Client Connection failed: {e}. Retrying in {current_reconnect_delay} seconds...")
                current_reconnect_delay = min(2 ** attempt, self.max_reconnect_delay)
                await asyncio.sleep(current_reconnect_delay)

        logger.warning(f"Exceeded maximum retry attempts ({self.max_reconnect_attempts}).")

    async def close_connection(self) -> None:
        """ Gracefully close the connection to TCP server """
        if self.writer:
            logger.debug(f"Closing connection to ({self.host}, {self.port})...")
            self.writer.close()
            await self.writer.wait_closed()
            self.reader, self.writer = None, None
            logger.info(f"Connection to ({self.host}, {self.port}) closed successfully.")
        else:
            logger.warning("No active connection to close.")
