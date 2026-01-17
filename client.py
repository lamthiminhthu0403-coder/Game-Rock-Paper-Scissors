import tkinter as tk
from tkinter import messagebox, simpledialog, Listbox, END
import socket
import json
import threading
import time
import os

# Try to import PIL for better image support (especially for jpg)
try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

class RPSClient:
    def __init__(self, root):
        self.root = root
        self.root.title("🎮 Kéo Búa Bao Online")
        self.root.geometry("800x600")
        self.root.configure(bg="#1a1a2e")
        
        # State
        self.host = '127.0.0.1'
        self.port = 5555
        self.client_socket = None
        self.player_name = ""
        self.opponent_name = ""
        self.is_connected = False
        
        # Images
        self.images = {}
        self.load_images()
        
        # UI Frames
        self.main_container = tk.Frame(root, bg="#1a1a2e")
        self.main_container.pack(fill=tk.BOTH, expand=True)
        
        self.login_frame = None
        self.lobby_frame = None
        self.game_frame = None
        
        self.setup_login_ui()

    def load_images(self):
        """Load images safely"""
        # Mapping: key -> filename
        image_files = {
            'rock': 'bua.png',
            'paper': 'bao.jpg',
            'scissors': 'keo.png'
        }
        
        cwd = os.getcwd()
        # Check current folder and bt-game-keo-bua-bao folder
        possible_paths = [cwd, os.path.join(cwd, 'bt-game-keo-bua-bao')]
        
        for key, filename in image_files.items():
            path = filename
            for p in possible_paths:
                full_path = os.path.join(p, filename)
                if os.path.exists(full_path):
                    path = full_path
                    break
            
            try:
                if HAS_PIL:
                    img = Image.open(path)
                    img = img.resize((150, 150), Image.Resampling.LANCZOS)
                    self.images[key] = ImageTk.PhotoImage(img)
                else:
                    # Fallback for standard tkinter (PNG only usually, JPG might fail)
                    if filename.endswith('.png'):
                        img = tk.PhotoImage(file=path)
                        # Zoom/Subsample for resizing if needed, but PhotoImage is limited
                        self.images[key] = img
                    else:
                        print(f"Cannot load {filename} without PIL")
                        self.images[key] = None
            except Exception as e:
                print(f"Error loading {key}: {e}")
                self.images[key] = None

    def clear_frame(self):
        for widget in self.main_container.winfo_children():
            widget.destroy()

    def setup_login_ui(self):
        self.clear_frame()
        self.root.title("Kéo Búa Bao - Đăng nhập")
        
        frame = tk.Frame(self.main_container, bg="#1a1a2e")
        frame.place(relx=0.5, rely=0.5, anchor="center")
        
        tk.Label(frame, text="ĐẠI CHIẾN KÉO BÚA BAO", font=("Segoe UI", 24, "bold"), fg="#00ff88", bg="#1a1a2e").pack(pady=20)
        
        tk.Label(frame, text="Nhập tên của bạn:", font=("Segoe UI", 12), fg="white", bg="#1a1a2e").pack(pady=5)
        
        self.name_entry = tk.Entry(frame, font=("Segoe UI", 14), width=20)
        self.name_entry.pack(pady=10)
        self.name_entry.bind('<Return>', lambda e: self.connect_to_server())
        
        btn = tk.Button(frame, text="KẾT NỐI", font=("Segoe UI", 12, "bold"), bg="#e94560", fg="white", width=15,
                       command=self.connect_to_server, relief=tk.FLAT)
        btn.pack(pady=20)

    def setup_lobby_ui(self):
        self.clear_frame()
        self.root.title(f"Sảnh Chờ - {self.player_name}")
        
        # Header
        header = tk.Frame(self.main_container, bg="#16213e", height=60)
        header.pack(fill=tk.X)
        tk.Label(header, text=f"👤 {self.player_name}", font=("Segoe UI", 14, "bold"), fg="white", bg="#16213e").pack(side=tk.LEFT, padx=20, pady=10)
        
        # Main Content
        content = tk.Frame(self.main_container, bg="#1a1a2e")
        content.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Player List
        left_panel = tk.Frame(content, bg="#1a1a2e")
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        tk.Label(left_panel, text="Danh sách người chơi online:", font=("Segoe UI", 12), fg="#00ff88", bg="#1a1a2e").pack(anchor="w")
        
        self.player_listbox = Listbox(left_panel, font=("Segoe UI", 12), bg="#0f3460", fg="white", selectmode=tk.SINGLE, relief=tk.FLAT)
        self.player_listbox.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Buttons
        btn_frame = tk.Frame(content, bg="#1a1a2e")
        btn_frame.pack(side=tk.RIGHT, fill=tk.Y)
        
        tk.Button(btn_frame, text="⚔️ THÁCH ĐẤU", font=("Segoe UI", 12, "bold"), bg="#e94560", fg="white", width=15,
                 command=self.challenge_player).pack(pady=10)

        tk.Button(btn_frame, text="🤖 CHƠI VỚI MÁY", font=("Segoe UI", 12, "bold"), bg="#3498db", fg="white", width=15,
                 command=self.start_bot_game).pack(pady=10)
        
        tk.Button(btn_frame, text="🔄 LÀM MỚI", font=("Segoe UI", 10), bg="#16213e", fg="white", width=15,
                 command=lambda: self.send_request({'type': 'get_players'})).pack(pady=5)

    def setup_game_ui(self, mode="pvp"): # mode: pvp or bot
        self.clear_frame()
        opponent_display = self.opponent_name if mode == "pvp" else "MÁY TÍNH 🤖"
        self.root.title(f"Trận đấu: {self.player_name} vs {opponent_display}")
        self.current_mode = mode
        
        # Status Header
        header = tk.Frame(self.main_container, bg="#16213e", pady=10)
        header.pack(fill=tk.X)
        
        tk.Label(header, text=f"{self.player_name}", font=("Segoe UI", 16, "bold"), fg="#00ff88", bg="#16213e").pack(side=tk.LEFT, padx=50)
        
        # Timer Display
        self.timer_label = tk.Label(header, text="10s", font=("Segoe UI", 24, "bold"), fg="#f39c12", bg="#16213e")
        self.timer_label.pack(side=tk.LEFT, expand=True)

        tk.Label(header, text=f"{opponent_display}", font=("Segoe UI", 16, "bold"), fg="#f1c40f", bg="#16213e").pack(side=tk.RIGHT, padx=50)
        
        # Game Area
        game_area = tk.Frame(self.main_container, bg="#1a1a2e")
        game_area.pack(fill=tk.BOTH, expand=True, pady=20)
        
        self.status_label = tk.Label(game_area, text="Hãy chọn nước đi!", font=("Segoe UI", 18), fg="white", bg="#1a1a2e")
        self.status_label.pack(pady=20)
        
        # Choices
        choices_frame = tk.Frame(game_area, bg="#1a1a2e")
        choices_frame.pack(pady=30)
        
        items = [('rock', 'BÚA', '#e74c3c'), ('paper', 'BAO', '#3498db'), ('scissors', 'KÉO', '#f39c12')]
        
        self.choice_btns = []
        for key, name, color in items:
            frame = tk.Frame(choices_frame, bg="#1a1a2e", padx=20)
            frame.pack(side=tk.LEFT)
            
            img = self.images.get(key)
            if img:
                btn = tk.Button(frame, image=img, bg="#1a1a2e", activebackground="#1a1a2e", bd=0,
                               command=lambda k=key: self.make_choice(k))
                btn.image = img
                btn.pack()
            else:
                btn = tk.Button(frame, text=name, font=("Segoe UI", 20, "bold"), bg=color, fg="white", width=8, height=3,
                               command=lambda k=key: self.make_choice(k))
                btn.pack()
            self.choice_btns.append(btn)
            
            tk.Label(frame, text=name, font=("Segoe UI", 14), fg="white", bg="#1a1a2e").pack(pady=10)

        # Leave Button
        tk.Button(self.main_container, text="RỜI TRẬN", font=("Segoe UI", 10, "bold"), bg="#555", fg="white",
                 command=self.leave_game).pack(side=tk.BOTTOM, pady=20)
                 
        # Start Timer
        self.time_left = 10
        self.timer_running = True
        self.update_timer()

    def update_timer(self):
        if not self.timer_running: return
        
        self.timer_label.config(text=f"{self.time_left}s")
        if self.time_left > 0:
            self.time_left -= 1
            self.root.after(1000, self.update_timer)
        else:
            self.timer_running = False
            self.status_label.config(text="Hết giờ! Tự động chọn ngẫu nhiên...", fg="#e74c3c")
            import random
            auto_choice = random.choice(['rock', 'paper', 'scissors'])
            self.make_choice(auto_choice)

    def start_bot_game(self):
        self.setup_game_ui(mode="bot")

    def connect_to_server(self):
        name = self.name_entry.get().strip()
        if not name:
            messagebox.showwarning("Lỗi", "Vui lòng nhập tên!")
            return
            
        try:
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Disable Nagle's algorithm
            self.client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.client_socket.connect((self.host, self.port))
            
            # Start listening thread
            threading.Thread(target=self.listen_to_server, daemon=True).start()
            
            # Send connect
            self.send_request({'type': 'connect', 'player_name': name})
            
        except Exception as e:
            messagebox.showerror("Lỗi kết nối", f"Không thể kết nối đến server: {e}")

    def send_request(self, data):
        if self.client_socket:
            try:
                self.client_socket.send((json.dumps(data) + '\n').encode('utf-8'))
            except Exception as e:
                print(f"Error sending: {e}")

    def listen_to_server(self):
        buffer = ""
        while True:
            try:
                data = self.client_socket.recv(4096).decode('utf-8')
                if not data: 
                    print(f"[CLIENT] No data received (connection closed)")
                    break
                
                buffer += data
                print(f"[CLIENT] Received: {buffer[:100]}")
                
                # Process complete messages (delimited by newline)
                while '\n' in buffer:
                    message_str, buffer = buffer.split('\n', 1)
                    if message_str.strip():
                        try:
                            msg = json.loads(message_str)
                            print(f"[CLIENT] Parsed message: {msg.get('type')}")
                            self.root.after(0, self.handle_message, msg)
                        except json.JSONDecodeError as je:
                            print(f"[CLIENT] Failed to parse message: {je}")
                            # Try to recover from concatenated messages (simple heuristic)
                            if '}{' in message_str:
                                print(f"[CLIENT] Attempting to parse merged messages...")
                                parts = message_str.replace('}{', '}|{').split('|')
                                for part in parts:
                                    try:
                                        msg = json.loads(part)
                                        print(f"[CLIENT] Recovered message: {msg.get('type')}")
                                        self.root.after(0, self.handle_message, msg)
                                    except json.JSONDecodeError:
                                        pass
                        
            except Exception as e:
                print(f"[CLIENT] Connection lost: {e}")
                self.root.after(0, lambda: messagebox.showerror("Mất kết nối", "Đã mất kết nối đến máy chủ"))
                self.root.after(0, self.root.destroy)
                break

    def handle_message(self, msg):
        msg_type = msg.get('type')
        print(f"[CLIENT] Handling message type: {msg_type}")
        
        if msg_type == 'connect_ack':
            self.player_name = msg['name']
            self.setup_lobby_ui()
            
        elif msg_type == 'player_list':
            if hasattr(self, 'player_listbox') and self.player_listbox and self.player_listbox.winfo_exists():
                self.players_data = msg['players'] # Store raw data
                self.player_listbox.delete(0, END)
                for p in msg['players']:
                    display = p['name']
                    if p['name'] == self.player_name:
                        display += " (Bạn)"
                    if p['status'] != 'idle':
                        display += f" [{p['status'].upper()}]"
                    self.player_listbox.insert(END, display)
                    
        elif msg_type == 'challenge_request':
            challenger = msg['challenger']
            if messagebox.askyesno("Thách đấu", f"{challenger} muốn thách đấu với bạn!"):
                self.send_request({'type': 'accept_challenge', 'challenger': challenger, 'accept': True})
            else:
                self.send_request({'type': 'accept_challenge', 'challenger': challenger, 'accept': False})
                
        elif msg_type == 'game_start':
            self.opponent_name = msg['opponent']
            self.setup_game_ui(mode="pvp")
            
        elif msg_type == 'challenge_rejected':
            messagebox.showinfo("Từ chối", f"Người chơi {msg['opponent']} đã từ chối.")

        elif msg_type == 'opponent_choosed':
            print(f"[CLIENT] Opponent has chosen, waiting for result")
            self.status_label.config(text="Đối thủ đã chọn xong! Đến lượt bạn!", fg="#f1c40f")
            
        elif msg_type == 'game_result':
            print(f"[CLIENT] Received game result!")
            self.timer_running = False # Stop timer
            result = msg['result']
            my_move = self.translate(msg['my_choice'])
            opp_move = self.translate(msg['opponent_choice'])
            
            if result == 'win':
                text = f"THẮNG!\nBạn: {my_move}   vs   Địch: {opp_move}"
                text_color = "#00ff88"
            elif result == 'lose':
                text = f"THUA!\nBạn: {my_move}   vs   Địch: {opp_move}"
                text_color = "#e74c3c"
            else:
                text = f"HÒA!\nBạn: {my_move}   vs   Địch: {opp_move}"
                text_color = "#f39c12"
                
            self.status_label.config(text=text, fg=text_color)
            
            # Next round countdown
            self.root.after(3000, self.next_round)
            
        elif msg_type == 'opponent_left':
            messagebox.showinfo("Thông báo", "Đối thủ đã thoát trận.")
            self.setup_lobby_ui()
            
        elif msg_type == 'error':
            messagebox.showerror("Lỗi", msg['message'])

    def next_round(self):
        # Reset UI for next round
        self.status_label.config(text="Ván mới! Hãy chọn tiếp...", fg="white")
        self.time_left = 10
        self.timer_running = True
        self.update_timer()
        # Enable buttons for new round
        for btn in self.choice_btns:
            btn.config(state=tk.NORMAL)

    def challenge_player(self):
        selection = self.player_listbox.curselection()
        if not selection:
            messagebox.showwarning("Chú ý", "Hãy chọn một người chơi!")
            return
            
        target_index = selection[0]
        if target_index < len(self.players_data):
            target_name = self.players_data[target_index]['name']
        else:
            # Fallback (should not happen if synced)
            target_str = self.player_listbox.get(target_index)
            target_name = target_str.split(' ')[0]
        
        if target_name == self.player_name:
            messagebox.showwarning("Chú ý", "Không thể tự thách đấu bản thân!")
            return
            
        self.send_request({'type': 'challenge', 'target_name': target_name})
        self.status_label = tk.Label(self.root, text="Đã gửi lời mời...", bg="#1a1a2e", fg="white") # Temp hint

    def make_choice(self, choice):
        print(f"[CLIENT] Making choice: {choice}")
        self.status_label.config(text="Đã chọn! Đang chờ kết quả...", fg="#3498db")
        self.timer_running = False # Stop timer once chosen waiting for opponent
        
        # Disable buttons to prevent multiple choices
        for btn in self.choice_btns:
            btn.config(state=tk.DISABLED)
            
        req_type = 'play_bot' if self.current_mode == 'bot' else 'play'
        self.send_request({'type': req_type, 'choice': choice})
        print(f"[CLIENT] Sent {req_type} request")

    def leave_game(self):
        if messagebox.askyesno("Thoát", "Bạn muốn rời trận đấu?"):
            self.timer_running = False
            # Send quit signal to server but keep connection
            self.send_request({'type': 'quit_match'})
            self.setup_lobby_ui() 

            
    def translate(self, key):
        return {'rock': 'Búa 🪨', 'paper': 'Bao 📄', 'scissors': 'Kéo ✂️'}.get(key, key)

if __name__ == "__main__":
    root = tk.Tk()
    app = RPSClient(root)
    root.mainloop()
