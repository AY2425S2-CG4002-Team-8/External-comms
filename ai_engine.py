import asyncio
from datetime import datetime
import json
from config import COOLDOWN_TOPIC
from pynq import Overlay, allocate, PL, Clocks
import pynq.ps
from logger import get_logger
import pandas as pd
import numpy as np
import joblib
from numpy import fft
from sklearn.preprocessing import LabelEncoder
import os


logger = get_logger(__name__)

class AiEngine:

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~Engine Init~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~#   

    def __init__(self, p1_read_buffer: asyncio.Queue, p2_read_buffer: asyncio.Queue, write_buffer: asyncio.Queue, visualiser_send_buffer: asyncio.Queue):
        PL.reset()
        self.MAX_PREDICTION_DATA_POINTS = 35 
        self.FEATURE_SIZE = 12
        self.PACKET_TIMEOUT = 0.2

        self.p1_read_buffer = p1_read_buffer
        self.p2_read_buffer = p2_read_buffer
        self.write_buffer = write_buffer
        self.visualiser_send_buffer = visualiser_send_buffer

        self.COLUMNS = ['gun_ax', 'gun_ay', 'gun_az', 'gun_gx', 'gun_gy', 'gun_gz', 'glove_ax', 'glove_ay', 'glove_az', 'glove_gx', 'glove_gy', 'glove_gz']
        self.bitstream_path = "/home/xilinx/capstone/FPGA-AI/mlp_trim35.bit"
        self.input_size = 132 
        self.output_size = 10  
        self.scaler_path = "/home/xilinx/capstone/FPGA-AI/robust_scaler_mlp_trim35.save"
        self.scaler = joblib.load(self.scaler_path)
        self.classes = '/home/xilinx/capstone/FPGA-AI/classes_comb.npy'
        self.label_encoder = LabelEncoder()
        self.label_encoder.classes_ = np.load(self.classes, allow_pickle=True)
        self.dir = os.path.dirname(__file__)
        self.csv_dir = os.path.join(self.dir, "./output")

        # Insert overlay and set up modules
        self.ol = Overlay(self.bitstream_path)
        if not self.ol.axi_dma_0:
            print("ERROR: DMA 0 Not Detected")
            exit
        self.dma_0 = self.ol.axi_dma_0
        self.dma_0_send = self.dma_0.sendchannel
        self.dma_0_recv = self.dma_0.recvchannel

        if not self.ol.axi_dma_1:
            print("ERROR: DMA 1 Not Detected")
            exit
        self.dma_1 = self.ol.axi_dma_1
        self.dma_1_send = self.dma_1.sendchannel
        self.dma_1_recv = self.dma_1.recvchannel

        if not self.ol.action_mlp_0:
            print("ERROR: MLP 0 Not Detected")
            exit
        self.mlp_0 = self.ol.action_mlp_0

        if not self.ol.action_mlp_1:
            print("ERROR: MLP 1 Not Detected")
            exit
        self.mlp_1 = self.ol.action_mlp_1

        # Activate neural network IP module
        self.mlp_0.write(0x0, 0x81) # 0 (AP_START) to “1” and bit 7 (AUTO_RESTART) to “1”
        self.mlp_1.write(0x0, 0x81) # 0 (AP_START) to “1” and bit 7 (AUTO_RESTART) to “1”

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~AI Preprocessing~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~#   
    
    def feature_eng(self, df):
        cols = ['gun_ax', 'gun_ay', 'gun_az', 'gun_gx', 'gun_gy', 'gun_gz', 'glove_ax', 'glove_ay', 'glove_az', 'glove_gx', 'glove_gy', 'glove_gz']
        time_series_set = df.iloc[0,:]
        row_df = pd.DataFrame()
        for col in cols:
            cell_cols = [f'{col}_sem', f'{col}_mean', f'{col}_rank', f'{col}_max', f'{col}_min', f'{col}_range', f'{col}_iqr', f'{col}_skew', f'{col}_kurt', f'{col}_std', f'{col}_median']
            cell_df = pd.DataFrame(columns=cell_cols)
            time_series =  pd.DataFrame(time_series_set[col])
            cell_df[f'{col}_mean'] = time_series.mean()
            cell_df[f'{col}_sem'] = time_series.sem()
            cell_df[f'{col}_rank'] = time_series.rank()
            cell_df[f'{col}_max'] = time_series.max()
            cell_df[f'{col}_min'] = time_series.min()
            cell_df[f'{col}_range'] = cell_df[f'{col}_max'] - cell_df[f'{col}_min']
            cell_df[f'{col}_std'] = time_series.std()
            cell_df[f'{col}_skew'] = time_series.skew() 
            cell_df[f'{col}_kurt'] = time_series.kurtosis()
            cell_df[f'{col}_median'] = time_series.median()
            cell_df[f'{col}_iqr'] = time_series.quantile(0.75) - time_series.quantile(0.25)
        
            row_df = pd.concat((row_df, cell_df), axis=1)
        
        return row_df

    def classify(self, df: pd.DataFrame, player: int) -> str:
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~AI Preprocessing~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~#   
        # Feature engineering
        df = self.feature_eng(df)
        # Scaling
        input = self.scaler.transform(df.to_numpy())
        input = input.flatten().reshape(input.shape[1], 1)

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~AI Inferencing~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~#   
        input_buffer = allocate(shape=(self.input_size,), dtype=np.float32)
        output_buffer = allocate(shape=(self.output_size,), dtype=np.float32)
        for i in range(self.input_size):
            input_buffer[i] = input[i]

        # Player 1
        if player == 1:
            self.dma_0_send.transfer(input_buffer)
            self.dma_0_recv.transfer(output_buffer)

            # Wait for completion
            self.dma_0_send.wait()
            self.dma_0_recv.wait()

            if(self.dma_0_send.error):
                print("DMA_0 SEND ERR: " + self.dma_0_send.error)
            if(self.dma_0_recv.error):
                print("DMA_0 RECV ERR: " + self.dma_0_recv.error)

        # Player 2
        else:
            self.dma_1_send.transfer(input_buffer)
            self.dma_1_recv.transfer(output_buffer)

            # Wait for completion
            self.dma_1_send.wait()
            self.dma_1_recv.wait()

            if(self.dma_1_send.error):
                print("DMA_1 SEND ERR: " + self.dma_1_send.error)
            if(self.dma_1_recv.error):
                print("DMA_1 RECV ERR: " + self.dma_1_recv.error)

        pred = np.argmax(output_buffer)
        pred_class = self.label_encoder.inverse_transform([pred])
        del input_buffer, output_buffer
        return pred_class[0]
    
    async def run(self) -> None:
        await asyncio.gather(
            self.predict(player=1, read_buffer=self.p1_read_buffer),
            self.predict(player=2, read_buffer=self.p2_read_buffer)
        )

    async def clear_queue(self, queue: asyncio.Queue) -> None:
        """Clears all items from an asyncio queue."""
        while not queue.empty():
            try:
                queue.get_nowait()
                logger.warning("Cleared queue")
                queue.task_done()
            except asyncio.QueueEmpty:
                logger.warning(f"Queue is empty with len: {queue.qsize()}")
                break

    async def send_visualiser_cooldown(self, topic: str, player: int, ready: bool) -> None:
        message = self.generate_cooldown_mqtt_message(player, ready)
        logger.debug(f"Sending cooldown to topic {topic} on visualiser: {message}")
        await self.visualiser_send_buffer.put((topic, message))

    def generate_cooldown_mqtt_message(self, player: int, ready: bool) -> json:
        cooldown_payload = {
            'player': player,
            'ready': ready,
        }

        return json.dumps(cooldown_payload)

    def save_data_to_csv(self, data_dictionary):
        """
        Saves the data dictionary as a CSV file in the output directory.
        """
        if not os.path.exists(self.csv_dir):
            os.makedirs(self.csv_dir)  # Ensure the directory exists

        # Generate a timestamped filename
        filename = f"{self.csv_dir}/prediction_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        # Convert dictionary to DataFrame and save
        df = pd.DataFrame.from_dict(data_dictionary)
        df.to_csv(filename, index=False)  # Save without row indices

    async def predict(self, player: int, read_buffer: asyncio.Queue) -> None:
        """
        Collects self.PREDICTION_DATA_POINTS packets to form a dictionary of arrays (current implementation) for AI inference
        AI inference is against hardcoded dummy IMU data
        """
        log = logger.ai_p1 if player == 1 else logger.ai_p2
        try:
            while True:
                await self.clear_queue(read_buffer)
                packets = 0
                bufs = {col: [] for col in self.COLUMNS}

                log("AI Engine: Starting to collect data for prediction")
                for i in range(self.MAX_PREDICTION_DATA_POINTS):
                    try:
                        packet = await asyncio.wait_for(read_buffer.get(), timeout=self.PACKET_TIMEOUT)
                        bufs['gun_ax'].append(packet.gun_ax)
                        bufs['gun_ay'].append(packet.gun_ay)
                        bufs['gun_az'].append(packet.gun_az)
                        bufs['gun_gx'].append(packet.gun_gx)
                        bufs['gun_gy'].append(packet.gun_gy)
                        bufs['gun_gz'].append(packet.gun_gz)
                        bufs['glove_ax'].append(packet.glove_ax)
                        bufs['glove_ay'].append(packet.glove_ay)
                        bufs['glove_az'].append(packet.glove_az)
                        bufs['glove_gx'].append(packet.glove_gx)
                        bufs['glove_gy'].append(packet.glove_gy)
                        bufs['glove_gz'].append(packet.glove_gz)
                        packets += 1
                        log(f"IMU packet Received on AI: {i+1}")

                    except asyncio.TimeoutError:
                        break

                # If data buffer is < threshold, we skip processing and continue to the next iteration
                if packets < 10:
                    log(f"{packets} packets received. Skipping prediction")
                    continue
                
                await self.send_visualiser_cooldown(COOLDOWN_TOPIC, player, False)
                df = pd.DataFrame([bufs])

                predicted_data = await asyncio.to_thread(self.classify, df, player)
                predicted_data = "bomb" if predicted_data == "snowbomb" else predicted_data
                log(f"AI Engine Prediction: {predicted_data}")

                await self.write_buffer.put((player, predicted_data))
                await asyncio.sleep(3)
                await self.send_visualiser_cooldown(COOLDOWN_TOPIC, player, True)

        except Exception as e:
            logger.error(f"Error occurred in the AI Engine: {e}")
   