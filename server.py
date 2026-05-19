import json
import socket
import threading
import time
from pathlib import Path


class GameServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 8765, join_token: str = ""):
        self.host = host
        self.port = port
        self.join_token = join_token
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
        self.names_file = Path(__file__).resolve().parent / "Namen.txt"
        self.bound_names = self._load_bound_names()

    def start(self):
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(32)
        self.running = True
        print(f"Server läuft auf {self.host}:{self.port}")
        threading.Thread(target=self._broadcast_loop, daemon=True).start()
        try:
            while self.running:
                conn, _addr = self.server_socket.accept()
                threading.Thread(target=self._handle_client, args=(conn, _addr), daemon=True).start()
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

    def _load_bound_names(self):
        result = {}
        if not self.names_file.exists():
            return result
        try:
            for raw in self.names_file.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line:
                    continue
                parts = line.rsplit(" ", 1)
                if len(parts) != 2:
                    continue
                name, ip = parts[0].strip(), parts[1].strip()
                if name and ip:
                    result[ip] = name
        except Exception:
            return {}
        return result

    def _save_bound_names(self):
        try:
            # Persistiere nur angemeldete, feste Name<->IP-Bindungen.
            lines = sorted(f"{name} {ip}" for ip, name in self.bound_names.items())
            self.names_file.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        except Exception:
            pass

    def _name_taken_by_other_ip(self, name: str, ip: str) -> bool:
        lname = name.casefold()
        for existing_ip, existing_name in self.bound_names.items():
            if existing_ip != ip and existing_name.casefold() == lname:
                return True
        return False

    def _handle_client(self, conn, addr):
        conn.settimeout(0.5)
        player_id = None
        client_ip = str(addr[0]) if addr else "0.0.0.0"
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
                        if self.join_token and str(msg.get("token", "")) != self.join_token:
                            self._send(conn, {"type": "error", "message": "invalid_token"})
                            try:
                                conn.close()
                            except Exception:
                                pass
                            return
                        requested_name = str(msg.get("name", "")).strip()
                        if requested_name.casefold() == "spieler":
                            requested_name = ""
                        is_guest = bool(msg.get("guest", False)) or not requested_name
                        with self.lock:
                            fixed_name = self.bound_names.get(client_ip, "")
                            if not fixed_name:
                                # Nur echte Anmeldung bindet Name an IP und schreibt Namen.txt.
                                if is_guest:
                                    fixed_name = requested_name if requested_name else f"Gast{self.next_id}"
                                else:
                                    if not requested_name:
                                        self._send(conn, {"type": "error", "message": "name_required"})
                                        try:
                                            conn.close()
                                        except Exception:
                                            pass
                                        return
                                    if self._name_taken_by_other_ip(requested_name, client_ip):
                                        self._send(conn, {"type": "error", "message": "name_taken"})
                                        try:
                                            conn.close()
                                        except Exception:
                                            pass
                                        return
                                    fixed_name = requested_name
                                    self.bound_names[client_ip] = fixed_name
                                    self._save_bound_names()
                            elif is_guest:
                                # Bereits registrierte IP bleibt immer auf festem Namen.
                                pass
                            player_id = self.next_id
                            self.next_id += 1
                            self.clients[conn] = player_id
                            self.players[player_id] = {
                                "id": player_id,
                                "name": fixed_name,
                                "x": 0.0,
                                "y": 0.0,
                                "health": 0.0,
                                "wave": 1,
                                "state": "menu",
                                "in_portal": False,
                                "portal_index": -1,
                                "dead": False,
                                "ip": client_ip,
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
                    elif msg_type == "register_name" and player_id is not None:
                        requested_name = str(msg.get("name", "")).strip()
                        if not requested_name or requested_name.casefold() == "spieler":
                            continue
                        with self.lock:
                            if self._name_taken_by_other_ip(requested_name, client_ip):
                                self._send(conn, {"type": "error", "message": "name_taken"})
                                continue
                            fixed_name = self.bound_names.get(client_ip)
                            if fixed_name is None:
                                self.bound_names[client_ip] = requested_name
                                fixed_name = requested_name
                                self._save_bound_names()
                            player = self.players.get(player_id)
                            if player:
                                player["name"] = fixed_name
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
