import asyncio
import aiomqtt
from logger import get_logger

logger = get_logger(__name__)

class MqttClient:
    def __init__(self, host: str, port: int, read_buffer, send_buffer, g_buffer, send_topics: list[tuple[str, int]], read_topics: list[tuple[str, int]], base_reconnect_delay, max_reconnect_delay, max_reconnect_attempts):
        self.host = host
        self.port = port
        self.read_buffer = read_buffer
        self.send_buffer = send_buffer
        self.g_buffer = g_buffer
        self.send_topics = send_topics
        self.read_topics = read_topics
        self.base_reconnect_delay = base_reconnect_delay
        self.max_reconnect_delay = max_reconnect_delay
        self.max_reconnect_attempts = max_reconnect_attempts
        self.isConnected = False
        self.client = None
    
    async def run(self) -> None:
        try:
            await self.connect()
            return
        except Exception as e:
            logger.error(f"Error connecting to server with MQTT broker on (host, port): ({self.host}, {self.port}), Attemping reconnection...")
            await self.reconnect()

    async def connect(self) -> None:
        """
        Connects to MQTT broker at desired host and port
        Once connected set client and isConnected, and run produce and consume tasks
        """
        try:
            async with aiomqtt.Client(self.host, self.port) as client:
                self.client = client
                self.isConnected = True
                logger.debug(f"Connected to MQTT broker at {self.host}:{self.port}")
                await asyncio.gather(
                    asyncio.create_task(self.produce()),
                    asyncio.create_task(self.consume())
                )
        except (aiomqtt.MqttError, aiomqtt.MqttCodeError) as e:
            logger.error(f"MQTT error: {e}")
            self.connected = False
            raise e
        except Exception as e:
            logger.error(f"Error ocurred when running MQTT: {e}")
            raise

    async def publish(self, topic, message) -> None:
        """ Publishes message to all topics that it should be published to """
        if self.client and self.isConnected:
            await self.client.publish(topic, message)
            logger.debug(f"Published message '{message}' to topic '{topic}'")
        else:
            logger.warning("Not connected to MQTT broker to publish")
    
    async def broadcast(self, message) -> None:
        """ Publishes message to all topics that it should be published to """
        if self.client and self.isConnected:
            for topic, qos in self.send_topics:
                await self.client.publish(topic, message, qos=qos)
                logger.debug(f"Published message '{message}' to topic '{topic}'")
        else:
            logger.warning("Not connected to MQTT broker to publish")
    
    async def subscribe(self) -> None:
        """ Subscribe to all topics in self.read_topics - the topics this client needs to listen to """
        for topic, qos in self.read_topics:
            await self.client.subscribe(topic, qos=qos)
            logger.debug(f"Successfully subscribed to topic {topic} with qos {qos}")

    async def listen(self) -> None:
        """ Listens to messages published by subscribed entities on client's cental message buffer and put into read_buffer """
        async for message in self.client.messages:
            logger.debug(f"Received message: {message.payload.decode()} on topic '{message.topic}'")
            logger.critical(f"Received message: {message.payload.decode()} on topic '{message.topic}'")
            if message.topic == 'G':
                logger.critical("G_BUFFER")
                await self.g_buffer.put(message.payload.decode())
            else:
                # Put the message into the read buffer for processing
                await self.read_buffer.put(message.payload.decode())
    
    async def produce(self) -> None:
        """ Coroutine that asynchronously publishes all messages from send_buffer to all relevant topics """
        while self.isConnected:
            try:
                topic, message = await self.send_buffer.get()
                await self.publish(topic, message)
            except (aiomqtt.MqttError, aiomqtt.MqttCodeError) as e:
                logger.error(f"MQTT publish error: {e}. Disconnecting produce.")
                self.connected = False
                raise e
            except Exception as e:
                logger.error(f"Unexpected error in produce: {e}")

    async def consume(self) -> None:
        """ Coroutine that initialises subscription and runs listen asynchronously """
        if self.client and self.isConnected:
            await self.subscribe()
            await self.listen()
        else:
            logger.error("Not connected to MQTT broker to listen")
            
    async def reconnect(self) -> None:
        """ Attempt to reconnect to MQTT broker with exponential backoff """
        current_reconnect_delay = self.base_reconnect_delay

        # Disconnect any client connection to refresh connection
        if self.client:
            try:
                await self.client.disconnect()
            except Exception as e:
                logger.error(f"Error closing existing MQTT connection: {e}")

        # Attempt connection every after a reconnection delay that exponentially increases to a maximum of 60 seconds
        for attempt in range(self.max_reconnect_attempts):
            self.isConnected, self.client = False, None
            try:
                await self.connect()
                logger.debug(f"Successfully reconnected to server with (host, port): ({self.host}, {self.port})")
                return
            except Exception as e:
                logger.error(f"MQTT Client Connection failed: {e}. Retrying in {current_reconnect_delay} seconds...")
            current_reconnect_delay = min(2 ** attempt, self.max_reconnect_delay)
            await asyncio.sleep(current_reconnect_delay)

        logger.error(f"Exceeded maximum number of retry attempts: {self.max_reconnect_attempts}")
        