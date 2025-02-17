import asyncio
import json
from mqtt.mqtt_client import MqttClient
from eval_client import EvalClient
from packet import PacketFactory, IMU, HEALTH, GUN
from relay_server import RelayServer
from ai_engine import AiEngine
from config import SECRET_KEY, HOST, MQTT_HOST, MQTT_PORT, SEND_TOPICS, READ_TOPICS
from logger import get_logger

logger = get_logger(__name__)

class GameEngine:
    def __init__(self, port):
        self.secret_key = SECRET_KEY
        self.host = HOST
        self.port = port

        self.eval_client_read_buffer = asyncio.Queue()
        self.eval_client_send_buffer = asyncio.Queue()
        self.visualiser_read_buffer = asyncio.Queue()
        self.visualiser_send_buffer = asyncio.Queue()
        self.relay_server_read_buffer = asyncio.Queue()
        self.relay_server_send_buffer = asyncio.Queue()
        self.ai_engine_read_buffer = asyncio.Queue()
        self.ai_engine_write_buffer = asyncio.Queue()
        self.health_buffer = asyncio.Queue()
        self.gun_buffer = asyncio.Queue()
        self.imu_buffer = asyncio.Queue()
        self.event_buffer = asyncio.Queue()

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
            mqtt_client = MqttClient(MQTT_HOST, MQTT_PORT, self.visualiser_read_buffer, self.visualiser_send_buffer, SEND_TOPICS, READ_TOPICS, 1, 60, 10)
            logger.debug("Starting MQTT")
            await mqtt_client.run()
        except:
            logger.error("Failed to run MQTT Task")

    async def initiate_eval_client(self):
        eval_client = EvalClient(self.secret_key, self.host, self.port, self.eval_client_read_buffer, self.eval_client_send_buffer)
        logger.debug("Starting Eval_Client")
        await eval_client.run()

    async def initiate_relay_server(self):
        relay_server_port = 8080
        relay_server = RelayServer(self.secret_key, self.host, relay_server_port, self.relay_server_read_buffer, self.relay_server_send_buffer)
        logger.debug("Starting Relay Server")
        await relay_server.run()

    async def initiate_ai_engine(self):
        ai_engine = AiEngine(self.ai_engine_read_buffer, self.ai_engine_write_buffer)
        logger.debug("Starting AI Engine")
        await ai_engine.run()

    async def handle_packet(self, packet) -> None:
        """Handles different packet types and places actions into the appropriate queues."""
        if packet.type == HEALTH:
            logger.debug("HEALTH PACKET Received")
            await self.health_buffer.put(True)
        elif packet.type == GUN:
            logger.debug("GUN PACKET Received")
            await self.gun_buffer.put(True)
        elif packet.type == IMU:
            logger.debug("IMU PACKET Received")
            await self.ai_engine_read_buffer.put(packet)
        else:
            logger.debug(f"Invalid packet type received: {packet.type}")

    async def relay_process(self) -> None:
        while True:
            try:
                packet_byte_array = await self.relay_server_read_buffer.get()
                packet = PacketFactory.create_packet(packet_byte_array)
                logger.debug(f"Received packet from RELAY CLIENT {packet}")
                await self.handle_packet(packet)
            except Exception as e:
                logger.error(f"Error in read_relay_node: {e}")
    
    def handle_fov(self, fov):
        if not int(fov):
            return False
        return True
    
    async def gun_process(self):
        while True:
            try:
                await self.gun_buffer.get()
                logger.debug(f"Attempted to shoot")
                try:
                    await asyncio.wait_for(self.health_buffer.get(), timeout=0.3)
                    logger.debug("Hit - Received health packet")
                    await self.event_buffer.put("gun")
                    logger.debug("Added gun to action buffer")
                except asyncio.TimeoutError:
                    logger.debug(f"Missed - No Health Packet Received")
            except Exception as e:
                logger.error(f"Error in handle_gun: {e}")
                
    async def prediction_process(self):
        while True:
            try:
                predicted_data = await self.ai_engine_write_buffer.get()
                await self.event_buffer.put(predicted_data)
            except Exception as e:
                logger.error(f"Error in prediction process: {e}")
    
    async def process(self):
        while True:
            try:
                action = await self.event_buffer.get()
                logger.info(f"action: {action}")
                mqtt_prefix = "gun_" if action == "gun" else "action_"
                fov = True
                
                mqtt_message = f"{mqtt_prefix}{action}"
                await self.visualiser_send_buffer.put(mqtt_message)
                if action != "gun":
                    fov_message = await asyncio.wait_for(self.visualiser_read_buffer.get(), timeout=5)
                    fov = self.handle_fov(fov_message)
                    logger.info(f"Received FOV state from visualiser: {fov}")

                eval_data = self.generate_game_state(fov, action)
                await self.eval_client_send_buffer.put(json.dumps(eval_data))

            except Exception as e:
                logger.error(f"Exception in process: {e}")
                raise
    
    def generate_game_state(self, fov, predicted_action) -> json:
        logger.debug(f"Generating game state with action: {predicted_action}")
        if predicted_action == "gun":
            if self.p1['bullets'] > 0:
                self.p2['hp'] -= 5
                self.p1['bullets'] -= 1
        else:
            self.p2['hp'] = self.p2['hp'] - 10 if fov else self.p2['hp']
            self.p2['hp'] = self.p2['hp'] - 10 if fov else self.p2['hp']
            
        eval_data = {
            "player_id": 1, 
            "action": str(predicted_action), 
            "game_state": {
                "p1": self.p1,  # Keep as dictionary
                "p2": self.p2   # Keep as dictionary
            }
        }
        logger.info(f"Generated eval data: {eval_data}")

        return eval_data

    async def eval_process(self):
        while True:
            game_state = await self.eval_client_read_buffer.get()
            logger.info(f"Received game state data from eval_server = {game_state}")

            logger.info(f"Sending game state to relay node")
            await self.relay_server_send_buffer.put(game_state)
            
            mqtt_message = "state_" + game_state
            logger.info("Sending game state to visualiser")
            await self.visualiser_send_buffer.put(mqtt_message)

    async def stop(self):
        logger.info("Cancelling tasks...")
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def start(self):
        self.tasks = [
            asyncio.create_task(self.initiate_mqtt()),
            asyncio.create_task(self.initiate_eval_client()),
            asyncio.create_task(self.initiate_relay_server()),
            asyncio.create_task(self.initiate_ai_engine()),
            asyncio.create_task(self.relay_process()),
            asyncio.create_task(self.gun_process()),
            asyncio.create_task(self.prediction_process()),
            asyncio.create_task(self.eval_process()),
            asyncio.create_task(self.process())
        ]
        try:
            await asyncio.gather(*self.tasks)
        except Exception as e:
            logger.error(f"An error occurred while running game engine tasks: {e}")
    
    async def run(self):
        try:
            logger.info("Starting Game engine.")
            await self.start()
        except KeyboardInterrupt:
            logger.info("\nCTRL+C detected, stopping...")
            await self.stop()
            logger.info("Game engine stopped.")
        except Exception as e:
            logger.error(f"An error occurred while running game engine tasks: {e}")
