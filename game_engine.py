import asyncio
from mqtt.mqtt_client import MqttClient
from eval_client import EvalClient

class GameEngine:
    def __init__(self, secret_key, host, port):
        self.secret_key = secret_key
        self.host = host
        self.port = port
        self.eval_client_send_buffer = asyncio.Queue()
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
            publish_buffer = asyncio.Queue()
            await publish_buffer.put("Hello Visualiser.")
            await publish_buffer.put("Hello Visualiser 2.")
            subscribe_topics = ["test/topic", publish_topic]
            mqtt_client = MqttClient(host, port, publish_buffer, publish_topic, subscribe_topics)
            print("Starting MQTT")
            await mqtt_client.run()
        except:
            print("Failed to run MQTT Task")

    async def initiate_eval_client(self):
        eval_client = EvalClient(self.secret_key, self.host, self.port, self.eval_client_send_buffer)
        await eval_client.run()

    async def temporary_eval_client_buffer_putter(self):
        test_data = {
            "player_id": 1, 
            "action": "gun", 
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
        while True:
            try:
                x = await asyncio.to_thread(input)
                await self.eval_client_send_buffer.put(test_data)
                print("Data added to EvalClient buffer.")
            except Exception as e:
                print(f"temporary_eval_client_buffer_putter task has raised exception {e}.")
                raise

    async def stop(self):
        print("Cancelling tasks...")
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def start(self):
        self.tasks = [
            self.initiate_mqtt(),
            self.initiate_eval_client(),
            self.temporary_eval_client_buffer_putter()
        ]
        try:
            await asyncio.gather(*self.tasks)
        except KeyboardInterrupt:
            print("\nCTRL+C detected, stopping...")
            await self.stop()
            print("Game engine stopped.")
        except Exception as e:
            print(f"An error occurred while running game engine tasks: {e}")
    
    