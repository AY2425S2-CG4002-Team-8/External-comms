from logger import get_logger 

logger = get_logger(__name__)

IMU = 0x0
GUN = 0x1
HEALTH = 0x2

class PacketFactory:
    def create_packet(packet_byte_array: bytearray):
        if len(packet_byte_array) < 20:
            raise ValueError("Invalid packet size. Expected 20 bytes.")
        
        packet_type = packet_byte_array[0]
        logger.debug(f"Packet_type = {packet_type}")
        if packet_type == IMU:
            return ImuPacket(packet_byte_array)
        elif packet_type == GUN:
            return GunPacket(packet_byte_array)
        elif packet_type == HEALTH:
            return HealthPacket(packet_byte_array)
        else:
            raise ValueError(f"Unknown packet type: {packet_type}")

class ImuPacket:
    def __init__(self, byteArray=None) -> None:
        self.type = IMU
        if byteArray is None:
            self.ax = bytearray(2)
            self.ay = bytearray(2)
            self.az = bytearray(2)
            self.gx = bytearray(2)
            self.gy = bytearray(2)
            self.gz = bytearray(2)
            self.padding = bytearray(7) # Ensure total 20 bytes
        else:
            self.ax = byteArray[1:3]
            self.ay = byteArray[3:5]
            self.az = byteArray[5:7]
            self.gx = byteArray[7:9]
            self.gy = byteArray[9:11]
            self.gz = byteArray[11:13]
            self.padding = byteArray[13:]

    def to_bytes(self) -> bytearray:
        byte_array = bytearray()
        byte_array.append(self.type)
        byte_array.extend(self.ax)
        byte_array.extend(self.ay)
        byte_array.extend(self.az)
        byte_array.extend(self.gx)
        byte_array.extend(self.gy)
        byte_array.extend(self.gz)
        byte_array.extend(self.padding)

        return byte_array


class GunPacket:
    def __init__(self, byteArray=None) -> None:
        self.type = GUN
        if byteArray is None:
            self.shoot = 0x0
            self.padding = bytearray(18) # Ensure total 20 bytes
        else:
            self.shoot = byteArray[1]
            self.padding = byteArray[2:]

    def to_bytes(self) -> bytearray:
        byte_array = bytearray()
        byte_array.append(self.type)  # Ensure correct type
        byte_array.append(self.shoot)  # Ensure correct single-byte value
        byte_array.extend(self.padding)  # Explicit padding to 20 bytes
        return byte_array


class HealthPacket:
    def __init__(self, byteArray=None) -> None:
        self.type = HEALTH
        if byteArray is None:
            self.p1_health = 0x0
            self.p2_health = 0x0
            self.padding = bytearray(17) # Ensure total 20 bytes
        else:
            self.p1_health = byteArray[1]
            self.p2_health = byteArray[2]
            self.padding = byteArray[3:]

    def to_bytes(self) -> bytearray:
        byte_array = bytearray()
        byte_array.append(self.type)  # Ensure correct type
        byte_array.append(self.p1_health) # Single-byte health values
        byte_array.append(self.p2_health)
        byte_array.extend(self.padding)  # Explicit padding to 20 bytes
        return byte_array

