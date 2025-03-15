# Socket Configuration
SECRET_KEY="8888888888888888"
HOST="127.0.0.1"
ALL_INTERFACE=""
RELAY_SERVER_HOST_NAME="makerslab-fpga-25.d2.comp.nus.edu.sg"
RELAY_SERVER_PORT=8080

#U96 Configuration
U96_PORT=8888
U96_HOST_NAME="makerslab-fpga-25.d2.comp.nus.edu.sg"
U96_USER="xilinx"
U96_PASSWORD="b08password"

# MQTT Configuration
MQTT_HOST="175.41.155.178"
MQTT_PORT=4100
ACTION_TOPIC="GE/Vis/actions"
CONNECTION_TOPIC="GE/Vis/connections"
COOLDOWN_TOPIC="GE/Vis/cooldown"
SIGHT_TOPIC="Vis/GE/sight"
SEND_TOPICS = [(ACTION_TOPIC, 0), (CONNECTION_TOPIC, 0), (COOLDOWN_TOPIC, 0)]
READ_TOPICS = [(SIGHT_TOPIC, 2)]
MQTT_BASE_RECONNECT_DELAY=1
MQTT_MAX_RECONNECT_DELAY=60
MQTT_MAX_RECONNECT_ATTEMPTS=10

# AI configuration
AI_PACKET_TIMEOUT = 0.5
AI_READ_BUFFER_MAX_SIZE = 40

# Action Configuration
ACTION_AVALANCHE = "avalanche"
GUN_TIMEOUT = 0.3