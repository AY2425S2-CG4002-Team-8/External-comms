import json


from tcp.tcp_client import TcpClient

test_data = {
    "player_id": 1, 
    "action": "gun", 
    "game_state": {
        "p1": {
            "hp": 100, 
            "bullets": 5, 
            "bombs": 2, 
            "shield_hp": 0, 
            "deaths": 0, 
            "shields": 3
        },
        "p2": {
            "hp": 95, 
            "bullets": 6, 
            "bombs": 2, 
            "shield_hp": 0, 
            "deaths": 0, 
            "shields": 3
        },
    }
}


class EvalClient:
    def __init__(self, secret_key, host, port):
        self.secret_key = secret_key
        self.tcp_client = TcpClient(secret_key, host, port)
    
    async def initiate_eval_client(self):
        await self.tcp_client.connect_to_server()
        await self.tcp_client.handshake()
        while True:
            print("Press enter")
            x = input()
            await self.tcp_client.send_message(json.dumps(test_data))
            success, res = await self.tcp_client.receive_message()
            print(success, res)
