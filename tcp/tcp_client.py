import asyncio
import base64

from base64 import b64encode
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad, unpad

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
    
    async def initiate_connection(self):
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)

    async def connect_to_server(self):
        try:
            await self.initiate_connection()
            print(f"Successfully connected to server with (host, port): ({self.host}, {self.port})")
        except Exception as e:
            print(f"Error connecting to server with (host, port): ({self.host}, {self.port})")
            await self.reconnect()

    def encrypt(self, message) -> bytes:
        message = message.encode('utf-8')
        iv = get_random_bytes(AES.block_size)
        cipher = AES.new(self.secret_key.encode('utf-8'), AES.MODE_CBC, iv)
        pad_length = AES.block_size - len(message) % AES.block_size
        message += bytes([pad_length] * pad_length)
        encrypted = cipher.encrypt(message)
        encoded = base64.b64encode(iv + encrypted)

        return encoded
    
    async def handshake(self):
        try:
            message = "hello"
            await self.send_message(message)
            print(f"Succesfully handshook with server with (host, port): ({self.host}, {self.port}), with message: {message}")
            return
        except Exception as e:
            print(f"Failed to handshake to server with exception: {e}")

    async def receive_message(self):
        """
        Receive the message from tcp server
        """
        success, message = False, None
        try:
            while True:
                data = b''
                while not data.endswith(b'_'):
                    literal = await self.reader.read(1)
                    if not literal:
                        print(f"Client disconnected unexpectedly")
                        return success, message
                    data += literal
                    
                if len(data) == 0:
                    print(f"Packet is empty")
                    return success, message
                
                data = data.decode("utf-8")
                length = int(data[:-1])
                success = True
                message = await self.reader.readexactly(length)
                return success, message
            
        except asyncio.TimeoutError:
            print("Timeout while waiting for message.")
            return success, message
        except asyncio.IncompleteReadError:
            print("Incomplete read error. Connection may have been lost.")
            return success, message
        except ValueError:
            print("Invalid message format received.")
            return success, message
        except Exception as e:
            print(f"Error receiving message: {e}")
            return success, message

    async def send_message(self, message):
        if self.writer is None:
            print("No connection has been made to the server to send message")
            return
        try:
            encrypted_message = self.encrypt(message) if self.require_encryption else message
            if isinstance(encrypted_message, str):
                encrypted_message = encrypted_message.encode('utf-8')

            self.writer.write(f"{len(encrypted_message)}_".encode() + encrypted_message)
            await self.writer.drain()  # Ensure the message is sent
            print(f"Succesfully sent message to server with (host, port): ({self.host}, {self.port}), with message: {message}")
        except Exception as e:
            print(f"Failed to send encrypted message to server with exception: {e}")

    
    async def reconnect(self):
        current_reconnect_delay = self.base_reconnect_delay
        for attempt in range(self.max_reconnect_attempts):
            await asyncio.sleep(current_reconnect_delay)
            try:
                await self.initiate_connection()
                print(f"Successfully reconnected to server with (host, port): ({self.host}, {self.port})")
                return
            except Exception as e:
                print(f"Reconnect attempt {attempt + 1} failed with error: {e}")
            current_reconnect_delay = max(2 * current_reconnect_delay, self.max_reconnect_delay)
