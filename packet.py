from logger import get_logger 
import struct
import sys

logger = get_logger(__name__)

IMU = 2
GUN = 3
HEALTH = 4
CONN = 5

class PacketFactory:
    def create_packet(packet_byte_array: bytearray):
        packet_type = packet_byte_array[0]
        if packet_type == IMU:
            return ImuPacket(packet_byte_array)
        elif packet_type == GUN:
            return GunPacket(packet_byte_array)
        elif packet_type == HEALTH:
            return HealthPacket(packet_byte_array)
        elif packet_type == CONN:
            return ConnPacket(packet_byte_array)
        else:
            raise ValueError(f"Unknown packet type: {packet_type}")

class ImuPacket:
    def __init__(self, byteArray=None) -> None:
        self.type = IMU
        if byteArray is None:
            self.seq = bytearray(1)
            self.gun_ax = bytearray(2)
            self.gun_ay = bytearray(2)
            self.gun_az = bytearray(2)
            self.gun_gx = bytearray(2)
            self.gun_gy = bytearray(2)
            self.gun_gz = bytearray(2)
            self.glove_ax = bytearray(2)
            self.glove_ay = bytearray(2)
            self.glove_az = bytearray(2)
            self.glove_gx = bytearray(2)
            self.glove_gy = bytearray(2)
            self.glove_gz = bytearray(2) # Total 25 byte
        else:
            self.seq = byteArray[1]
            self.gun_ax = struct.unpack('<h',byteArray[2:4])[0]
            self.gun_ay = struct.unpack('<h',byteArray[4:6])[0]
            self.gun_az = struct.unpack('<h',byteArray[6:8])[0]
            self.gun_gx = struct.unpack('<h',byteArray[8:10])[0]
            self.gun_gy = struct.unpack('<h',byteArray[10:12])[0]
            self.gun_gz = struct.unpack('<h',byteArray[12:14])[0]
            self.glove_ax = struct.unpack('<h',byteArray[14:16])[0]
            self.glove_ay = struct.unpack('<h',byteArray[16:18])[0]
            self.glove_az = struct.unpack('<h',byteArray[18:20])[0]
            self.glove_gx = struct.unpack('<h',byteArray[20:22])[0] 
            self.glove_gy = struct.unpack('<h',byteArray[22:24])[0]
            self.glove_gz = struct.unpack('<h',byteArray[24:26])[0]

    def to_bytes(self) -> bytes:
        """Convert ImuPacket to bytes for transmission."""
        return (
            struct.pack('<B', self.type)
            + struct.pack('<B', self.seq)
            + struct.pack('<h', self.gun_ax)
            + struct.pack('<h', self.gun_ay)
            + struct.pack('<h', self.gun_az)
            + struct.pack('<h', self.gun_gx)
            + struct.pack('<h', self.gun_gy)
            + struct.pack('<h', self.gun_gz)
            + struct.pack('<h', self.glove_ax)
            + struct.pack('<h', self.glove_ay)
            + struct.pack('<h', self.glove_az)
            + struct.pack('<h', self.glove_gx)
            + struct.pack('<h', self.glove_gy)
            + struct.pack('<h', self.glove_gz)
        )

    def __len__(self):
        return sys.getsizeof(self)

class GunPacket:
    def __init__(self, byteArray=None) -> None:
        self.type = GUN
        if byteArray is None:
            self.player = bytearray(1) # Device ID -> Mapped to player
            self.ammo = bytearray(1)
        else:
            self.player = byteArray[1]
            self.ammo = byteArray[2]

    def to_bytes(self) -> bytearray:
        byte_array = bytearray()
        byte_array.append(self.type)  # Ensure correct type
        byte_array.append(self.player) # Single-byte health values
        byte_array.append(self.ammo)  # Ensure correct single-byte value
        return byte_array
    
    def __len__(self):
        return sys.getsizeof(self)

class HealthPacket:
    def __init__(self, byteArray=None) -> None:
        self.type = HEALTH
        if byteArray is None:
            self.player = bytearray(1) # Device ID -> Mapped to player
            self.p_health = bytearray(1)
            self.s_health = bytearray(1)
        else:
            self.player = byteArray[1]
            self.p_health = byteArray[2]
            self.s_health = byteArray[3]

    def to_bytes(self) -> bytearray:
        byte_array = bytearray()
        byte_array.append(self.type)  # Ensure correct type
        byte_array.append(self.player) # Single-byte health values
        byte_array.append(self.p_health)
        byte_array.append(self.s_health)
        return byte_array
    
    def __len__(self):
        return sys.getsizeof(self)

class ConnPacket:
    def __init__(self, byteArray=None) -> None:
        self.type = CONN
        if byteArray is None:
            self.player = bytearray(1) 
            self.device = bytearray(1)
            self.first_conn = bytearray(1)

        else:
            self.player = byteArray[1]
            self.device = byteArray[2]
            self.first_conn = byteArray[3]

    def to_bytes(self) -> bytearray:
        byte_array = bytearray()
        byte_array.append(self.type)
        byte_array.append(self.player)
        byte_array.append(self.device)
        byte_array.append(self.first_conn)
        
        return byte_array
    
    def __len__(self):
        return sys.getsizeof(self)