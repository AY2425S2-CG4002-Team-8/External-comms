import asyncio
import json
from mqtt.mqtt_client import MqttClient
from eval_client import EvalClient
from relay_server import RelayServer
from ai_engine import AiEngine

class GameEngine:
    def __init__(self, secret_key, host, port):
        self.secret_key = secret_key

        self.host = host
        self.port = port

        self.eval_client_read_buffer = asyncio.Queue()
        self.eval_client_send_buffer = asyncio.Queue()
        self.visualiser_read_buffer = asyncio.Queue()
        self.visualiser_send_buffer = asyncio.Queue()
        self.relay_server_read_buffer = asyncio.Queue()
        self.relay_server_send_buffer = asyncio.Queue()
        self.ai_engine_read_buffer = asyncio.Queue()
        self.ai_engine_write_buffer = asyncio.Queue()

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
            mqtt_client = MqttClient(host, port, self.visualiser_read_buffer, self.visualiser_send_buffer, publish_topic, subscribe_topics, 1, 64, 10)
            print("Starting MQTT")
            await mqtt_client.run()
        except:
            print("Failed to run MQTT Task")

    async def initiate_eval_client(self):
        eval_client = EvalClient(self.secret_key, self.host, self.port, self.eval_client_read_buffer, self.eval_client_send_buffer)
        await eval_client.run()

    async def initiate_relay_server(self):
        relay_server_port = 8080
        relay_server = RelayServer(self.secret_key, self.host, relay_server_port, self.relay_server_read_buffer, self.relay_server_send_buffer)
        await relay_server.run()

    async def initiate_ai_engine(self):
        ai_engine = AiEngine(self.ai_engine_read_buffer, self.ai_engine_write_buffer)
        await ai_engine.run()

    def temp_generate_game_state(self, predicted_action) -> json:
        test_data = {
            "player_id": 1, 
            "action": str(predicted_action), 
            "game_state": {
                "p1": {
                    "hp": 100, 
                    "bullets": 5, 
                    "bombs": 2, 
                    "shield_hp": 0, 
                    "deaths": 0, 
                    "shields": 3
                },
                "p2": {
                    "hp": 95, 
                    "bullets": 6, 
                    "bombs": 2, 
                    "shield_hp": 0, 
                    "deaths": 0, 
                    "shields": 3
                },
            }
        }

        return test_data

    async def process(self):
        while True:
            # message: gun or action
            # if gun: directly put into prediction output buffer
            # if any other action: pass through auxiliary function to "predict",put into prediction output buffer
            # subsequently run another method to push into eval_client buffer + await server response
            message = await self.relay_server_read_buffer.get()
            message = json.loads(message)
            print(f"Received mmessage from RELAY CLIENT {message}")
            await self.ai_engine_read_buffer.put(message)
            predicted_data = await self.ai_engine_write_buffer.get()
            print(f"Predicted data {predicted_data}")
            test_data = self.temp_generate_game_state(predicted_data)
            test_data_str = json.dumps(test_data)
            await self.eval_client_send_buffer.put(test_data_str)
            game_state = await self.eval_client_read_buffer.get()
            print(f"Game state after loads = {game_state}")
            await self.visualiser_send_buffer.put(game_state)
            await self.relay_server_send_buffer.put(game_state)

    # async def game_process(self):
    #     """
    #     Consumes messages from relay_server_read_buffer and forwards them to eval_client_send_buffer.
    #     """
    #     while True:
    #         message = await self.relay_server_read_buffer.get()
    #         # Run loads as a temporary measure to simulate a new json created by GE
    #         message = json.loads(message)
    #         print(f"Processing message: {message}")
    #         await self.eval_client_send_buffer.put(message)
    #         print(f"Queued message to eval_server: {message}")

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
            self.initiate_ai_engine(),
            self.process()
        ]
        try:
            await asyncio.gather(*self.tasks)
        except Exception as e:
            print(f"An error occurred while running game engine tasks: {e}")
    
    async def run(self):
        try:
            print("Starting Game engine.")
            await self.start()
        except KeyboardInterrupt:
            print("\nCTRL+C detected, stopping...")
            await self.stop()
            print("Game engine stopped.")
        except Exception as e:
            print(f"An error occurred while running game engine tasks: {e}")
