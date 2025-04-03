import asyncio
from collections import deque
import json
from mqtt.mqtt_client import MqttClient
from eval_client import EvalClient
from packet import GunPacket, HealthPacket, PacketFactory, IMU, HEALTH, GUN, CONN
from relay_server import RelayServer
from ai_engine import AiEngine
from game_state import GameState, Round, VisualiserState
from config import AI_READ_BUFFER_MAX_SIZE, CONNECTION_TOPIC, EVENT_TIMEOUT, GE_SIGHT_TOPIC, GOOGLE_DRIVE_FOLDER_ID, GUN_TIMEOUT, SECRET_KEY, HOST, MQTT_HOST, MQTT_PORT, SEND_TOPICS, READ_TOPICS, MQTT_BASE_RECONNECT_DELAY, MQTT_MAX_RECONNECT_DELAY, MQTT_MAX_RECONNECT_ATTEMPTS, RELAY_SERVER_PORT, ACTION_TOPIC, ALL_INTERFACE, SERVICE_ACCOUNT_FILE
from logger import get_logger
import random
import os
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account

logger = get_logger(__name__)
perceived_game_round = 1

class GameEngine:
    def __init__(self, port):
        self.secret_key = SECRET_KEY
        self.host = HOST
        self.port = port

        self.game_state = GameState()
        self.p1_visualiser_state = VisualiserState()
        self.p2_visualiser_state = VisualiserState()
        self.round = Round()

        self.game_state_lock = asyncio.Lock()
        self.p1_event = asyncio.Event()
        self.p2_event = asyncio.Event()

        self.eval_client_read_buffer = asyncio.Queue()
        self.eval_client_send_buffer = asyncio.Queue()
        self.visualiser_read_buffer = asyncio.Queue()
        self.visualiser_send_buffer = asyncio.Queue()
        self.relay_server_read_buffer = asyncio.Queue()
        self.relay_server_send_buffer = asyncio.Queue()
        self.p1_ai_engine_read_buffer = asyncio.Queue(AI_READ_BUFFER_MAX_SIZE)
        self.p2_ai_engine_read_buffer = asyncio.Queue(AI_READ_BUFFER_MAX_SIZE)
        self.ai_engine_write_buffer = asyncio.Queue()
        self.connection_buffer = asyncio.Queue()
        self.p1_gun_buffer = asyncio.Queue()
        self.p1_health_buffer = asyncio.Queue()
        self.p2_gun_buffer = asyncio.Queue()
        self.p2_health_buffer = asyncio.Queue()
        self.p1_event_buffer = asyncio.Queue()
        self.p2_event_buffer = asyncio.Queue()

        self.p1_logger = logger.ge_p1
        self.p2_logger = logger.ge_p2

        self.actions = ["badminton", "fencing", "boxing", "golf", "shield", "reload", "bomb"]
        self.roulette_dictionary = {}


        self.df_buffer = []
        self.p1_end_game_event = asyncio.Event()
        self.p2_end_game_event = asyncio.Event()

        self.tasks = []

    def init_roulette(self):
        for player in [1, 2]:
            self.roulette_dictionary[player] = {
                action: 2 for action in self.actions
            }

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

    async def initiate_eval_client(self):
        eval_client = EvalClient(
            secret_key=SECRET_KEY,
            host=HOST,
            port=self.port,
            eval_client_read_buffer=self.eval_client_read_buffer,
            eval_client_send_buffer=self.eval_client_send_buffer
        )
        logger.critical("Starting Eval_Client")
        await eval_client.run()

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
            round=self.round,
            df_buffer=self.df_buffer
        )
        logger.critical("Starting AI Engine")
        await ai_engine.run()

    async def handle_packet(self, packet) -> None:
        """Handles different packet types and places actions into the appropriate queues."""
        try:
            player = packet.player
            if packet.type == GUN:
                logger.info(f"GUN PACKET Received")
                if player == 1:
                    await self.p1_event_buffer.put("gun")
                else:
                    await self.p2_event_buffer.put("gun")
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
                player, device, first_conn = connection_packet.player, connection_packet.device, connection_packet.first_conn
                if first_conn:
                    await self.send_relay_node()
                if device == 12:
                    device = "gun"
                elif device == 13:
                    device = "glove"
                elif device == 14:
                    device = "vest"
                await self.send_visualiser_connection(CONNECTION_TOPIC, player, device)
            except Exception as e:
                logger.error(f"Error in connection_process: {e}")
                
    async def prediction_process(self) -> None:
        """
        Puts predicted action from AI engine into a central event buffer for processing
        """
        while True:
            try:
                player, predicted_data = await self.ai_engine_write_buffer.get()
                if player == 1:
                    await self.p1_event_buffer.put(predicted_data)
                else:
                    await self.p2_event_buffer.put(predicted_data)
            except Exception as e:
                logger.error(f"Error in prediction process: {e}")
    
    def is_invalid(self, event: asyncio.Event, action: str, perceived_game_round: int) -> bool:
        if event.is_set() or (perceived_game_round < 22 and action == "logout"):
            return True
        return action in ["shoot", "walk"]
    
    async def process(self, player: int, event_buffer: asyncio.Queue, event: asyncio.Event, visualiser_state, log, end_game_event: asyncio.Event) -> None:
        """
        Sends action (gun or AI) to visualiser, followed by the avalanche damage if any.
        Updates game state accordingly and puts into eval_client_send_buffer to queue sending to eval_server
        """
        while True:
            try:
                action = await event_buffer.get()
                perceived_game_round = self.round.round_number
                if perceived_game_round >= 22:
                    action = "logout"
                if self.is_invalid(event=event, action=action, perceived_game_round=perceived_game_round):
                    log(f"Dropping action: {action} in round {perceived_game_round}, with event: {event.is_set()}")
                    await self.send_visualiser_action(ACTION_TOPIC, player, "drop", False, False, 0)
                    continue

                fov, snow_number = visualiser_state.get_fov(), visualiser_state.get_snow_number()

                async with self.game_state_lock:
                    hit, action_possible = self.game_state.perform_action(action, player, fov, snow_number)
                    action = "gun" if action == "miss" else action

                    if action == "logout":
                        end_game_event.set()
                        logger.critical(f"Player {player} has logged out. Setting end game event.")

                    # Prepare for eval_server
                    eval_data = self.generate_game_state(player, action)
                    await self.eval_client_send_buffer.put(eval_data)
                    event.set()
                    log(f"ROUND: {perceived_game_round}. Sending eval data for player {player} with FOV: {hit}, ACTION_POSSIBLE: {action_possible} and SNOW_NUMBER: {snow_number} to eval_server: {eval_data}")

                await self.send_visualiser_action(ACTION_TOPIC, player, action, hit, action_possible, snow_number)
                self.update_roulette_dictionary(player, action)
                
            except Exception as e:
                logger.error(f"Exception in process: {e}")
                raise

    def next_round(self) -> None:
        self.p1_event.clear()
        self.p2_event.clear()
        self.round.round_number += 1

    def update_roulette_dictionary(self, player: int, action: str) -> None:
        try:
            if action not in self.actions:
                return 
            self.roulette_dictionary[player][action] -= 1
            if action in self.roulette_dictionary and self.roulette_dictionary[player][action] == 0:
                del self.roulette_dictionary[player][action]
        except:
            logger.error(f"Error in update rolette dictionary: {e}")

    async def eval_process(self) -> None:
        """
        Listens to eval_client_read_buffer for eval_server updates
        Puts updated game state into relay_server and visualiser send_buffers to update
        """ 
        while True:
            try:
                try:
                    await asyncio.wait_for(
                        asyncio.gather(
                            self.p1_event.wait(),
                            self.p2_event.wait()
                        ),
                        timeout=EVENT_TIMEOUT 
                    )
                except asyncio.TimeoutError:
                    logger.warning("Event flag timeout occurred, proceeding without waiting.")
                    
                if not self.p1_event.is_set():
                    logger.error("P2 event is not set, continuing...")
                    await self.eval_client_send_buffer.put(self.generate_game_state(1, self.russian_roulette(1)))

                # Double await to clear both flags after both updates received
                eval_game_state = await self.eval_client_read_buffer.get()
                logger.critical(f"Received FIRST game state from eval_server = {eval_game_state}")
                self.update_game_state(eval_game_state)

                if not self.p2_event.is_set():
                    logger.error("P1 event is not set, continuing...")
                    await self.eval_client_send_buffer.put(self.generate_game_state(2, self.russian_roulette(2)))

                eval_game_state = await self.eval_client_read_buffer.get()
                logger.critical(f"Received SECOND game state from eval_server = {eval_game_state}")
                self.update_game_state(eval_game_state)

                # Propagate the final game state to visualiser with ignored action and hit
                mqtt_message = self.generate_action_mqtt_message(0, None, None, None, None)
                await self.send_relay_node()
                await self.visualiser_send_buffer.put((ACTION_TOPIC, mqtt_message))

                self.next_round()

            except Exception as e:
                logger.error(f"Error in eval_process: {e}")


    def russian_roulette(self, player: int) -> str:
        action = random.choice(list(self.roulette_dictionary[player].keys()))
        self.update_roulette_dictionary(player, action)

        return action
    
    async def send_visualiser_connection(self, topic: str, player: int, device: str) -> None:
        message = self.generate_connection_mqtt_message(player, device)
        await self.visualiser_send_buffer.put((topic, message))

    async def send_visualiser_action(self, topic: str, player: int, action: str, hit: bool, action_possible: bool, avalanche_count: int) -> None:
        message = self.generate_action_mqtt_message(player, action, hit, action_possible, avalanche_count)
        await self.visualiser_send_buffer.put((topic, message))

    def generate_connection_mqtt_message(self, player: int, device: str) -> json:
        connection_payload = {
            'player': player,
            'device': device,
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

    def update_game_state(self, eval_game_state: str) -> None:
        eval_game_state = json.loads(eval_game_state)

        for player_key, player_data in eval_game_state.items():
            if player_key == "p1":
                player = self.game_state.player_1
            else:
                player = self.game_state.player_2

            # Update the player's attributes
            player.hp = player_data.get("hp", player.hp)
            player.num_bullets = player_data.get("bullets", player.num_bullets)
            player.num_bombs = player_data.get("bombs", player.num_bombs)
            player.hp_shield = player_data.get("shield_hp", player.hp_shield)
            player.num_deaths = player_data.get("deaths", player.num_deaths)
            player.num_shield = player_data.get("shields", player.num_shield)

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

    def authenticate_google_drive(self):
        creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=["https://www.googleapis.com/auth/drive"])
        return build("drive", "v3", credentials=creds)

    # Upload file to Google Drive
    async def upload_to_google_drive(self, filename, folder_id=GOOGLE_DRIVE_FOLDER_ID):
        await asyncio.gather(
            self.p1_end_game_event.wait(),
            self.p2_end_game_event.wait()
        )
        drive_service = self.authenticate_google_drive()

        for filename in self.df_buffer:
            file_metadata = {
                "name": filename,
                "parents": [folder_id]  # Upload to specific folder
            }
            media = MediaFileUpload(filename, mimetype="text/csv")

            file = drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields="id"
            ).execute()

            print(f"Uploaded {filename} to Google Drive with file ID: {file.get('id')}")

    # Save to CSV and Upload
    def save_to_csv(self, df, filename):
        """Appends data to a CSV file, creating the file if it doesn't exist, then uploads it to Google Drive."""
        if not os.path.exists(filename):
            df.to_csv(filename, index=False)
        else:
            df.to_csv(filename, mode='a', index=False, header=False)

        # Upload to Google Drive
        self.upload_to_google_drive(filename)

    async def google_drive_process(self, player, bufs, predicted_data, predicted_conf):
         async with self.count_lock:
            max_len = len(bufs['gun_ax'])  # Assuming all lists have the same length
            unraveled_data = []
            for i in range(max_len):
                row = {col: bufs[col][i] for col in self.COLUMNS}
                unraveled_data.append(row)
        
            google_drive_df = pd.DataFrame(unraveled_data)

            # Add predicted_data and predicted_conf to the dataframe
            google_drive_df["Action"] = predicted_data
            google_drive_df["Confidence"] = predicted_conf

            # Save to CSV
            if predicted_data not in ["shoot", "walk"]:
                self.save_to_csv(google_drive_df, f"round_{(self.temporary_round + 2) // 2}_player_{player}_action_{predicted_data}.csv")
            self.temporary_round += 1

    async def stop(self) -> None:
        logger.critical("Cancelling tasks...")
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
            asyncio.create_task(self.prediction_process()),
            asyncio.create_task(self.process(player=1, event_buffer=self.p1_event_buffer, event=self.p1_event, visualiser_state=self.p1_visualiser_state, log=self.p1_logger, end_game_event=self.p1_end_game_event)),
            asyncio.create_task(self.process(player=2, event_buffer=self.p2_event_buffer, event=self.p2_event, visualiser_state=self.p2_visualiser_state, log=self.p2_logger, end_game_event=self.p2_end_game_event)),
            asyncio.create_task(self.eval_process()),
            asyncio.create_task(self.visualiser_state_process()),
            asyncio.create_task(self.connection_process())
        ]
        try:
            self.init_roulette()
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
