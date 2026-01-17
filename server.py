import socket
import json
import threading
import time

class RPSServer:
    def __init__(self, host='0.0.0.0', port=5555):
        self.host = host
        self.port = port
        self.server_socket = None
        self.clients = {}  # {socket: {'name': str, 'status': str, 'opponent': socket, 'choice': str}}
        self.lock = threading.RLock()
        self.game_choices = ['rock', 'paper', 'scissors']

    def start(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Disable Nagle's algorithm for lower latency
        self.server_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen()
        print(f"Server started on {self.host}:{self.port}")

        try:
            while True:
                client_socket, addr = self.server_socket.accept()
                client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                print(f"New connection from {addr}")
                threading.Thread(target=self.handle_client, args=(client_socket,), daemon=True).start()
        except KeyboardInterrupt:
            print("Server stopping...")
        finally:
            self.shutdown()

    def broadcast_player_list(self):
        """Send updated player list to all clients in lobby"""
        clients_to_send = {}
        message = ""
        
        with self.lock:
            # Build list of players
            players_list = []
            for sock, info in self.clients.items():
                if info['name']:  # Only list players who have identified themselves
                    players_list.append({
                        'name': info['name'],
                        'status': info['status']
                    })
            
            message = json.dumps({'type': 'player_list', 'players': players_list}) + '\n'
            clients_to_send = {sock: info for sock, info in self.clients.items()}
        
        # Send outside of lock to avoid blocking other threads
        for sock in clients_to_send:
            try:
                sock.send(message.encode('utf-8'))
            except:
                pass

    def handle_client(self, client_socket):
        buffer = ""
        try:
            while True:
                data = client_socket.recv(4096).decode('utf-8')
                if not data:
                    break
                
                buffer += data
                
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if not line.strip(): continue
                    
                    print(f"[SERVER] Processing line: {line[:100]}", flush=True)
                    
                    try:
                        request = json.loads(line)
                        req_type = request.get('type')
                        print(f"[SERVER] Processing request type: {req_type}", flush=True)

                        if req_type == 'connect':
                            self.handle_connect(client_socket, request)
                        elif req_type == 'challenge':
                            self.handle_challenge(client_socket, request)
                        elif req_type == 'accept_challenge':
                            self.handle_accept_challenge(client_socket, request)
                        elif req_type == 'play':
                            self.handle_play(client_socket, request)
                        elif req_type == 'play_bot':
                            self.handle_play_bot(client_socket, request)
                        elif req_type == 'quit_match':
                            self.handle_quit_match(client_socket, request)
                        elif req_type == 'chat':
                            self.handle_chat(client_socket, request)
                    except json.JSONDecodeError as je:
                        print(f"[SERVER] JSON Error: {je} for line: {line}", flush=True)

        except Exception as e:
            print(f"[SERVER] Error handling client: {e}", flush=True)
        finally:
            self.disconnect_client(client_socket)

    # ... (handle_connect, handle_challenge, handle_accept_challenge remain same)

    def handle_quit_match(self, client_sock, request):
        with self.lock:
            if client_sock not in self.clients: return
            
            # Reset this player
            self.clients[client_sock]['status'] = 'idle'
            opponent_sock = self.clients[client_sock]['opponent']
            self.clients[client_sock]['opponent'] = None
            self.clients[client_sock]['choice'] = None
            
            # Notify opponent
            if opponent_sock and opponent_sock in self.clients:
                self.clients[opponent_sock]['status'] = 'idle'
                self.clients[opponent_sock]['opponent'] = None
                self.clients[opponent_sock]['choice'] = None
                try:
                    opponent_sock.send((json.dumps({'type': 'opponent_left'}) + '\n').encode('utf-8'))
                except:
                    pass
            
        self.broadcast_player_list()

    def handle_connect(self, client_sock, request):
        name = request.get('player_name')
        if not name: return

        with self.lock:
            # Check if name exists
            if any(info['name'] == name for info in self.clients.values()):
                 name = f"{name}_{int(time.time())}" # Append timestamp to make unique

            self.clients[client_sock] = {
                'name': name,
                'status': 'idle', # idle, playing, waiting
                'opponent': None,
                'choice': None
            }
            
            # Send ack
            response = {'type': 'connect_ack', 'status': 'success', 'name': name}
            client_sock.send((json.dumps(response) + '\n').encode('utf-8'))
        
        self.broadcast_player_list()

    def handle_challenge(self, challenger_sock, request):
        target_name = request.get('target_name')
        challenger_name = self.clients[challenger_sock]['name']
        
        target_sock = None
        with self.lock:
            for sock, info in self.clients.items():
                if info['name'] == target_name and info['status'] == 'idle':
                    target_sock = sock
                    break
        
        if target_sock:
            msg = {
                'type': 'challenge_request',
                'challenger': challenger_name
            }
            target_sock.send((json.dumps(msg) + '\n').encode('utf-8'))
        else:
            challenger_sock.send((json.dumps({'type': 'error', 'message': 'Player not available'}) + '\n').encode('utf-8'))

    def handle_accept_challenge(self, target_sock, request):
        challenger_name = request.get('challenger')
        accepted = request.get('accept')
        
        challenger_sock = None
        with self.lock:
            for sock, info in self.clients.items():
                if info['name'] == challenger_name:
                    challenger_sock = sock
                    break
            
            if accepted and challenger_sock and self.clients[challenger_sock]['status'] == 'idle':
                # Start game
                self.clients[target_sock]['status'] = 'playing'
                self.clients[target_sock]['opponent'] = challenger_sock
                self.clients[target_sock]['choice'] = None
                
                self.clients[challenger_sock]['status'] = 'playing'
                self.clients[challenger_sock]['opponent'] = target_sock
                self.clients[challenger_sock]['choice'] = None
                
                # Notify both
                msg_target = {'type': 'game_start', 'opponent': challenger_name, 'mode': 'pvp'}
                target_sock.send((json.dumps(msg_target) + '\n').encode('utf-8'))
                
                msg_challenger = {'type': 'game_start', 'opponent': self.clients[target_sock]['name'], 'mode': 'pvp'}
                challenger_sock.send((json.dumps(msg_challenger) + '\n').encode('utf-8'))
                
                self.broadcast_player_list()
            elif challenger_sock:
                # Rejected
                challenger_sock.send((json.dumps({'type': 'challenge_rejected', 'opponent': self.clients[target_sock]['name']}) + '\n').encode('utf-8'))

    def handle_play(self, client_sock, request):
        choice = request.get('choice')
        print(f"[PLAY] Request received: choice={choice}", flush=True)
        player_name = ""
        opponent_name = ""
        
        with self.lock:
            if client_sock not in self.clients: 
                print(f"ERROR: Client socket not in clients dict", flush=True)
                return
            
            player_name = self.clients[client_sock]['name']
            self.clients[client_sock]['choice'] = choice
            opponent_sock = self.clients[client_sock]['opponent']
            
            print(f"[PLAY] {player_name} chose: {choice}, Opponent socket: {opponent_sock is not None}", flush=True)
            
            if opponent_sock and opponent_sock in self.clients:
                opponent_name = self.clients[opponent_sock]['name']
                opponent_choice = self.clients[opponent_sock]['choice']
                
                print(f"[PLAY] {opponent_name}'s current choice: {opponent_choice}", flush=True)
                
                if opponent_choice:
                    # Both played - determine winner from current player's perspective
                    result_client = self.determine_winner(choice, opponent_choice)
                    # Determine winner from opponent's perspective
                    result_opponent = self.determine_winner(opponent_choice, choice)
                    
                    print(f"[RESULT] {player_name}({choice}) vs {opponent_name}({opponent_choice}) - Sending results", flush=True)
                    
                    # Send results to both players
                    try:
                        client_sock.send((json.dumps({
                            'type': 'game_result',
                            'my_choice': choice,
                            'opponent_choice': opponent_choice,
                            'result': result_client
                        }) + '\n').encode('utf-8'))
                        print(f"[RESULT] Sent to {player_name}", flush=True)
                    except Exception as e:
                        print(f"[ERROR] Failed to send result to {player_name}: {e}", flush=True)
                    
                    try:
                        opponent_sock.send((json.dumps({
                            'type': 'game_result',
                            'my_choice': opponent_choice,
                            'opponent_choice': choice,
                            'result': result_opponent
                        }) + '\n').encode('utf-8'))
                        print(f"[RESULT] Sent to {opponent_name}", flush=True)
                    except Exception as e:
                        print(f"[ERROR] Failed to send result to {opponent_name}: {e}", flush=True)
                    
                    # Reset choices for next round
                    self.clients[client_sock]['choice'] = None
                    self.clients[opponent_sock]['choice'] = None
                else:
                    # Opponent hasn't chosen yet - notify opponent that this player has chosen
                    print(f"[PLAY] Waiting for {opponent_name}, notifying them", flush=True)
                    try:
                        opponent_sock.send((json.dumps({'type': 'opponent_choosed'}) + '\n').encode('utf-8'))
                    except Exception as e:
                        print(f"[ERROR] Failed to notify opponent: {e}", flush=True)
            else:
                print(f"[ERROR] Opponent socket invalid or not in clients", flush=True)

    def handle_play_bot(self, client_sock, request):
        choice = request.get('choice')
        print(f"[PLAY BOT] Request received: choice={choice}", flush=True)
        import random
        server_choice = random.choice(self.game_choices)
        result = self.determine_winner(choice, server_choice)
        
        response = {
            'type': 'game_result',
            'my_choice': choice,
            'opponent_choice': server_choice,
            'result': result,
            'mode': 'bot'
        }
        try:
            client_sock.send((json.dumps(response) + '\n').encode('utf-8'))
            print(f"[PLAY BOT] Sent result: {result} ({choice} vs {server_choice})", flush=True)
        except Exception as e:
            print(f"[ERROR] Failed to send bot result: {e}", flush=True)

    def determine_winner(self, p1, p2):
        if p1 == p2: return 'draw'
        wins = {'rock': 'scissors', 'scissors': 'paper', 'paper': 'rock'}
        if wins.get(p1) == p2: return 'win'
        return 'lose'

    def disconnect_client(self, sock):
        with self.lock:
            if sock in self.clients:
                info = self.clients[sock]
                opponent_sock = info['opponent']
                
                if opponent_sock and opponent_sock in self.clients:
                    # Notify opponent
                    try:
                        opponent_sock.send((json.dumps({'type': 'opponent_left'}) + '\n').encode('utf-8'))
                        self.clients[opponent_sock]['status'] = 'idle'
                        self.clients[opponent_sock]['opponent'] = None
                    except:
                        pass
                
                del self.clients[sock]
        
        self.broadcast_player_list()
        try:
            sock.close()
        except:
            pass

    def shutdown(self):
        if self.server_socket:
            self.server_socket.close()

if __name__ == "__main__":
    server = RPSServer()
    server.start()
