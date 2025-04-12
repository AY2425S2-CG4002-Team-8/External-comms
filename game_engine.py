import asyncio
from collections import deque
import json
from mqtt.mqtt_client import MqttClient
from eval_client import EvalClient
from packet import GunPacket, HealthPacket, PacketFactory, IMU, HEALTH, GUN, CONN
from relay_server import RelayServer
from ai_engine import AiEngine
from game_state import GameState, VisualiserState
from config import ACTION_DELAY, AI_READ_BUFFER_MAX_SIZE, CONNECTION_TOPIC, GE_SIGHT_TOPIC, GOOGLE_DRIVE_FOLDER_ID, GUN_TIMEOUT, SECRET_KEY, HOST, MQTT_HOST, MQTT_PORT, SEND_TOPICS, READ_TOPICS, MQTT_BASE_RECONNECT_DELAY, MQTT_MAX_RECONNECT_DELAY, MQTT_MAX_RECONNECT_ATTEMPTS, RELAY_SERVER_PORT, ACTION_TOPIC, ALL_INTERFACE, SERVICE_ACCOUNT_FILE
from logger import get_logger
import random
import os
import pandas as pd
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account
from datetime import datetime, timedelta

logger = get_logger(__name__)

class GameEngine:
    def __init__(self, port):
        self.secret_key = SECRET_KEY
        self.host = HOST
        self.port = port

        self.game_state = GameState()
        self.p1_visualiser_state = VisualiserState()
        self.p2_visualiser_state = VisualiserState()

        self.visualiser_read_buffer = asyncio.Queue()
        self.visualiser_send_buffer = asyncio.Queue()
        self.relay_server_read_buffer = asyncio.Queue()
        self.relay_server_send_buffer = asyncio.Queue()
        self.p1_ai_engine_read_buffer = asyncio.Queue(AI_READ_BUFFER_MAX_SIZE)
        self.p2_ai_engine_read_buffer = asyncio.Queue(AI_READ_BUFFER_MAX_SIZE)
        self.ai_engine_write_buffer = asyncio.Queue()
        self.event_buffer = asyncio.Queue()
        self.connection_buffer = asyncio.Queue()

        self.p1_gun_buffer = asyncio.Queue()
        self.p2_gun_buffer = asyncio.Queue()
        self.p1_health_buffer = asyncio.Queue()
        self.p2_health_buffer = asyncio.Queue()

        self.p1_logger = logger.ge_p1
        self.p2_logger = logger.ge_p2

        self.actions = ["badminton", "fencing", "boxing", "golf", "shield", "reload", "bomb"]
        # self.roulette_dictionary = {}

        self.last_send_dictionary = {
            1: datetime.now(),
            2: datetime.now()
        }
        

        self.tasks = []

    # def init_roulette(self):
    #     for player in [1, 2]:
    #         self.roulette_dictionary[player] = {
    #             action: 2 for action in self.actions
    #         }

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
            logger.critical("Starting MQTT")
            await mqtt_client.run()
        except:
            logger.error("Failed to run MQTT Task")

    async def initiate_relay_server(self):
        relay_server = RelayServer(
            secret_key=SECRET_KEY,
            host=ALL_INTERFACE,
            port=RELAY_SERVER_PORT,
            read_buffer=self.relay_server_read_buffer,
            send_buffer=self.relay_server_send_buffer
        )
        logger.critical("Starting Relay Server")
        await relay_server.run()

    async def initiate_ai_engine(self):
        ai_engine = AiEngine(
            p1_read_buffer=self.p1_ai_engine_read_buffer, 
            p2_read_buffer=self.p2_ai_engine_read_buffer,
            write_buffer=self.ai_engine_write_buffer,
            visualiser_send_buffer=self.visualiser_send_buffer,
        )
        logger.critical("Starting AI Engine")
        await ai_engine.run()

    async def handle_packet(self, packet) -> None:
        """Handles different packet types and places actions into the appropriate queues."""
        try:
            player = packet.player
            if packet.type == HEALTH:
                logger.info(f"HEALTH PACKET Received")
                if player == 2:
                    await self.p1_health_buffer.put(player)
                else:
                    await self.p2_health_buffer.put(player)
            elif packet.type == GUN:
                logger.info(f"GUN PACKET Received")
                if player == 1:
                    await self.p1_gun_buffer.put(player)
                else:
                    await self.p2_gun_buffer.put(player)
            elif packet.type == IMU:
                logger.info(f"IMU PACKET Received")
                try:
                    if player == 1:
                        self.p1_ai_engine_read_buffer.put_nowait(packet)
                    else:
                        self.p2_ai_engine_read_buffer.put_nowait(packet)
                except asyncio.QueueFull:
                    logger.warning(f"AI buffer full, dropping IMU packet for player {player}")
            elif packet.type == CONN:
                logger.info(f"CONNECTION PACKET Received")
                await self.connection_buffer.put(packet)
            else:
                logger.info(f"Invalid packet type received: {packet.type}")
        except Exception as e:
            logger.error(f"Error in handle_packet: {e}")

    async def relay_process(self) -> None:
        """
        Listens to relay server read buffer - Relay node data
        """
        while True:
            try:
                packet_byte_array = await self.relay_server_read_buffer.get()
                packet = PacketFactory.create_packet(packet_byte_array)
                await self.handle_packet(packet)
            except Exception as e:
                logger.error(f"Error in read_relay_node: {e}")

    async def connection_process(self) -> None:
        """
        Listens to connection buffer for connection packets from the relay node.
        Connection packets are heartbeats from the devices worn by different players to inform the game engine of their connection.
        """
        while True:
            try:
                connection_packet = await self.connection_buffer.get()
                player, device, first_conn, status = connection_packet.player, connection_packet.device, connection_packet.first_conn, connection_packet.status
                if first_conn:
                    logger.critical(f"SENDING FIRST CONNECTION GAME STATE for device {device} for player {player}")
                    await self.send_relay_node()
                if device == 12:
                    device = "gun"
                elif device == 13:
                    device = "glove"
                elif device == 14:
                    device = "vest"
                await self.send_visualiser_connection(CONNECTION_TOPIC, player, device, status)
            except Exception as e:
                logger.error(f"Error in connection_process: {e}")

    async def gun_process(self, gun_buffer: asyncio.Queue, health_buffer: asyncio.Queue) -> None:
        """
        When gun packet is received, wait for health packet with timeout
        If health packet received before timeout, IR registered , and puts in central event buffer. Else, shot missed
        """
        while True:
            try:
                player = await gun_buffer.get()
                logger.critical(f"Attempted to shoot")
                try:
                    await asyncio.wait_for(health_buffer.get(), timeout=GUN_TIMEOUT)
                    logger.critical("Hit - Received health packet")
                    if player == 1:
                        await self.event_buffer.put((player, "gun", self.p1_logger))
                    else:
                        await self.event_buffer.put((player, "gun", self.p2_logger))
                    logger.critical("Added gun to action buffer")
                except asyncio.TimeoutError:
                    if player == 1:
                        await self.event_buffer.put((player, "miss", self.p1_logger))
                    else:
                        await self.event_buffer.put((player, "miss", self.p2_logger))
                    logger.critical(f"Missed - No Health Packet Received")
            except Exception as e:
                logger.error(f"Error in handle_gun: {e}")
                
    async def prediction_process(self) -> None:
        """
        Puts predicted action from AI engine into a central event buffer for processing
        """
        while True:
            try:
                player, predicted_data = await self.ai_engine_write_buffer.get()
                if player == 1:
                    await self.event_buffer.put((player, predicted_data, self.p1_logger))
                else:
                    await self.event_buffer.put((player, predicted_data, self.p2_logger))
            except Exception as e:
                logger.error(f"Error in prediction process: {e}")
    
    def is_invalid(self, player: int, action: str) -> bool:
        if (datetime.now() - self.last_send_dictionary[player] < timedelta(seconds=3)):
            return True
        return action in ["shoot", "walk"]
    
    async def process(self) -> None:
        """
        Sends action (gun or AI) to visualiser, followed by the avalanche damage if any.
        Updates game state accordingly and puts into eval_client_send_buffer to queue sending to eval_server
        """
        while True:
            try:
                # event_buffer: (player: int, action: str, log)
                player, action, log = await self.event_buffer.get()

                visualiser_state = self.p1_visualiser_state if player == 1 else self.p2_visualiser_state
                fov, snow_number = visualiser_state.get_fov(), visualiser_state.get_snow_number()

                hit, action_possible = self.game_state.perform_action(action, player, fov, snow_number)
                action = "gun" if action == "miss" else action

                self.last_send_dictionary[player] = datetime.now()

                await self.send_visualiser_action(ACTION_TOPIC, player, action, hit, action_possible, snow_number)
                log(f"Data for player {player} with FOV: {hit}, ACTION_POSSIBLE: {action_possible} and SNOW_NUMBER: {snow_number}")
                await self.send_relay_node()
                # self.update_roulette_dictionary(player, action)
                
            except Exception as e:
                logger.error(f"Exception in process: {e}")
                raise
    
    async def send_visualiser_connection(self, topic: str, player: int, device: str, status: int) -> None:
        message = self.generate_connection_mqtt_message(player, device, status)
        await self.visualiser_send_buffer.put((topic, message))

    async def send_visualiser_action(self, topic: str, player: int, action: str, hit: bool, action_possible: bool, avalanche_count: int) -> None:
        message = self.generate_action_mqtt_message(player, action, hit, action_possible, avalanche_count)
        await self.visualiser_send_buffer.put((topic, message))

    def generate_connection_mqtt_message(self, player: int, device: str, status: int) -> json:
        connection_payload = {
            'player': player,
            'device': device,
            'status': status
        }

        return json.dumps(connection_payload)
    
    def generate_ge_sight_mqtt_message(self, player: int, ge_sight: bool, ge_avalanche: int) -> json:
        ge_sight_payload = {
            'player': player,
            'ge_sight': ge_sight,
            'ge_avalanche': ge_avalanche
        }

        return json.dumps(ge_sight_payload)

    def generate_action_mqtt_message(self, player: int, action: str, hit: bool, action_possible: bool, avalanche_count: int) -> json:
        action_payload = {
            'player': player,
            'action': action,
            'hit': hit,
            'action_possible': action_possible,
            'avalanche_count': avalanche_count,
            'game_state': self.game_state.to_dict()
        }

        return json.dumps(action_payload)

    def generate_game_state(self, player: int, predicted_action: str) -> json:
        logger.debug(f"Generating game state with action: {predicted_action}")
        eval_data = {
            'player_id': player, 
            'action': str(predicted_action), 
            'game_state': self.game_state.to_dict()
        }
        logger.info(f"Generated eval data for player {player}: {eval_data}")

        return json.dumps(eval_data)
    
    def generate_game_state_packet(self) -> tuple[GunPacket, GunPacket, HealthPacket, HealthPacket]:
        p1_gun_packet = GunPacket()
        p1_gun_packet.player, p1_gun_packet.ammo = 1, self.game_state.player_1.num_bullets
        logger.info(f"Sending ammo packet to relay server p1")
        p2_gun_packet = GunPacket()
        p2_gun_packet.player, p2_gun_packet.ammo = 4, self.game_state.player_2.num_bullets
        logger.info(f"Sending ammo packet to relay server p2")

        p1_health_packet = HealthPacket()
        p1_health_packet.player = 3
        p1_health_packet.p_health, p1_health_packet.s_health = self.game_state.player_1.hp, self.game_state.player_1.hp_shield
        logger.info(f"Sending health packet to relay server p1")
        p2_health_packet = HealthPacket()
        p2_health_packet.player = 6
        p2_health_packet.p_health, p2_health_packet.s_health = self.game_state.player_2.hp, self.game_state.player_2.hp_shield
        logger.info(f"Sending health packet to relay server: p2")

        return p1_gun_packet, p2_gun_packet, p1_health_packet, p2_health_packet
    
    async def send_relay_node(self) -> None:
        p1_gun_packet, p2_gun_packet, p1_health_packet, p2_health_packet = self.generate_game_state_packet()

        await self.relay_server_send_buffer.put(p1_gun_packet.to_bytes())
        await self.relay_server_send_buffer.put(p2_gun_packet.to_bytes())
        await self.relay_server_send_buffer.put(p1_health_packet.to_bytes())
        await self.relay_server_send_buffer.put(p2_health_packet.to_bytes())

    async def visualiser_state_process(self) -> None:
        for player in [1, 2]:
            ge_sight = self.p1_visualiser_state.get_fov() if player == 1 else self.p2_visualiser_state.get_fov()
            ge_avalanche = self.p1_visualiser_state.get_snow_number() if player == 1 else self.p2_visualiser_state.get_snow_number()
            await self.visualiser_send_buffer.put((GE_SIGHT_TOPIC, self.generate_ge_sight_mqtt_message(player, ge_sight, ge_avalanche)))

        while True:
            try:
                sight_payload = await self.visualiser_read_buffer.get()
                sight_payload = json.loads(sight_payload)
                player, fov, snow_number = sight_payload['player'], sight_payload['in_sight'], sight_payload['avalanche']
                visualiser_state = self.p1_visualiser_state if player == 1 else self.p2_visualiser_state

                visualiser_state.set_fov(fov)
                visualiser_state.set_snow_number(snow_number)

                await self.visualiser_send_buffer.put((GE_SIGHT_TOPIC, self.generate_ge_sight_mqtt_message(player, fov, snow_number)))

            except Exception as e:
                logger.error(f"Error in visualiser_state_process: {e}")

    async def start(self) -> None:
        self.tasks = [
            asyncio.create_task(self.initiate_mqtt()),
            asyncio.create_task(self.initiate_relay_server()),
            asyncio.create_task(self.initiate_ai_engine()),
            asyncio.create_task(self.relay_process()),
            asyncio.create_task(self.gun_process(gun_buffer=self.p1_gun_buffer, health_buffer=self.p1_health_buffer)),
            asyncio.create_task(self.gun_process(gun_buffer=self.p2_gun_buffer, health_buffer=self.p2_health_buffer)),
            asyncio.create_task(self.prediction_process()),
            asyncio.create_task(self.process()),
            asyncio.create_task(self.visualiser_state_process()),
            asyncio.create_task(self.connection_process()),
        ]
        try:
            # self.init_roulette()
            await asyncio.gather(*self.tasks)
        except Exception as e:
            logger.error(f"An error occurred while running game engine tasks: {e}")
    
    async def run(self) -> None:
        try:
            logger.critical("Starting Game engine.")
            await self.start()
        except KeyboardInterrupt:
            logger.critical("\nCTRL+C detected, stopping...")
            await self.stop()
            logger.critical("Game engine stopped.")
        except Exception as e:
            logger.error(f"An error occurred while running game engine tasks: {e}")
