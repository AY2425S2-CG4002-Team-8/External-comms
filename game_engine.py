import asyncio
import json
from mqtt.mqtt_client import MqttClient
from eval_client import EvalClient
from relay_server import RelayServer

class GameEngine:
    def __init__(self, secret_key, host, port):
        self.secret_key = secret_key

        self.host = host
        self.port = port

        self.eval_client_send_buffer = asyncio.Queue()
        self.visualiser_read_buffer = asyncio.Queue()
        self.visualiser_send_buffer = asyncio.Queue()
        self.relay_server_read_buffer = asyncio.Queue()
        self.relay_server_send_buffer = asyncio.Queue()

        self.tasks = []

        self.p1 = {
            'hp': 100,
            'bullets': 6,
            'bombs': 2,
            'shield_hp': 0,
            'deaths': 0,
            'shields': 3
        }
        self.p2 = {
            'hp': 100,
            'bullets': 6,
            'bombs': 2,
            'shield_hp': 0,
            'deaths': 0,
            'shields': 3
        }

    async def initiate_mqtt(self):
        try:
            host = "175.41.155.178"
            port = 1883
            publish_topic = "M2MQTT_Unity/test"
            await self.visualiser_send_buffer.put("Hello Visualiser.")
            await self.visualiser_send_buffer.put("Hello Visualiser 2.")
            subscribe_topics = ["test/topic", publish_topic]
            mqtt_client = MqttClient(host, port, self.visualiser_send_buffer, publish_topic, subscribe_topics)
            print("Starting MQTT")
            await mqtt_client.run()
        except:
            print("Failed to run MQTT Task")

    async def initiate_eval_client(self):
        eval_client = EvalClient(self.secret_key, self.host, self.port, self.eval_client_send_buffer)
        await eval_client.run()

    async def initiate_relay_server(self):
        relay_server_port = 8080
        relay_server = RelayServer(self.secret_key, self.host, relay_server_port, self.relay_server_read_buffer, self.relay_server_send_buffer)
        await relay_server.run()

    async def game_process(self):
        """
        Consumes messages from relay_server_read_buffer and forwards them to eval_client_send_buffer.
        """
        while True:
            message = await self.relay_server_read_buffer.get()
            # Run loads as a temporary measure to simulate a new json created by GE
            message = json.loads(message)
            print(f"Processing message: {message}")
            await self.eval_client_send_buffer.put(message)
            print(f"Queued message to eval_server: {message}")

    async def stop(self):
        print("Cancelling tasks...")
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def start(self):
        self.tasks = [
            self.initiate_mqtt(),
            self.initiate_eval_client(),
            self.initiate_relay_server(),
            self.game_process()
        ]
        try:
            await asyncio.gather(*self.tasks)
        except KeyboardInterrupt:
            print("\nCTRL+C detected, stopping...")
            await self.stop()
            print("Game engine stopped.")
        except Exception as e:
            print(f"An error occurred while running game engine tasks: {e}")
    
    