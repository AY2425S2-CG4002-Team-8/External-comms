import asyncio

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
            print(f"TCP Server on (host, port): ({self.host}, {self.port}) failed to start.")
        

    async def on_client_connect(self, reader, writer):
        success, message = await self.receive_message(reader)
        if not success:
            print(f"Client from {writer.get_extra_info('peername')} was not able to connect.")
            await self.close_connection(writer)
            return

        host_name = writer.get_extra_info('peername')
        try:
            if message != "hello":
                print(f"Incorrect handshake packet from {host_name}. Got {message} instead")
                await self.close_connection(writer)
                return
            self.add_client(writer)
            print(f"Successfully received handshake packet from {host_name}")

            await asyncio.gather(
                asyncio.create_task(self.read_task(reader, writer)),
                asyncio.create_task(self.write_task(writer))
            )

        except Exception as e:
            print(f"Exception on TCP server: {e}")
    
    def add_client(self, writer):
        """
        Adds writer as a unique identifier for open client sockets
        """
        self.clients.add(writer)
        return
        
    
    def remove_client(self, writer):
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
                        print(f"Client disconnected unexpectedly")
                        return success, message
                    data += literal
                    
                if len(data) == 0:
                    print(f"Packet is empty")
                    return success, message
                
                data = data.decode("utf-8")
                length = int(data[:-1])
                success = True
                message = await reader.readexactly(length)
                message = message.decode('utf-8')
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
    
    async def send_message(self, writer, message):
        try:
            writer.write(f"{len(message)}_".encode() + message.encode())
            await writer.drain()
            print(f"Sent message to client {writer.get_extra_info('peername')}")
        
        except Exception as e:
            print(f"Exception when sending packet to client: {writer.get_extra_info('peername')}, Exception: {e}")

    async def read_task(self, reader, writer):
        try:
            while True:
                success, message = await self.receive_message(reader)
                if not success:
                    print(f"Error in reading packet from client: {writer.get_extra_info('peername')}")
                    break
                await self.read_buffer.put(message)
        except Exception as e:
            print(f"Exception in reading message from client: {writer.get_extra_info('peername')}")
        finally:
            self.close_connection(writer)


    async def write_task(self, writer):
        while True:
            try:
                message = await self.send_buffer.get()
                await self.send_message(writer, message)
            except Exception as e:
                print(f"Not able to start write task in TCP server")

    async def close_connection(self, writer):
        host_name = writer.get_extra_info('peername')
        try:
            if not writer.is_closing():
                writer.close()
                await writer.wait_closed()
            self.remove_client(writer)
            print(f"Successfully disocnnected client: {host_name}")
        
        except Exception as e:
            print(f"Failed to close client connection from: {host_name}")