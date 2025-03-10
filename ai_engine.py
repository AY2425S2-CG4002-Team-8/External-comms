import asyncio
import json
from pynq import Overlay, allocate, PL, Clocks
import pynq.ps
from logger import get_logger
import pandas as pd
import numpy as np
import joblib
from numpy import fft
from sklearn.preprocessing import LabelEncoder


logger = get_logger(__name__)

class AiEngine:

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~Engine Init~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~#   

    def __init__(self, read_buffer, write_buffer):
        PL.reset()
        self.PREDICTION_DATA_POINTS = 40 # Actual:30
        self.read_buffer = read_buffer
        self.write_buffer = write_buffer
        self.bitstream_path = "/home/xilinx/capstone/FPGA-AI/off_mlp.bit"
        self.input_size = 228 # Actual:300
        self.output_size = 9  # Actual:9
        self.window_size = 9  # Actual: 5
        self.FFT_NUM = 5
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

    def get_fft(self, row):
        row = row.values
        fft_values = np.abs(fft.fft(row))
        mag_cols = [f'mag_{i}' for i in range(self.FFT_NUM)] 
        freq_cols = [f'freq_{i}' for i in range(self.FFT_NUM)] 
        # Ignore DC Signal
        fft_values[0] = 0
        frequencies = fft.fftfreq(len(row))
        # Get the top 5 fft_values
        mag_values = sorted( [(x,i) for (i,x) in enumerate(fft_values)], reverse=True)
        top_mag_fft = []
        for x,i in mag_values:
            if x not in top_mag_fft:
                top_mag_fft.append( x[0] )
                if len(top_mag_fft) == self.FFT_NUM:
                        break
        mag_df = pd.DataFrame([top_mag_fft], columns=mag_cols)

        freq_values = sorted( [(x,i) for (i,x) in enumerate(frequencies)], reverse=True)
        top_freq_fft = []
        for x,i in freq_values:
            if x not in top_freq_fft:
                top_freq_fft.append( x )
                if len(top_freq_fft) == self.FFT_NUM:
                        break
        freq_df = pd.DataFrame([top_freq_fft], columns=freq_cols)
        df = pd.concat((mag_df, freq_df), axis=1)
        return df

    def process_csv(self, df):
        bufs = {}
        for col in df.columns:
            bufs[col] = []
        for _, row in df.iterrows():
            # Append readings
            for col in df.columns:
                bufs[col].append(row[col])
        
        df = pd.DataFrame([bufs])
        return df
    
    def feature_eng(self, df):
        cols = ['gun_ax', 'gun_ay', 'gun_az', 'gun_gx', 'gun_gy', 'gun_gz', 'glove_ax', 'glove_ay', 'glove_az', 'glove_gx', 'glove_gy', 'glove_gz']
        time_series_set = df.iloc[0,:]
        row_df = pd.DataFrame()
        for col in cols:
            cell_cols = [f'{col}_mean', f'{col}_max', f'{col}_min', f'{col}_range', f'{col}_iqr', f'{col}_skew', f'{col}_kurt', f'{col}_std', f'{col}_median']
            cell_df = pd.DataFrame(columns=cell_cols)
            time_series = pd.DataFrame(time_series_set[col])
            cell_df[f'{col}_mean'] = time_series.mean()
            cell_df[f'{col}_max'] = time_series.max()
            cell_df[f'{col}_min'] = time_series.min()
            cell_df[f'{col}_range'] = cell_df[f'{col}_max'] - cell_df[f'{col}_min']
            cell_df[f'{col}_std'] = time_series.std()
            cell_df[f'{col}_skew'] = time_series.skew() 
            cell_df[f'{col}_kurt'] = time_series.kurtosis()
            cell_df[f'{col}_median'] = time_series.median()
            cell_df[f'{col}_iqr'] = time_series.quantile(0.75) - time_series.quantile(0.25)
        
            row_df = pd.concat((row_df, cell_df), axis=1)

            fft_df = self.get_fft(time_series)
            row_df = pd.concat((row_df, fft_df), axis=1)
        
        return row_df

    def classify(self, data_dict) -> str:
        df = pd.DataFrame.from_dict(data_dict)

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~AI Preprocessing~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~#   
        
        df = self.process_csv(df)
        df.reset_index(drop=True, inplace=True)
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
        self.dma_send.transfer(input_buffer)
        self.dma_recv.transfer(output_buffer)
        
        # Wait for completion
        self.dma_send.wait()
        self.dma_recv.wait()
        
        if(self.dma_send.error):
            print("DMA_SEND ERR: " + self.dma_send.error)
        if(self.dma_recv.error):
            print("DMA_RECV ERR: " + self.dma_recv.error)

        #TODO: Check softmax confidence level and classify low confidence as null

        pred = np.argmax(output_buffer)
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
   