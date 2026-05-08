import json
import socket
import threading
import time


class GameServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 8765):
        self.host = host
        self.port = port
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.clients = {}
        self.players = {}
        self.next_id = 1
        self.running = False
        self.lock = threading.Lock()
        self.portal_started_at = {0: None, 1: None, 2: None}
        self.next_bullet_id = 1
        self.bullet_events = []

    def start(self):
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(32)
        self.running = True
        print(f"Server läuft auf {self.host}:{self.port}")
        threading.Thread(target=self._broadcast_loop, daemon=True).start()
        try:
            while self.running:
                conn, _addr = self.server_socket.accept()
                threading.Thread(target=self._handle_client, args=(conn,), daemon=True).start()
        finally:
            self.stop()

    def stop(self):
        self.running = False
        try:
            self.server_socket.close()
        except Exception:
            pass
        with self.lock:
            for conn in list(self.clients.keys()):
                try:
                    conn.close()
                except Exception:
                    pass
            self.clients.clear()
            self.players.clear()

    def _send(self, conn, payload):
        data = (json.dumps(payload) + "\n").encode("utf-8")
        conn.sendall(data)

    def _handle_client(self, conn):
        conn.settimeout(0.5)
        player_id = None
        buffer = ""
        try:
            while self.running:
                try:
                    chunk = conn.recv(8192)
                    if not chunk:
                        break
                    buffer += chunk.decode("utf-8")
                except socket.timeout:
                    continue

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    msg = json.loads(line)
                    msg_type = msg.get("type")
                    if msg_type == "hello":
                        with self.lock:
                            player_id = self.next_id
                            self.next_id += 1
                            self.clients[conn] = player_id
                            self.players[player_id] = {
                                "id": player_id,
                                "name": str(msg.get("name", f"User{player_id}")),
                                "x": 0.0,
                                "y": 0.0,
                                "health": 0.0,
                                "wave": 1,
                                "state": "menu",
                                "in_portal": False,
                                "portal_index": -1,
                                "dead": False,
                            }
                        self._send(conn, {"type": "welcome", "id": player_id})
                    elif msg_type == "state" and player_id is not None:
                        with self.lock:
                            player = self.players.get(player_id)
                            if player:
                                player["x"] = float(msg.get("x", player["x"]))
                                player["y"] = float(msg.get("y", player["y"]))
                                player["health"] = float(msg.get("health", player["health"]))
                                player["wave"] = int(msg.get("wave", player["wave"]))
                                player["state"] = str(msg.get("state", player["state"]))
                                player["in_portal"] = bool(msg.get("in_portal", player["in_portal"]))
                                player["portal_index"] = int(msg.get("portal_index", player["portal_index"]))
                                player["dead"] = bool(msg.get("dead", player["dead"]))
                    elif msg_type == "shot" and player_id is not None:
                        with self.lock:
                            shot = {
                                "id": self.next_bullet_id,
                                "owner_id": player_id,
                                "x": float(msg.get("x", 0.0)),
                                "y": float(msg.get("y", 0.0)),
                                "vx": float(msg.get("vx", 0.0)),
                                "vy": float(msg.get("vy", 0.0)),
                                "t0": time.time(),
                                "ttl": float(msg.get("ttl", 1.2)),
                            }
                            self.next_bullet_id += 1
                            self.bullet_events.append(shot)
                    elif msg_type == "revive" and player_id is not None:
                        with self.lock:
                            target_id = int(msg.get("target_id", -1))
                            target = self.players.get(target_id)
                            if target:
                                target["dead"] = False
                                target["health"] = max(1.0, float(target.get("health", 1.0)))
        except Exception:
            pass
        finally:
            with self.lock:
                if conn in self.clients:
                    pid = self.clients.pop(conn)
                    self.players.pop(pid, None)
            try:
                conn.close()
            except Exception:
                pass

    def _broadcast_loop(self):
        while self.running:
            with self.lock:
                players = list(self.players.values())
                targets = list(self.clients.keys())
                now = time.time()

                # Portal occupancy and shared countdown.
                portal_counts = {0: 0, 1: 0, 2: 0}
                for player in players:
                    if player.get("state") == "lobby" and player.get("in_portal"):
                        portal_idx = int(player.get("portal_index", -1))
                        if portal_idx in portal_counts:
                            portal_counts[portal_idx] += 1
                portal_data = {}
                for idx in (0, 1, 2):
                    count = portal_counts[idx]
                    started = self.portal_started_at[idx]
                    if count > 0 and started is None:
                        started = now
                        self.portal_started_at[idx] = started
                    if count == 0:
                        self.portal_started_at[idx] = None
                        started = None
                    if started is None:
                        remaining = 10.0
                        ready = False
                    else:
                        remaining = max(0.0, 10.0 - (now - started))
                        ready = remaining <= 0.0
                    portal_data[idx] = {"count": count, "remaining": remaining, "ready": ready}

                # Keep only live bullet events.
                self.bullet_events = [b for b in self.bullet_events if (now - b["t0"]) <= b["ttl"]]
                bullets = list(self.bullet_events)

            packet = {"type": "snapshot", "players": players, "portals": portal_data, "bullets": bullets}
            for conn in targets:
                try:
                    self._send(conn, packet)
                except Exception:
                    pass
            time.sleep(0.05)


if __name__ == "__main__":
    GameServer().start()
