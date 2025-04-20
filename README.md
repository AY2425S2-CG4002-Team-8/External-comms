# External Communications
## Setup
1. Prepare the environment (install the required packages)
``pip3 install -r requirements.txt``
2. Run the evaluation server inside the real_eval_server folder ``python WebSocketServer.py``
3. Open eval server's index.html in a browser.
4. Enter the Eval Server IP Address (127.0.0.1 if running on the same machine) and click connect. Select the B08 and enter the password (See config.py)
5. Click "Login"
6. On this screen, you should see ```TCP server waiting for connection from eval_client on port number xxxx```. Take note of the port number
7. Run deploy.py ``python deploy.py <EVAL_SERVER_PORT_NUMBER>``
8. Game Engine has started on the Ultra96

## For Relay Node Mock
- If you wish to run the mock relay node (for testing purposes in the absence of hardware), go to /int_comms/relay/ and run ``python temp_relay_node.py``

## Game Engine Architecture
### Overview
The GameEngine is the core component that orchestrates all gameplay logic, communication between devices, and state management for the laser tag system. Built using Python's asyncio framework, it handles:
- Real-time player action processing
- MQTT communication with visualizers
- TCP relay server connections
- AI prediction integration
- Game state synchronisation

### Key Features
#### Action Processing Pipeline
Input Handling:
- Gun shots via GUN packets
- IMU data via IMU packets
- Connection heartbeats via CONN packets

Central `process()` method that processes Gun and AI action events. Game State is processed and transmitted to the eval server.

#### Validation:
```
def is_invalid(self, player, event, action, round):
    # Checks:
    # 1. Event already processed
    # 2. Minimum 3s between actions
    # 3. Early logout prevention
```
#### State Updates:
- Sequential round processing with p1_event/p2_event synchronization
- Batched evaluation server updates

## Network Communication Modules

### Overview
This package provides three core networking classes for secure device communication:
1. `TcpClient` - Encrypted TCP client with auto-reconnect
2. `TcpServer` - Async TCP server with client management  
3. `MqttClient` - Robust MQTT client with QoS support

### TCP Client
- AES-256 encrypted communication (with Eval Server)
- Automatic reconnection with exponential backoff
- Message framing with length prefixes
- Async handshake protocol

#### Key Methods
- `connect()`: Establishes TCP connection
- `send_message()`: Encrypts and frames messages
- `receive_message()`: Reads and decrypts messages
- `reconnect()`: Auto-reconnect with exponential backoff

### TCP Server
- Async client management
- Dual read/write tasks per connection
- Client heartbeat monitoring
- Graceful connection cleanup

#### Key Methods
- `on_client_connect()`: Callback on client connect. Handshake verification and open read/write streams.
- `read_task()`: Continuous message ingestion
- `write_task()`: Buffered message sending

### MqttClient
- Full QoS support (0,1,2)
- Topic-based pub/sub
- Automatic reconnection with exponential backoff 
- Concurrent produce/consume
