import asyncio
import json
from mqtt.mqtt_client import MqttClient
from eval_client import EvalClient
from packet import PacketFactory, IMU, HEALTH, GUN
from relay_server import RelayServer
from ai_engine import AiEngine
from game_state import GameState
from fov_manager import FOVManager
from config import SECRET_KEY, HOST, MQTT_HOST, MQTT_PORT, SEND_TOPICS, READ_TOPICS
from logger import get_logger

logger = get_logger(__name__)

# class GameState:
#     def __init__(self):
#         self.p1 = {
#             'player_id': 1,
#             'action': None,
#             'state': {
#                 'hp': 100,
#                 'bullets': 6,
#                 'bombs': 2,
#                 'shield_hp': 0,
#                 'deaths': 0,
#                 'shields': 3
#             }
#         }
#         self.p2 = {
#             'player_id': 2,
#             'action': None,
#             'state': {
#                 'hp': 100,
#                 'bullets': 6,
#                 'bombs': 2,
#                 'shield_hp': 0,
#                 'deaths': 0,
#                 'shields': 3
#             }
#         }

class GameEngine:
    def __init__(self, port):
        self.secret_key = SECRET_KEY
        self.host = HOST
        self.port = port

        self.game_state = GameState()
        self.p1_fov_manager = FOVManager()
        # self.p2_fov_manager = FOVManager()

        self.eval_client_read_buffer = asyncio.Queue()
        self.eval_client_send_buffer = asyncio.Queue()
        self.visualiser_read_buffer = asyncio.Queue()
        self.visualiser_fov_read_buffer = asyncio.Queue()
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

    async def initiate_mqtt(self) -> None:
        try:
            mqtt_client = MqttClient(MQTT_HOST, MQTT_PORT, self.visualiser_read_buffer, self.visualiser_send_buffer, SEND_TOPICS, READ_TOPICS, 1, 60, 10)
            logger.debug("Starting MQTT")
            await mqtt_client.run()
        except:
            logger.error("Failed to run MQTT Task")

    async def initiate_eval_client(self) -> None:
        eval_client = EvalClient(self.secret_key, self.host, self.port, self.eval_client_read_buffer, self.eval_client_send_buffer)
        logger.debug("Starting Eval_Client")
        await eval_client.run()

    async def initiate_relay_server(self) -> None:
        relay_server_port = 8080
        relay_server = RelayServer(self.secret_key, self.host, relay_server_port, self.relay_server_read_buffer, self.relay_server_send_buffer)
        logger.debug("Starting Relay Server")
        await relay_server.run()

    async def initiate_ai_engine(self) -> None:
        ai_engine = AiEngine(self.ai_engine_read_buffer, self.ai_engine_write_buffer)
        logger.debug("Starting AI Engine")
        await ai_engine.run()

    async def handle_packet(self, packet) -> None:
        """Handles different packet types and places actions into the appropriate queues."""
        if packet.type == HEALTH:
            logger.debug(f"HEALTH PACKET Received: P {packet.p_health} S {packet.s_health}")
            logger.info(f"Echoing health packet back...")
            await self.relay_server_send_buffer.put(packet.to_bytes())
        elif packet.type == GUN:
            logger.debug(f"GUN PACKET Received: AMMO {packet.ammo}")
            logger.info(f"Echoing ammo packet back...")
            await self.relay_server_send_buffer.put(packet.to_bytes())
        elif packet.type == IMU:
            logger.debug(f"IMU PACKET Received: Gun_ax {packet.gun_ax} Gun_ay {packet.gun_ay} Gun_az {packet.gun_az} Gun_gx {packet.gun_gx} Gun_gy {packet.gun_gy} Gun_gz {packet.gun_gz} Glove_ax {packet.glove_ax} Glove_ay {packet.glove_ay} Glove_az {packet.glove_az} Glove_gx {packet.glove_gx} Glove_gy {packet.glove_gy} Glove_gz {packet.glove_gz}")
        else:
            logger.debug(f"Invalid packet type received: {packet.type}")

    async def relay_process(self) -> None:
        """
        Listens to relay server read buffer - Relay node data
        """
        while True:
            try:
                packet_byte_array = await self.relay_server_read_buffer.get()
                packet = PacketFactory.create_packet(packet_byte_array)
                logger.debug(f"Received packet from RELAY CLIENT {packet}")
                await self.handle_packet(packet)
            except Exception as e:
                logger.error(f"Error in read_relay_node: {e}")
    
    async def gun_process(self) -> None:
        """
        When gun packet is received, wait for health packet with timeout
        If health packet received before timeout, IR registered , and puts in central event buffer. Else, shot missed
        """
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
                
    async def prediction_process(self) -> None:
        """
        Puts predicted action from AI engine into a central event buffer for processing
        """
        while True:
            try:
                predicted_data = await self.ai_engine_write_buffer.get()
                await self.event_buffer.put(predicted_data)
            except Exception as e:
                logger.error(f"Error in prediction process: {e}")
    
    async def process(self) -> None:
        """
        Sends gun or action to visualiser.
        If gun, no need to await for FOV data. Else visualiser updates game engine that player was in view of action
        Updates game state accordingly and puts into eval_client_send_buffer to queue sending to eval_server
        """
        while True:
            try:
                action = await self.event_buffer.get()
                logger.info(f"action: {action}")
                mqtt_prefix = "gun_" if action == "gun" else "action_"
                fov = True
                
                mqtt_message = f"{mqtt_prefix}{action}"
                await self.visualiser_send_buffer.put(mqtt_message)
                if action != "gun":
                    fov = self.p1_fov_manager.get_fov()
                    # fov = self.p2_fov_manager.get_fov()
                # Considered passing in fov manager instance but this is a synchronous function
                self.game_state.perform_action(action, 1, fov)
                eval_data = self.generate_game_state(fov, action)
                await self.eval_client_send_buffer.put(json.dumps(eval_data))

            except Exception as e:
                logger.error(f"Exception in process: {e}")
                raise
    
    def generate_game_state(self, fov: bool, predicted_action: str) -> json:
        logger.debug(f"Generating game state with action: {predicted_action}")
        eval_data = {
            'player_id': 1, 
            'action': str(predicted_action), 
            'game_state': self.game_state.to_dict()
        }
        logger.info(f"Generated eval data: {eval_data}")

        return eval_data

    async def eval_process(self) -> None:
        """
        Listens to eval_client_read_buffer for eval_server updates
        Puts updated game state into relay_server and visualiser send_buffers to update
        """ 
        while True:
            game_state = await self.eval_client_read_buffer.get()
            logger.info(f"Received game state data from eval_server = {game_state}")

            logger.info(f"Sending game state to relay node")
            await self.relay_server_send_buffer.put(game_state)
            
            mqtt_message = "state_" + game_state
            logger.info("Sending game state to visualiser")
            await self.visualiser_send_buffer.put(mqtt_message)

    async def fov_process(self) -> None:
        while True:
            try:
                # Can consider 2 topics for p1, p2 to avoid congestion
                # For now single topic string parse
                fov_data = await self.visualiser_fov_read_buffer.get()
                fov_data = fov_data.split("_")
                if len(fov) != 2:
                    logger.error(f"Invalid FOV data received: {fov}")
                    raise
                player, fov = fov_data
                if player == "p1":
                    self.p1_fov_manager.handle_fov(fov)
                else:
                    self.p2_fov_manager.handle_fov(fov)
            except Exception as e:
                logger.error(f"Error in update_fov: {e}")

    async def stop(self) -> None:
        logger.info("Cancelling tasks...")
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def start(self) -> None:
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
    
    async def run(self) -> None:
        try:
            logger.info("Starting Game engine.")
            await self.start()
        except KeyboardInterrupt:
            logger.info("\nCTRL+C detected, stopping...")
            await self.stop()
            logger.info("Game engine stopped.")
        except Exception as e:
            logger.error(f"An error occurred while running game engine tasks: {e}")
