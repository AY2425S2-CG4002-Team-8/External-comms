import asyncio
import aiomqtt

class MqttClient:
    def __init__(self, host: str, port: int, publish_buffer, publish_topic: str, subscribe_topics: list):
        self.host = host
        self.port = port
        self.publish_buffer = publish_buffer
        self.publish_topic = publish_topic
        self.subscribe_topics = subscribe_topics
        self.isConnected = False
        self.client = None
    
    async def run(self):
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
    
    async def publish(self, message):
        if self.client and self.isConnected:
            await self.client.publish(self.publish_topic, message)
            print(f"Published message '{message}' to topic '{self.publish_topic}'")
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
                message = await self.publish_buffer.get()
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
            

        