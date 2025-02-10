import asyncio
import aiomqtt

class MqttClient:
    def __init__(self, host: str, port: int, read_buffer, send_buffer, send_topic: str, subscribe_topics: list, base_reconnect_delay, max_reconnect_delay, max_reconnect_attempts):
        self.host = host
        self.port = port
        self.read_buffer = read_buffer
        self.send_buffer = send_buffer
        self.send_topic = send_topic
        self.subscribe_topics = subscribe_topics
        self.base_reconnect_delay = base_reconnect_delay
        self.max_reconnect_delay = max_reconnect_delay
        self.max_reconnect_attempts = max_reconnect_attempts
        self.isConnected = False
        self.client = None
    
    async def run(self):
        try:
            await self.connect()
            return
        except Exception as e:
            print(f"Error connecting to server with MQTT broker on (host, port): ({self.host}, {self.port}), Attemping reconnection...")
            await self.reconnect()

    async def connect(self):
        try:
            async with aiomqtt.Client(self.host, self.port) as client:
                self.client = client
                self.isConnected = True
                print(f"Connected to MQTT broker at {self.host}:{self.port}")
                await asyncio.gather(
                    asyncio.create_task(self.produce()),
                    asyncio.create_task(self.consume())
                )
        except (aiomqtt.MqttError, aiomqtt.MqttCodeError) as e:
            print(f"MQTT error: {e}")
            self.connected = False
            raise e
        except Exception as e:
            print(f"Error ocurred when running MQTT: {e}")
            raise
    
    async def publish(self, message):
        if self.client and self.isConnected:
            await self.client.publish(self.send_topic, message)
            print(f"Published message '{message}' to topic '{self.send_topic}'")
        else:
            print("Not connected to MQTT broker!")
    
    async def subscribe(self):
        for topic in self.subscribe_topics:
            await self.client.subscribe(topic)
            print(f"Successfully subscribed to topic {topic}")

    async def listen(self):
        async for message in self.client.messages:
            print(f"Received message: {message.payload.decode()} on topic '{message.topic}'")
    
    async def produce(self):
        while self.isConnected:
            try:
                message = await self.send_buffer.get()
                await self.publish(message)
            except (aiomqtt.MqttError, aiomqtt.MqttCodeError) as e:
                print(f"MQTT publish error: {e}. Disconnecting produce.")
                self.connected = False
                raise e
            except Exception as e:
                print(f"Unexpected error in produce: {e}")

    async def consume(self):
        if self.client and self.isConnected:
            await self.subscribe()
            await self.listen()
        else:
            print("Not connected to MQTT broker!")
            
    async def reconnect(self):
        current_reconnect_delay = self.base_reconnect_delay
        for attempt in range(self.max_reconnect_attempts):
            self.isConnected, self.client = False, None
            try:
                await self.connect()
                print(f"Successfully reconnected to server with (host, port): ({self.host}, {self.port})")
                return
            except Exception as e:
                print(f"TCP Client Connection failed: {e}. Retrying in {current_reconnect_delay} seconds...")
            current_reconnect_delay = min(2 ** attempt, self.max_reconnect_delay)
            await asyncio.sleep(current_reconnect_delay)

        print(f"Exceeded maximum number of retry attempts: {self.max_reconnect_attempts}")
        