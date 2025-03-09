import asyncio
import json
from pynq import Overlay, allocate, PL, Clocks
import pynq.ps
from logger import get_logger
import pandas as pd
import numpy as np
import joblib
from sklearn.preprocessing import LabelEncoder


logger = get_logger(__name__)

class AiEngine:

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~Engine Init~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~#   

    def __init__(self, read_buffer, write_buffer):
        self.PREDICTION_DATA_POINTS = 40 # Actual:30
        self.read_buffer = read_buffer
        self.write_buffer = write_buffer
        self.bitstream_path = "/home/xilinx/capstone/FPGA-AI/mlp_inline_unroll_part_flow_pipe_merge.bit"
        self.input_size = 192 # Actual:300
        self.output_size = 6  # Actual:9
        self.window_size = 9  # Actual: 5
        self.scaler_path = "/home/xilinx/capstone/FPGA-AI/robust_scaler.save"
        self.scaler = joblib.load(self.scaler_path)
        self.classes = '/home/xilinx/capstone/FPGA-AI/classes.npy'
        self.label_encoder = LabelEncoder()
        self.label_encoder.classes_ = np.load(self.classes, allow_pickle=True)

        # Insert overlay and set up modules
        self.ol = Overlay(self.bitstream_path)
        if not self.ol.axi_dma_0:
            print("ERROR: DMA Not Detected")
            exit
        self.dma = self.ol.axi_dma_0
        self.dma_send = self.dma.sendchannel
        self.dma_recv = self.dma.recvchannel

        if self.ol.action_mlp_0:
            self.mlp = self.ol.action_mlp_0
        elif self.ol.action_mlp_1:
            self.mlp = self.ol.action_mlp_1

        # Activate neural network IP module
        self.mlp.write(0x0, 0x81) # 0 (AP_START) to “1” and bit 7 (AUTO_RESTART) to “1”

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~Data Link with GE~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~#   

    def get_data(self, data) -> dict[str, list[int]]: 
        """
        Converts a list of PacketImu objects into a combined input list for the AI.
        """
        gun_ax_array, gun_ay_array, gun_az_array = [], [], []
        gun_gx_array, gun_gy_array, gun_gz_array = [], [], []
        glove_ax_array, glove_ay_array, glove_az_array = [], [], []
        glove_gx_array, glove_gy_array, glove_gz_array = [], [], []

        for packet in data:
            # Gets integer from bytes. Little endian as defined by relay node and signed since values can be -ve
            gun_ax_array.append(packet.gun_ax)
            gun_ay_array.append(packet.gun_ay)
            gun_az_array.append(packet.gun_az)
            gun_gx_array.append(packet.gun_gx)
            gun_gy_array.append(packet.gun_gy)
            gun_gz_array.append(packet.gun_gz)
            glove_ax_array.append(packet.glove_ax)
            glove_ay_array.append(packet.glove_ay)
            glove_az_array.append(packet.glove_az)
            glove_gx_array.append(packet.glove_gx)
            glove_gy_array.append(packet.glove_gy)
            glove_gz_array.append(packet.glove_gz)

        return {
            'gun_ax': gun_ax_array,
            'gun_ay': gun_ay_array,
            'gun_az': gun_az_array,
            'gun_gx': gun_gx_array,
            'gun_gy': gun_gy_array,
            'gun_gz': gun_gz_array,
            'glove_ax': glove_ax_array,
            'glove_ay': glove_ay_array,
            'glove_az': glove_az_array,
            'glove_gx': glove_gx_array,
            'glove_gy': glove_gy_array,
            'glove_gz': glove_gz_array
        }

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~AI Preprocessing~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~#   

    def trim(self, df):
        if len(df) > self.PREDICTION_DATA_POINTS:
            df = df.head(self.PREDICTION_DATA_POINTS)
        return df

    # Duplicate the values of df until the window size is met
    def fill_window(self, df,window):
        current_size = len(df)
    
        if current_size < window:
            # Calculate how many times to repeat the DataFrame
            repeat_times = (window // current_size) + 1  # We add 1 to make sure we have enough rows
            # Repeat and slice the DataFrame
            df = pd.concat([df] * repeat_times, ignore_index=True).head(window)
                
        return df

    def process_csv(self, df):
        # Populate until window size is met
        df = self.fill_window(df, self.PREDICTION_DATA_POINTS)
        df = self.trim(df)
        return df
    
    def feature_eng(self, df):
        timestep_dataset = pd.DataFrame()

        cols = ['gun_ax', 'gun_ay', 'gun_az', 'gun_gx', 'gun_gy', 'gun_gz', 'glove_ax', 'glove_ay', 'glove_az', 'glove_gx', 'glove_gy', 'glove_gz']
        # Break up each sensor feature into one feature per timestep
        for feature in cols:
            timestep_dataset[[f"{feature}_{i}" for i in range(self.PREDICTION_DATA_POINTS)]] = df[feature].to_list()

        timestep_dataset = timestep_dataset.map(int)
        timestep_dataset["action"] = df["action"]

        # Rolling Window Stats
        df_dict = {}
        window_df = pd.DataFrame()

        def get_window(df, window, cols):
            rolled = df.rolling(window, min_periods=window, step=window)
            roll_mean = rolled.mean()
            roll_max = rolled.max()
            roll_min = rolled.min()
            roll_std = rolled.std()
            new_row = []
            for i in range(1,int(self.PREDICTION_DATA_POINTS/self.window_size)):
                new_row = new_row + [roll_mean[i], roll_max[i], roll_min[i], roll_std[i], roll_skew[i]]
            df = pd.DataFrame(new_row).transpose().reset_index().drop("index", axis=1)
            df.columns = cols
            return df

        for index in range(0, 12):
            window = timestep_dataset.iloc[:,index*self.PREDICTION_DATA_POINTS:(index*self.PREDICTION_DATA_POINTS)+self.PREDICTION_DATA_POINTS]
            label = window.columns.values[0]
            axis = label.split("_")[0] + label.split("_")[1]
            new_cols = []
            cols = [[f'{axis}_window_{i}_mean', f'{axis}_window_{i}_max', f'{axis}_window_{i}_min', f'{axis}_window_{i}_std', f'{axis}_window_{i}skew'] for i in range (int(self.PREDICTION_DATA_POINTS/self.window_size)-1)]
            for list in cols:
                new_cols = new_cols + list
            df_dict[index] = pd.DataFrame(columns = new_cols)
            for _, row in window.iterrows():
                newdf = get_window(row, self.window_size, new_cols)
                df_dict[index] = pd.concat((df_dict[index], newdf), axis=0, ignore_index=True)

        for key in df_dict:
            window_df = pd.concat((window_df, df_dict[key]), axis=1)

        window_df["action"] = df["action"].reset_index().drop("index", axis=1)
        return window_df

    def classify(self, data_dict) -> str:
        df = pd.DataFrame.from_dict(data_dict)

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~AI Preprocessing~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~#   
        
        df = self.process_csv(df)
        df.reset_index(drop=True, inplace=True)
        # Feature engineering
        df = self.feature_eng(df)
        # Scaling
        input_array = self.scaler.transform(df.drop("action", axis=1).to_numpy())

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~AI Inferencing~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~#   
        input_buffer = allocate(shape=(self.input_size,), dtype=np.float32)
        output_buffer = allocate(shape=(self.output_size,), dtype=np.float32)
        for i in range(self.input_size):
            self.input_buffer[i] = input_array[i]
        self.dma_send.transfer(self.input_buffer)
        self.dma_recv.transfer(self.output_buffer)
        
        # Wait for completion
        self.dma_send.wait()
        self.dma_recv.wait()
        
        if (self.dma_send.error):
            print("DMA_SEND ERR: " + self.dma_send.error)
        if (self.dma_recv.error):
            print("DMA_RECV ERR: " + self.dma_recv.error)

        # Obtain model prediction
        e_x = np.exp(self.output_buffer - np.max(self.output_buffer))
        softmax = e_x / e_x.sum(axis=0)

        #TODO: Check softmax confidence level and classify low confidence as null

        pred = np.argmax(softmax)
        pred_class = self.label_encoder.inverse_transform(pred)
        del input_buffer, output_buffer
        return pred_class
    
    async def run(self) -> None:
        await asyncio.gather(
            self.predict(1)
        )

    async def predict(self, player: int) -> None:
        """
        Collects self.PREDICTION_DATA_POINTS packets to form a dictionary of arrays (current implementation) for AI inference
        AI inference is against hardcoded dummy IMU data
        """
        data = []
        try:
            while True:
                data.clear()
                while len(data) < self.PREDICTION_DATA_POINTS:
                    try:
                        packet = await asyncio.wait_for(self.read_buffer.get(), timeout=0.5)
                        data.append(packet)
                        logger.debug(f"IMU packet: {packet}. Received: {len(data)}/{self.PREDICTION_DATA_POINTS}")
                    except asyncio.TimeoutError:
                        break

                # If data buffer is empty, we skip processing and continue to the next iteration
                if len(data) < 10:
                    continue

                logger.info(f"Predicting with window size: {len(data)}")
                data_dictionary = self.get_data(data)
                predicted_data = self.classify(data_dictionary)
                logger.debug(f"AI Engine Prediction: {predicted_data}")
                await self.write_buffer.put(predicted_data)

        except Exception as e:
            logger.error(f"Error occurred in the AI Engine: {e}")
        # try:
        #     while True:
        #         data.clear()
        #         while len(data) < self.PREDICTION_DATA_POINTS:
        #             packet = await self.read_buffer.get()
        #             data.append(packet)
        #             logger.debug(f"IMU packet: {packet}. Received: {len(data)}/{self.PREDICTION_DATA_POINTS}")

        #         if len(data) != self.PREDICTION_DATA_POINTS:
        #             logger.debug(f"Packet size of {self.PREDICTION_DATA_POINTS} was not received")
        #             continue
                
        #         data_dictionary = self.get_data(data)
        #         predicted_data = self.classify(data_dictionary)
        #         logger.debug(f"AI Engine Prediction: {predicted_data}")
        #         await self.write_buffer.put(predicted_data)

        # except Exception as e:
        #     logger.error(f"Error occurred in the AI Engine: {e}")