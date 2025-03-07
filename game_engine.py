import asyncio
import json
from mqtt.mqtt_client import MqttClient
from eval_client import EvalClient
from packet import PacketFactory, IMU, HEALTH, GUN
from relay_server import RelayServer
from ai_engine import AiEngine
from game_state import GameState, VisualiserState
from config import SECRET_KEY, HOST, MQTT_HOST, MQTT_PORT, SEND_TOPICS, READ_TOPICS, MQTT_BASE_RECONNECT_DELAY, MQTT_MAX_RECONNECT_DELAY, MQTT_MAX_RECONNECT_ATTEMPTS, RELAY_SERVER_PORT, ACTION_TOPIC
from logger import get_logger

logger = get_logger(__name__)

class GameEngine:
    def __init__(self, port):
        self.secret_key = SECRET_KEY
        self.host = HOST
        self.port = port

        self.game_state = GameState()
        self.p1_visualiser_state = VisualiserState()
        self.p2_visualiser_state = VisualiserState()

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

    async def initiate_mqtt(self):
        try:
            mqtt_client = MqttClient(
                host=MQTT_HOST,
                port=MQTT_PORT,
                read_buffer=self.visualiser_read_buffer,
                send_buffer=self.visualiser_send_buffer,
                send_topics=SEND_TOPICS,
                read_topics=READ_TOPICS,
                base_reconnect_delay=MQTT_BASE_RECONNECT_DELAY,
                max_reconnect_delay=MQTT_MAX_RECONNECT_DELAY,
                max_reconnect_attempts=MQTT_MAX_RECONNECT_ATTEMPTS
            )
            logger.debug("Starting MQTT")
            await mqtt_client.run()
        except:
            logger.error("Failed to run MQTT Task")

    async def initiate_eval_client(self):
        eval_client = EvalClient(
            secret_key=SECRET_KEY,
            host=HOST,
            port=self.port,
            eval_client_read_buffer=self.eval_client_read_buffer,
            eval_client_send_buffer=self.eval_client_send_buffer
        )
        logger.debug("Starting Eval_Client")
        await eval_client.run()

    async def initiate_relay_server(self):
        relay_server = RelayServer(
            secret_key=SECRET_KEY,
            host="",
            port=RELAY_SERVER_PORT,
            read_buffer=self.relay_server_read_buffer,
            send_buffer=self.relay_server_send_buffer
        )
        logger.debug("Starting Relay Server")
        await relay_server.run()

    async def initiate_ai_engine(self):
        ai_engine = AiEngine(read_buffer=self.ai_engine_read_buffer, write_buffer=self.ai_engine_write_buffer)
        logger.debug("Starting AI Engine")
        await ai_engine.run()

    async def handle_packet(self, packet) -> None:
        """Handles different packet types and places actions into the appropriate queues."""
        if packet.type == HEALTH:
            logger.debug(f"HEALTH PACKET Received: P {packet.p_health} S {packet.s_health}")
            logger.info(f"Echoing health packet back...")
            await self.health_buffer.put(True)
            await self.relay_server_send_buffer.put(packet.to_bytes())
        elif packet.type == GUN:
            logger.debug(f"GUN PACKET Received: AMMO {packet.ammo}")
            logger.info(f"Echoing ammo packet back...")
            await self.relay_server_send_buffer.put(packet.to_bytes())
            await self.gun_buffer.put(True)
        elif packet.type == IMU:
            logger.debug(f"IMU PACKET Received: Gun_ax {packet.gun_ax} Gun_ay {packet.gun_ay} Gun_az {packet.gun_az} Gun_gx {packet.gun_gx} Gun_gy {packet.gun_gy} Gun_gz {packet.gun_gz} Glove_ax {packet.glove_ax} Glove_ay {packet.glove_ay} Glove_az {packet.glove_az} Glove_gx {packet.glove_gx} Glove_gy {packet.glove_gy} Glove_gz {packet.glove_gz}")
            await self.ai_engine_read_buffer.put(packet)
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
                hit = self.game_state.perform_action(action, 1, self.p1_visualiser_state)
                mqtt_message = self.generate_mqtt_message(1, action, hit)
                logger.info(f"Sending action to topic {ACTION_TOPIC} on visualiser: {mqtt_message}")
                await self.visualiser_send_buffer.put((ACTION_TOPIC, mqtt_message))
                eval_data = self.generate_game_state(action)
                logger.info(f"Sending eval data to eval_client: {eval_data}")
                await self.eval_client_send_buffer.put(eval_data)

            except Exception as e:
                logger.error(f"Exception in process: {e}")
                raise
    # public class ActionPayload
    #     {
    #         public int player;
    #         public string action;
    #         public bool hit;
    #         public GameState game_state;
    #     }
    def generate_mqtt_message(self, player: int, action: str, hit: bool) -> json:
        action_payload = {
            'player': player,
            'action': action,
            'hit': hit,
            'game_state': self.game_state.to_dict()
        }

        return json.dumps(action_payload)


    def generate_game_state(self, predicted_action: str) -> json:
        logger.debug(f"Generating game state with action: {predicted_action}")
        eval_data = {
            'player_id': 1, 
            'action': str(predicted_action), 
            'game_state': self.game_state.to_dict()
        }
        logger.info(f"Generated eval data: {eval_data}")

        return json.dumps(eval_data)

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
            
            null_action, null_hit = None, None
            mqtt_message = self.generate_mqtt_message(1, null_action, null_hit)
            logger.info("Sending game state to visualiser")
            await self.visualiser_send_buffer.put((ACTION_TOPIC, mqtt_message))

    async def visualiser_state_process(self) -> None:
        while True:
            try:
                # Can consider 2 topics for p1, p2 to avoid congestion
                # For now single topic string parse
                sight_payload = await self.visualiser_read_buffer.get()
                sight_payload = json.loads(sight_payload)
                player, fov, snow_number = sight_payload['player'], sight_payload['in_sight'], sight_payload['avalanche']
                if player == 1:
                    self.p1_visualiser_state.set_fov(fov)
                    self.p1_visualiser_state.set_snow_number(snow_number)
                elif player == 2:
                    self.p2_visualiser_state.set_fov(fov)
                    self.p2_visualiser_state.set_snow_number(snow_number)
                logger.info(f"Updated p1 visualiser state: {self.p1_visualiser_state.get_fov()}, {self.p1_visualiser_state.get_snow_number()}")
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
            asyncio.create_task(self.process()),
            asyncio.create_task(self.visualiser_state_process())
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
