from pathlib import Path

import arcade
import json
import math
import random
import socket
import threading
import time

# ---------------- SETTINGS ----------------
SCREEN_TITLE = "Survival Map"
SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080
MAP_WIDTH = 3600
MAP_HEIGHT = 3600
LOBBY_WIDTH = 4400
LOBBY_HEIGHT = 4400
ASSET_BASE = Path(__file__).resolve().parent / "assets"
if not ASSET_BASE.exists():
    ASSET_BASE = Path(__file__).resolve().parent
IMG_DIR = ASSET_BASE
SOUND_DIR = ASSET_BASE

PLAYER_WIDTH = 180
PLAYER_HEIGHT = 240
PLAYER_SPEED = 145 + (100 / 60) + 50 + 100 + 300 + 120

SPAWN_INTERVAL = 3.0
WAVE_DURATION = 30

ENEMY_SPEED = 95 + (100 / 60) + 50 + 100 + 300 + 120
MINIMAP_SCALE = 0.05

SHOT_RADIUS = 500
PORTAL_COOLDOWN = 0.4
AMMO_COST = 2
SPAWN_PREVIEW_DURATION = 1.0
SMOKE_BORDER_THICKNESS = 160
SMOKE_DAMAGE_PER_SECOND = 5.0


class OnlineClient:
    def __init__(self, host: str, port: int, name: str, token: str = ""):
        self.host = host
        self.port = port
        self.name = name
        self.token = token
        self.player_id = None
        self.connected = False
        self._sock = None
        self._lock = threading.Lock()
        self._snapshot = {}
        self.last_error = ""
        self._running = False
        self._recv_thread = None

    def connect(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.connect((self.host, self.port))
        self._sock.settimeout(0.5)
        self.connected = True
        self._running = True
        self._send({"type": "hello", "name": self.name, "token": self.token})
        self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._recv_thread.start()

    def close(self):
        self._running = False
        self.connected = False
        try:
            if self._sock:
                self._sock.close()
        except Exception:
            pass
        self._sock = None

    def _send(self, payload):
        if not self._sock:
            return
        data = (json.dumps(payload) + "\n").encode("utf-8")
        try:
            self._sock.sendall(data)
        except Exception:
            self.connected = False

    def send_state(self, x: float, y: float, health: float, wave: int, state: str, in_portal: bool, portal_index: int, dead: bool):
        if not self.connected:
            return
        self._send({
            "type": "state",
            "x": x,
            "y": y,
            "health": health,
            "wave": wave,
            "state": state,
            "in_portal": in_portal,
            "portal_index": portal_index,
            "dead": dead,
        })

    def send_shot(self, x: float, y: float, vx: float, vy: float, ttl: float = 1.2):
        if not self.connected:
            return
        self._send({"type": "shot", "x": x, "y": y, "vx": vx, "vy": vy, "ttl": ttl})

    def send_name(self, name: str):
        if not self.connected:
            return
        self._send({"type": "set_name", "name": name})

    def _recv_loop(self):
        buffer = ""
        while self._running and self._sock:
            try:
                chunk = self._sock.recv(8192)
                if not chunk:
                    self.connected = False
                    break
                buffer += chunk.decode("utf-8")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    msg = json.loads(line)
                    if msg.get("type") == "welcome":
                        self.player_id = msg.get("id")
                    elif msg.get("type") == "error":
                        self.last_error = str(msg.get("message", "error"))
                        self.connected = False
                        try:
                            self._sock.close()
                        except Exception:
                            pass
                        break
                    elif msg.get("type") == "snapshot":
                        with self._lock:
                            self._snapshot = msg
            except socket.timeout:
                continue
            except Exception:
                self.connected = False
                break

    def get_snapshot(self):
        with self._lock:
            return dict(self._snapshot)


class Enemy(arcade.Sprite):
    def __init__(self, image: str):
        super().__init__(image, scale=0.5)
        self.base_speed = ENEMY_SPEED
        self.hit_points = 1
        self.max_hit_points = 1
        self.enemy_type = 1
        self.gem_reward = 10
        self.touch_damage = 10
        self.final_texture = None
        self.final_scale = 0.25
        self.is_dying = False
        self.death_timer = 0.0
        self.is_spawning = False
        self.spawn_timer = 0.0

class SurvivalGame(arcade.Window):

    def __init__(self, online_client: OnlineClient | None = None):
        super().__init__(SCREEN_WIDTH, SCREEN_HEIGHT, SCREEN_TITLE, fullscreen=False, resizable=True)
        # Fluesig, aber stabil (zu hohe Update-Rates erzeugen eher Ruckler/CPU-Last).
        self.set_update_rate(1/240)
        arcade.set_background_color(arcade.color.DARK_GREEN)

        self.state = "menu"
        self.camera = arcade.Camera2D()
        self.camera_zoom = 0.30
        try:
            self.camera.zoom = self.camera_zoom
        except Exception:
            pass
        self.keys = set()
        self.online_client = online_client
        self.remote_players = []
        self.remote_bullets = []
        self.remote_bullet_seen = set()
        self.remote_portals = {}
        self.is_downed = False
        self.respawn_timer = 0.0

        self.wave_active = False
        self.wave_timer = 0
        self.spawn_timer = 0
        self.wave_number = 1
        self.current_spawn_interval = SPAWN_INTERVAL
        self.current_enemy_speed = ENEMY_SPEED
        self.wave_completed = False
        self.wave_started_once = False
        self.spawn_cycles_per_wave = 0
        self.spawn_cycles_done = 0
        self.wave_spawn_goal = 0
        self.wave_spawned_total = 0
        self.show_minimap = False
        self.wave_message = ""
        self.wave_message_timer = 0.0
        self.controls_hint_timer = 0.0
        self.wave_kills = 0
        self.wave_lives_lost = 0
        self.wave_reward_coins = 0
        self.total_coins = 50
        self.portal_cooldown_timer = 0.0
        self.ui_rects = {}
        self.gems = 50
        self.total_enemy_kills = 0
        self.mouse_x = 0
        self.mouse_y = 0
        self.last_menu_click_handled_at = 0.0
        self.admin_focus = False
        self.admin_message = ""
        self.admin_message_timer = 0.0
        self.caret_timer = 0.0
        self.caret_visible = True
        self.settings_unlocked = False
        self.hover_level = {}
        self.hover_velocity = {}
        self.text_cache = {}
        self.auto_shot_owned = False
        self.auto_shot_cooldown = 0.0
        self.weapon_shot_cooldown = 0.0
        self.weapon_hold_timer = 0.0
        self.mouse_hold_initial_delay = 0.18
        self.mouse_hold_repeat_delay = 0.05
        self.mouse_left_down = False
        self.weapon_level = 1
        self.wave_auto_timer = 5.0
        self.player_health_max = 200
        self.player_damage_cooldown = 0.0
        self.smoke_damage_acc = 0.0
        self.health_upgrade_count = 0
        self.player_name = ""
        self.name_confirmed = False
        self.menu_mode = "name"
        self.menu_focus_field = "name"
        self.lobby_wait_time = 10.0
        self.lobby_timer = self.lobby_wait_time
        self.lobby_active_circle = -1
        self.lobby_circles = []
        self.bullet_list = arcade.SpriteList()
        self.bullet_texture = None  # wird nicht mehr benutzt
        self.pistol_texture = arcade.load_texture(str(IMG_DIR / "pistole.png"))
        self.enemy_texture = arcade.load_texture(str(IMG_DIR / "gegner.png"))
        self.enemy2_texture = arcade.load_texture(str(IMG_DIR / "gegner2.png"))
        self.enemy3_texture = arcade.load_texture(str(IMG_DIR / "gegner3.png"))
        self.spawn_hole_texture = arcade.load_texture(str(IMG_DIR / "loch.png"))
        self.spawn_hole2_texture = arcade.load_texture(str(IMG_DIR / "loch2.png"))
        self.spawn_hole3_texture = arcade.load_texture(str(IMG_DIR / "loch3.png"))
        self.teleporter_texture = arcade.load_texture(str(IMG_DIR / "teleporter.png"))
        self.smoke_texture = arcade.load_texture(str(IMG_DIR / "Rauch.png"))
        self.player_texture_armed = arcade.load_texture(str(IMG_DIR / "spieler.png"))
        self.player_texture_unarmed = arcade.load_texture(str(IMG_DIR / "spielerB.png"))
        self.remote_player_texture = arcade.load_texture(str(IMG_DIR / "spieler.png"))
        self.player_scale_armed = 0.4
        self.player_scale_unarmed = 0.4
        self.pistol_icon_sprite = arcade.Sprite(str(IMG_DIR / "pistole.png"), scale=0.6)
        self.pistol_icon_list = arcade.SpriteList()
        self.pistol_icon_list.append(self.pistol_icon_sprite)
        self.upgrade_icon_sprite = arcade.Sprite(str(IMG_DIR / "pistole.png"), scale=0.7)
        self.upgrade_icon_list = arcade.SpriteList()
        self.upgrade_icon_list.append(self.upgrade_icon_sprite)
        self.weapon_equipped = True
        self.wave_auto_timer = 5.0
        self.house_upgrades_on = False

        self.player_health = self.player_health_max
        self.shots_left = float("inf")
        self.energy = 100.0
        self.sprint_drain_acc = 0.0
        self.last_energy_int = int(self.energy)

        self.start_button = None
        self.wave_button = None
        self.shop_return_button = None
        self.shop_buy_one_button = None
        self.hit_sound = None
        self.bg_sound = None
        self.bg_player = None
        self.prep_sound = None
        self.prep_player = None

        self.shop_sound = None
        self.shop_enter_sound = None
        self.shop_enter_player = None
        self.shop_sound_player = None
        self.bg_player = None
        self.cached_energy_cost = None
        self.info_sprite = None
        self.info_sprite_list = None
        self.settings_sprite = None
        self.settings_sprite_list = None
        self.win_sound = None

        # Cached UI text metrics so buttons don't stutter from per-frame Text creation.
        self.shop_buy_one_label = f"🔫 Kaufe 1   Preis: {AMMO_COST} 🪙"
        self.shop_leave_label = "Verlassen"
        self._ui_dirty = True
        self.update_ui_rects()

        self.setup_game()
        # Name kann vom Client vorbefüllt werden, Auswahl bleibt aber im Startmenü.
        if self.online_client and self.online_client.name:
            self.player_name = self.online_client.name
        if self.player_name.strip().lower() == "spieler":
            self.player_name = ""
        self.name_confirmed = False
        self.menu_mode = "name"
        self.menu_focus_field = "name"
        self.state = "menu"

    # ---------------- SETUP ----------------
    def setup_game(self):
        self.player_list = arcade.SpriteList()
        self.enemies = arcade.SpriteList()
        self.spawner_list = arcade.SpriteList()
        self.portal_list = arcade.SpriteList()
        self.decor_list = arcade.SpriteList()

        self.house_sprite = None

        self.weapon_equipped = True
        self.player = arcade.Sprite(str(IMG_DIR / "spielerB.png"), scale=self.player_scale_unarmed)
        self.player.center_x = 0
        self.player.center_y = 0
        self.player_list.append(self.player)
        self.prev_player_pos = (self.player.center_x, self.player.center_y)
        self.isch_sprite = None
        self.weapon_level = 1
        self.weapon_upgraded = False
        self.weapon_shot_cooldown = 0.0
        self.weapon_hold_timer = 0.0
        self.mouse_left_down = False

        self.player_health = self.player_health_max
        self.player_damage_cooldown = 0.0
        self.smoke_damage_acc = 0.0
        self.health_upgrade_count = 0
        self.shots_left = float("inf")
        self.energy = 100.0
        self.sprint_drain_acc = 0.0
        self.last_energy_int = int(self.energy)
        self.portal_x = 0
        self.portal_y = MAP_HEIGHT // 2 - 220
        self.portal_sprite = None  # portal.png entfernt

        # Spawner entfallen; Gegner werden zufällig am Kartenrand erzeugt
        self.spawners = []
        self.house_health_max = 0
        self.house_health = 0
        self.house_destroyed = True

        self.wave_active = False
        self.wave_timer = 0
        self.spawn_timer = 0
        self.wave_number = 1
        self.current_spawn_interval = SPAWN_INTERVAL
        self.current_enemy_speed = ENEMY_SPEED
        self.wave_completed = False
        self.wave_started_once = False
        self.spawn_cycles_per_wave = 0
        self.spawn_cycles_done = 0
        self.wave_spawn_goal = 0
        self.wave_spawned_total = 0
        self.show_minimap = False
        self.wave_message = ""
        self.wave_message_timer = 0.0
        self.controls_hint_timer = 0.0
        self.wave_kills = 0
        self.wave_lives_lost = 0
        self.wave_reward_coins = 0
        self.total_coins = 0
        self.total_enemy_kills = 0
        self.portal_cooldown_timer = 0.0
        self.ui_rects = {}
        self.lobby_timer = self.lobby_wait_time
        self.lobby_active_circle = -1
        self.lobby_circles = []

    # ---------------- INPUT ----------------
    def on_key_press(self, key, modifiers):
        self.keys.add(key)

        if self.state == "settings":
            if key == arcade.key.ENTER or key == arcade.key.RETURN:
                if self.admin_input.strip() == "fauli!":
                    self.admin_message = ""
                    self.admin_message_timer = 0.0
                    self.settings_unlocked = True
                else:
                    self.admin_message = "Falscher Code"
                    self.admin_message_timer = 2.0
                return
            if not self.admin_focus:
                return
            if key == arcade.key.BACKSPACE:
                self.admin_input = self.admin_input[:-1]
                return
        if self.state == "menu":
            if key == arcade.key.ENTER or key == arcade.key.RETURN:
                self._submit_name_and_start()
                return
            if key == arcade.key.BACKSPACE:
                self.player_name = self.player_name[:-1]
                self.name_confirmed = False
                return
        if self.state == "game":
            if key == arcade.key.KEY_1:
                self.weapon_equipped = not self.weapon_equipped
                if self.weapon_equipped:
                    self.player.texture = self.player_texture_armed
                    self.player.scale = self.player_scale_armed
                else:
                    self.player.texture = self.player_texture_unarmed
                    self.player.scale = self.player_scale_unarmed
        elif self.state == "shop":
            if key == arcade.key.ESCAPE:
                self.leave_shop()

    def on_key_release(self, key, modifiers):
        self.keys.discard(key)

    def on_mouse_motion(self, x: float, y: float, dx: float, dy: float):
        self.mouse_x = x
        self.mouse_y = y
        self.ensure_ui_rects()

    def point_in_rect(self, x, y, rect, padding=0):
        bx, by, bw, bh = rect
        return (bx - padding) <= x <= (bx + bw + padding) and (by - padding) <= y <= (by + bh + padding)

    def point_on_sprite(self, x, y, sprite, padding=0):
        if sprite is None:
            return False
        left = sprite.center_x - sprite.width / 2 - padding
        right = sprite.center_x + sprite.width / 2 + padding
        bottom = sprite.center_y - sprite.height / 2 - padding
        top = sprite.center_y + sprite.height / 2 + padding
        return left <= x <= right and bottom <= y <= top

    def point_on_tisch(self, x, y):
        if self.isch_sprite is None:
            return False
        try:
            if self.isch_sprite.collides_with_point((x, y)):
                return True
        except Exception:
            pass

        # Fallback: an die sichtbare Schmiede angepasst, rechts leicht erweitert.
        half_w = self.isch_sprite.width * 0.40
        half_h = self.isch_sprite.height * 0.24
        center_x = self.isch_sprite.center_x + self.isch_sprite.width * 0.03
        center_y = self.isch_sprite.center_y - self.isch_sprite.height * 0.02
        return (center_x - half_w) <= x <= (center_x + half_w) and (center_y - half_h) <= y <= (center_y + half_h)

    def change_zoom(self, delta):
        return
        try:
            self.camera.zoom = self.camera_zoom
        except Exception:
            pass

    def get_weapon_upgrade_cost(self):
        costs = [150, 750, 2500]
        if 1 <= self.weapon_level <= len(costs):
            return costs[self.weapon_level - 1]
        return None

    def get_health_upgrade_cost(self):
        base_cost = 200
        return int(round(base_cost * (1.35 ** self.health_upgrade_count)))

    def get_weapon_cooldown(self):
        if self.weapon_level == 1:
            return 0.5
        if self.weapon_level == 2:
            return 0.3
        if self.weapon_level == 3:
            return 0.05
        return 0.05

    def get_weapon_status_text(self):
        if self.weapon_level == 1:
            return "1 Schuss, 0.5s Cooldown"
        if self.weapon_level == 2:
            return "3 Schüsse, 0.3s Cooldown"
        if self.weapon_level == 3:
            return "1 Schuss, 0.75s Cooldown"
        if self.weapon_level == 4:
            return "3 Schüsse, kein Cooldown"
        return "3 Schüsse, halten für Dauerfeuer"

    def get_weapon_level_label(self):
        if self.weapon_level == 1:
            return "Pistole"
        if self.weapon_level == 2:
            return "Kampfflinte"
        if self.weapon_level == 3:
            return "AK-47"
        if self.weapon_level == 4:
            return "Minigun"
        return "Minigun"

    def get_next_weapon_name(self):
        if self.weapon_level == 1:
            return "Kampfflinte"
        if self.weapon_level == 2:
            return "AK-47"
        if self.weapon_level == 3:
            return "Minigun"
        if self.weapon_level == 4:
            return ""

    def _handle_click(self, x, y, button):
        self.ensure_ui_rects()
        self.mouse_x = x
        self.mouse_y = y

        if self.state == "menu":
            name_rect = self.ui_rects["menu_name_field"]
            play_rect = self.ui_rects["menu_login_play"]
            if self.point_in_rect(x, y, play_rect, padding=80):
                self._submit_name_and_start()
                return True
            if self.point_in_rect(x, y, name_rect, padding=30):
                self.menu_focus_field = "name"
                return True
            return True

        elif self.state == "lobby":
            bx, by, bw, bh = self.ui_rects.get("lobby_leave", (0, 0, 0, 0))
            if self.lobby_active_circle >= 0 and self.point_in_rect(x, y, (bx, by, bw, bh), padding=20):
                self.lobby_active_circle = -1
                self.lobby_timer = self.lobby_wait_time
                self.player.center_x = 0
                self.player.center_y = -LOBBY_HEIGHT / 2 + 40
                return True
            return True

        elif self.state == "game":
            if self.is_downed:
                return True

            weapon_cost = self.get_weapon_upgrade_cost()
            weapon_rect = self.ui_rects["upgrade_panel_weapon"]
            health_rect = self.ui_rects["upgrade_panel_health"]
            auto_rect = self.ui_rects["upgrade_panel_auto"]
            if self.point_in_rect(x, y, weapon_rect):
                if weapon_cost is not None and self.gems >= weapon_cost:
                    self.gems -= weapon_cost
                    self.weapon_level += 1
                    self.weapon_upgraded = self.weapon_level > 1
                return True
            if self.point_in_rect(x, y, health_rect):
                health_cost = self.get_health_upgrade_cost()
                if self.gems >= health_cost:
                    self.buy_health_upgrade()
                return True
            if self.point_in_rect(x, y, auto_rect):
                self.buy_auto_shot()
                return True
            if self.point_in_rect(x, y, self.ui_rects["upgrade_panel_window"]):
                return True

            if button == arcade.MOUSE_BUTTON_LEFT:
                self.fire_bullet(x, y)
                return True

        elif self.state == "settings":
            # Eingabefeld Fokus setzen
            ibx, iby, ibw, ibh = (self.width / 2 - 250, self.height - 300, 500, 60)
            if ibx <= x <= ibx + ibw and iby <= y <= iby + ibh:
                self.admin_focus = True
            else:
                self.admin_focus = False

            # Settings-Fenster deaktiviert – keine Interaktion
            return True

        elif self.state == "shop":
            bx, by, bw, bh = self.ui_rects["shop_leave"]
            if self.point_in_rect(x, y, (bx, by, bw, bh)):
                self.leave_shop()
                return True

            bx, by, bw, bh = self.ui_rects["shop_buy_one"]
            if self.point_in_rect(x, y, (bx, by, bw, bh)):
                self.buy_ammo(1)
                return True

            bx, by, bw, bh = self.ui_rects["shop_energy"]
            if self.point_in_rect(x, y, (bx, by, bw, bh)):
                self.buy_energy()
                return True

            bx, by, bw, bh = self.ui_rects["shop_auto"]
            if self.point_in_rect(x, y, (bx, by, bw, bh)):
                self.buy_auto_shot()
                return True

        elif self.state == "gameover":
            bx, by, bw, bh = self.ui_rects["gameover_restart"]
            if self.point_in_rect(x, y, (bx, by, bw, bh)):
                self.stop_bg()
                self.stop_shop_sound()
                self.stop_prep()
                self.setup_game()
                self.state = "lobby"
                self.lobby_timer = self.lobby_wait_time
                self.lobby_active_circle = -1
                return True
            return True

        return False

    def on_mouse_press(self, x, y, button, modifiers):
        if button == arcade.MOUSE_BUTTON_LEFT:
            # Hold-Fire nur im Spielzustand aktivieren, nie in Menüs.
            self.mouse_left_down = (self.state == "game")
            # Beim ersten Klick sofort einmal auslösen; Hold-Fire startet erst
            # nach kurzer Verzögerung, damit kein ungewollter Doppel-Schuss entsteht.
            handled = self._handle_click(x, y, button)
            if handled and self.state == "menu":
                self.last_menu_click_handled_at = time.time()
            if handled and self.state == "game":
                self.weapon_hold_timer = max(self.weapon_hold_timer, self.mouse_hold_initial_delay)
            return handled
        return self._handle_click(x, y, button)

    def on_mouse_release(self, x, y, button, modifiers):
        # Klicks nur auf mouse_press verarbeiten: kein zweiter Auslöser.
        if button == arcade.MOUSE_BUTTON_LEFT:
            self.mouse_left_down = False
        return True

    def on_text(self, text: str):
        if self.state == "settings" and self.admin_focus:
            if text and text.isprintable():
                self.admin_input += text
        if self.state == "menu":
            if self.name_confirmed:
                return
            if text and text.isprintable():
                if len(self.player_name) < 16:
                    self.player_name += text
                    self.name_confirmed = False

    # ---------------- RADIUS SHOT ----------------
    def radius_shot(self):
        # Radialschuss deaktiviert
        return

    def get_wave_button_rect(self):
        return (0, 0, 0, 0)  # Wave-Button deaktiviert/unsichtbar

    def get_shop_leave_button_rect(self):
        text_obj = arcade.Text(self.shop_leave_label, 0, 0, arcade.color.WHITE, 26, anchor_x="center", anchor_y="center")
        bw = text_obj.content_width + 140
        bh = text_obj.content_height + 50
        bx = self.width / 2 - bw / 2
        by = 120
        return (bx, by, bw, bh)

    def get_shop_buy_one_button_rect(self):
        text_obj = arcade.Text(self.shop_buy_one_label, 0, 0, arcade.color.WHITE, 24, anchor_x="center", anchor_y="center")
        bw = text_obj.content_width + 100
        bh = text_obj.content_height + 42
        bx = self.width / 2 - bw / 2
        by = self.height - 400
        return (bx, by, bw, bh)

    def get_shop_energy_button_rect(self):
        label = "⚡ Energie +5% auffüllen"
        text_obj = arcade.Text(label, 0, 0, arcade.color.WHITE, 24, anchor_x="center", anchor_y="center")
        bw = text_obj.content_width + 100
        bh = text_obj.content_height + 42
        bx = self.width / 2 - bw / 2
        by = self.height - 480
        return (bx, by, bw, bh)

    def get_shop_auto_button_rect(self):
        label = "🤖 Auto-Schuss  Preis: 100"
        text_obj = arcade.Text(label, 0, 0, arcade.color.WHITE, 24, anchor_x="center", anchor_y="center")
        bw = text_obj.content_width + 120
        bh = text_obj.content_height + 42
        bx = self.width / 2 - bw / 2
        by = self.height - 560
        return (bx, by, bw, bh)


    def buy_ammo(self, amount):
        if amount <= 0:
            return
        cost = amount * AMMO_COST
        if self.total_coins < cost:
            return
        self.total_coins -= cost
        self.shots_left += amount

    def buy_energy(self):
        missing = max(0, 100 - int(self.energy))
        if missing <= 0:
            self.cached_energy_cost = None
            return
        add_amount = min(5, missing)
        cost = add_amount * 5
        if self.total_coins < cost:
            return
        self.total_coins -= cost
        self.energy = min(100.0, self.energy + add_amount)
        self.cached_energy_cost = None
        self.compute_shop_rects()

    def buy_auto_shot(self):
        if self.auto_shot_owned or self.gems < 500:
            return
        self.gems -= 500
        self.auto_shot_owned = True
        self.auto_shot_cooldown = 0.0

    def buy_health_upgrade(self):
        cost = self.get_health_upgrade_cost()
        if self.gems < cost:
            return
        self.gems -= cost
        self.health_upgrade_count += 1
        self.player_health_max += 20
        self.player_health = min(self.player_health_max, self.player_health + 20)

    def start_bg(self):
        return

    def stop_bg(self):
        self.bg_player = None

    def start_prep(self):
        self.wave_auto_timer = 5.0

    def stop_prep(self):
        self.prep_player = None

    def start_shop_sound(self):
        return

    def stop_shop_sound(self):
        self.shop_sound_player = None
        self.shop_enter_player = None

    def ensure_ui_rects(self):
        if self._ui_dirty or not self.ui_rects:
            self.update_ui_rects()

    @staticmethod
    def lerp_color(c1, c2, t: float):
        return (
            int(c1[0] + (c2[0] - c1[0]) * t),
            int(c1[1] + (c2[1] - c1[1]) * t),
            int(c1[2] + (c2[2] - c1[2]) * t),
        )

    @staticmethod
    def draw_scaled_rect(bx, by, bw, bh, color, level, scale_factor=0.08):
        e = SurvivalGame.ease(level)
        # zusätzliches sanftes Overshoot für lebendige Buttons
        overshoot = 0.02 * e
        scale = 1.0 + scale_factor * e + overshoot
        cx = bx + bw / 2
        cy = by + bh / 2
        dw = bw * scale
        dh = bh * scale
        arcade.draw_lbwh_rectangle_filled(cx - dw / 2, cy - dh / 2, dw, dh, color)

    @staticmethod
    def ease(level: float) -> float:
        # Smoothstep easing for softer animation
        return level * level * (3 - 2 * level)

    def is_hover(self, key: str, x: float = None, y: float = None) -> bool:
        if x is None:
            x = self.mouse_x
        if y is None:
            y = self.mouse_y
        rect = self.ui_rects.get(key)
        if not rect:
            return False
        bx, by, bw, bh = rect
        return bx <= x <= bx + bw and by <= y <= by + bh

    def update_ui_rects(self):
        # Menu
        bw, bh = 360, 100
        bx = self.width // 2 - bw // 2
        by = self.height // 2 - bh // 2
        self.ui_rects["start_button"] = (bx, by, bw, bh)
        field_w = 520
        field_h = 60
        field_x = self.width / 2 - field_w / 2
        self.ui_rects["menu_name_field"] = (field_x, self.height / 2 - 140, field_w, field_h)
        self.ui_rects["menu_login_play"] = (self.width / 2 - 180, self.height / 2 - 20, 360, 90)

        # Game
        self.ui_rects["wave_button"] = self.get_wave_button_rect()
        self.ui_rects["prep_upgrade"] = (0, 0, 0, 0)
        self.ui_rects["info_button"] = (0, 0, 0, 0)
        panel_x = 20
        panel_y = self.height - 240
        panel_w = 340
        panel_h = 250
        box_h = 58
        inner_x = panel_x + 14
        inner_w = panel_w - 28
        weapon_box_y = panel_y + 160
        health_box_y = panel_y + 96
        auto_box_y = panel_y + 32
        self.ui_rects["upgrade_panel_window"] = (panel_x, panel_y, panel_w, panel_h)
        self.ui_rects["upgrade_panel_weapon"] = (inner_x, weapon_box_y, inner_w, box_h)
        self.ui_rects["upgrade_panel_health"] = (inner_x, health_box_y, inner_w, box_h)
        self.ui_rects["upgrade_panel_auto"] = (inner_x, auto_box_y, inner_w, box_h)
        self.ui_rects["upgrade_panel_targeter"] = (0, 0, 0, 0)
        # Settings deaktiviert, aber KeyError vermeiden
        self.ui_rects["settings_button"] = (0, 0, 0, 0)
        self.ui_rects["upgrade_close"] = (0, 0, 0, 0)
        self.ui_rects["upgrade_buy"] = (0, 0, 0, 0)
        self.ui_rects["upgrade_targeter"] = (0, 0, 0, 0)
        # Haus-Upgrades-Schalter deaktiviert
        self.ui_rects["house_upgrades"] = (0, 0, 0, 0)

        self.ui_rects["info_back"] = (0, 0, 0, 0)
        self.ui_rects["settings_back"] = (self.width - 220, self.height - 90, 200, 60)
        self.ui_rects["gameover_restart"] = (self.width / 2 - 140, self.height / 2 - 120, 280, 80)
        # Admin-Buttons (Settings unlocked)
        center_x = self.width / 2
        base_y = self.height - 360
        bw = 420
        bh = 60
        self.ui_rects["settings_ammo"] = (center_x - bw/2, base_y, bw, bh)
        self.ui_rects["settings_health"] = (center_x - bw/2, base_y - 80, bw, bh)
        self.ui_rects["settings_energy"] = (center_x - bw/2, base_y - 160, bw, bh)
        self.ui_rects["settings_coins"] = (center_x - bw/2, base_y - 240, bw, bh)

        # Shop
        self.ui_rects["shop_buy_one"] = self.get_shop_buy_one_button_rect()
        self.ui_rects["shop_energy"] = self.get_shop_energy_button_rect()
        self.ui_rects["shop_auto"] = self.get_shop_auto_button_rect()
        self.ui_rects["shop_leave"] = self.get_shop_leave_button_rect()
        self.cached_energy_cost = None
        self._ui_dirty = False
        self.compute_shop_rects()

    def compute_shop_rects(self):
        # buy-one Button: statisch, nur anlegen falls noch nicht vorhanden
        if "shop_buy_one" not in self.ui_rects:
            txt = arcade.Text(self.shop_buy_one_label, 0, 0, arcade.color.WHITE, 24, anchor_x="center", anchor_y="center")
            bw = txt.content_width + 100
            bh = txt.content_height + 42
            bx = self.width / 2 - bw / 2
            by = self.height - 400
            self.ui_rects["shop_buy_one"] = (bx, by, bw, bh)

        missing_energy = max(0, 100 - int(self.energy))
        energy_cost = min(5, missing_energy) * 5
        if self.cached_energy_cost != energy_cost or "shop_energy" not in self.ui_rects:
            energy_label = f"⚡ Energie +5%   Preis: {energy_cost}"
            txt2 = arcade.Text(energy_label, 0, 0, arcade.color.WHITE, 24, anchor_x="center", anchor_y="center")
            bw2 = txt2.content_width + 100
            bh2 = txt2.content_height + 42
            bx2 = self.width / 2 - bw2 / 2
            by2 = self.height - 480
            self.ui_rects["shop_energy"] = (bx2, by2, bw2, bh2)
            self.cached_energy_cost = energy_cost

        # leave Button bleibt unverändert

    def draw_cached_text(self, key, text, x, y, color, size, anchor_x="left", anchor_y="baseline"):
        sig = (size, anchor_x, anchor_y)
        cached = self.text_cache.get(key)
        if cached is None or cached["sig"] != sig:
            obj = arcade.Text(text, x, y, color, size, anchor_x=anchor_x, anchor_y=anchor_y)
            self.text_cache[key] = {"sig": sig, "obj": obj}
        else:
            obj = cached["obj"]
            obj.text = text
            obj.x = x
            obj.y = y
            obj.color = color
        obj.draw()

    def update_hover_levels(self, delta_time: float):
        active_keys = []
        if self.state == "menu":
            active_keys = ["menu_name_field", "menu_login_play"]
        elif self.state == "game":
            active_keys = ["wave_button"]
            active_keys.extend(["upgrade_panel_window", "upgrade_panel_weapon", "upgrade_panel_health", "upgrade_panel_auto"])
        elif self.state == "settings":
            active_keys = []
        elif self.state == "shop":
            active_keys = ["shop_buy_one", "shop_energy", "shop_leave"]
            if not self.auto_shot_owned:
                active_keys.append("shop_auto")
        elif self.state == "gameover":
            active_keys = ["gameover_restart"]

        # Physikalisch geglättetes Hover (Feder-Dämpfer)
        k = 4200.0     # noch direkter für Klick-/Hover-Reaktion
        d = 240.0      # stabil genug ohne Flattern
        for key in active_keys:
            target = 1.0 if self.is_hover(key) else 0.0
            x = self.hover_level.get(key, 0.0)
            v = self.hover_velocity.get(key, 0.0)
            # x'' = k*(target - x) - d*v
            a = k * (target - x) - d * v
            v += a * delta_time
            x += v * delta_time
            # clamp and reset small values
            if x < 0.0:
                x = 0.0
                v = 0.0
            elif x > 1.0:
                x = 1.0
                v = 0.0
            self.hover_level[key] = x
            self.hover_velocity[key] = v

        # Auto-Schuss Cooldown
        if self.auto_shot_cooldown > 0:
            self.auto_shot_cooldown -= delta_time
            if self.auto_shot_cooldown < 0:
                self.auto_shot_cooldown = 0.0
        if self.weapon_shot_cooldown > 0:
            self.weapon_shot_cooldown -= delta_time
            if self.weapon_shot_cooldown < 0:
                self.weapon_shot_cooldown = 0.0
        if self.weapon_hold_timer > 0:
            self.weapon_hold_timer -= delta_time
            if self.weapon_hold_timer < 0:
                self.weapon_hold_timer = 0.0
    def on_resize(self, width, height):
        super().on_resize(width, height)
        self._ui_dirty = True

    def leave_shop(self):
        self.state = "game"
        self.portal_cooldown_timer = PORTAL_COOLDOWN
        self.player.center_x = 0
        self.player.center_y = 0
        self.stop_shop_sound()
        # Shop-Eintritts-Sound ist einmalig, muss nicht gestoppt werden; falls geloopt wird, hier stoppen
        # (Arcade play_sound returns player, hier nicht gespeichert, daher kein expliziter Stop nötig)
        self.cached_energy_cost = None
        if not self.wave_active:
            self.start_prep()

    def screen_to_world(self, x, y):
        cx, cy = self.camera.position
        dx = (x - self.width / 2) / max(self.camera_zoom, 1e-6)
        dy = (y - self.height / 2) / max(self.camera_zoom, 1e-6)
        wx = dx + cx
        wy = dy + cy
        return wx, wy

    def get_ai_targets(self):
        targets = [self.player]
        for remote in self.remote_players:
            if getattr(remote, "dead", False):
                continue
            targets.append(remote)
        return targets

    def start_wave(self):
        if self.wave_active:
            return
        if self.wave_started_once and self.wave_completed:
            self.wave_number += 1
        # Schwerer: schnellerer Spawn und schnelleres Scaling pro Welle.
        self.current_spawn_interval = max(0.25, 0.80 - (self.wave_number - 1) * 0.025)
        self.current_enemy_speed = max(140, ENEMY_SPEED * 0.35 + (self.wave_number - 1) * 24)
        self.wave_active = True
        self.wave_started_once = True
        self.wave_completed = False
        self.wave_timer = 0
        self.spawn_timer = 0
        self.wave_message = ""
        self.wave_message_timer = 0.0
        self.spawn_cycles_done = 0
        self.spawn_cycles_per_wave = 0
        # Schwerer: deutlich mehr Zombies pro Welle (Welle 20 ~ 143).
        self.wave_spawn_goal = max(10, int(round(10 + (self.wave_number - 1) * 7.0)))
        self.wave_spawned_total = 0
        self.wave_kills = 0
        self.wave_lives_lost = 0
        self.wave_reward_coins = 0
        self.stop_prep()
        self.start_bg()
        self.wave_auto_timer = 5.0
    def fire_bullet_towards(self, target_x, target_y, apply_cooldown=True):
        if not self.weapon_equipped:
            return False
        if apply_cooldown and self.weapon_shot_cooldown > 0:
            return False
        dx = target_x - self.player.center_x
        dy = target_y - self.player.center_y
        dist = math.hypot(dx, dy)
        if dist == 0:
            return False
        dir_x = dx / dist
        dir_y = dy / dist
        # Schuss startet ~5mm rechts vom linken Rand (~19px) und ~1.5cm unterhalb des oberen Spielerrands (~57px)
        start_x = self.player.center_x - self.player.width / 2 + 30
        start_y = self.player.center_y + self.player.height / 2 - 57

        bullet_speed = ((170 + (100/60)) + 50 + 100 + 300 + 120)

        def spawn_single_bullet(local_dir_x, local_dir_y):
            bullet = arcade.SpriteCircle(5.5, arcade.color.ORANGE_PEEL,
                                         center_x=start_x,
                                         center_y=start_y)
            bullet.alpha = 255
            bullet.change_x = local_dir_x * bullet_speed
            bullet.change_y = local_dir_y * bullet_speed
            bullet.life_time = 1e9  # quasi unendlich
            self.bullet_list.append(bullet)
            if self.online_client and self.online_client.connected:
                self.online_client.send_shot(start_x, start_y, bullet.change_x, bullet.change_y, 1.2)

        if self.weapon_level in (1, 3):
            spawn_single_bullet(dir_x, dir_y)
            if apply_cooldown:
                self.weapon_shot_cooldown = self.get_weapon_cooldown()
            return True

        spread_angle = 0.12
        base_angle = math.atan2(dir_y, dir_x)
        for offset in (-spread_angle, 0.0, spread_angle):
            angle = base_angle + offset
            spawn_single_bullet(math.cos(angle), math.sin(angle))

        if apply_cooldown:
            cooldown = self.get_weapon_cooldown()
            if cooldown > 0:
                self.weapon_shot_cooldown = cooldown
        return True

    def fire_bullet(self, screen_x, screen_y):
        wx, wy = self.screen_to_world(screen_x, screen_y)
        return self.fire_bullet_towards(wx, wy, apply_cooldown=True)

    def on_close(self):
        self.stop_bg()
        self.stop_shop_sound()
        self.stop_prep()
        super().on_close()

    # ---------------- UPDATE ----------------
    def on_update(self, delta_time):

        if self.admin_message_timer > 0:
            self.admin_message_timer -= delta_time
            if self.admin_message_timer <= 0:
                self.admin_message = ""

        # Caret blink
        if self.admin_focus:
            self.caret_timer += delta_time
            if self.caret_timer >= 0.5:
                self.caret_timer = 0.0
                self.caret_visible = not self.caret_visible
        else:
            self.caret_visible = True
            self.caret_timer = 0.0

        self.update_hover_levels(delta_time)

        # Online-Snapshot in allen relevanten States aktualisieren (Lobby + Game).
        if self.online_client and self.online_client.connected:
            current_health = self.player_health if self.state == "game" else self.player_health_max
            self.online_client.send_state(
                self.player.center_x,
                self.player.center_y,
                current_health,
                self.wave_number,
                self.state,
                self.state == "lobby" and self.lobby_active_circle >= 0,
                self.lobby_active_circle,
                self.is_downed,
            )
            snapshot = self.online_client.get_snapshot()
            players = snapshot.get("players", [])
            new_remote = []
            self_data = None
            for player_data in players:
                if player_data.get("id") == self.online_client.player_id:
                    self_data = player_data
                    continue
                ghost = type("Ghost", (), {})()
                ghost.id = int(player_data.get("id", -1))
                ghost.center_x = float(player_data.get("x", 0.0))
                ghost.center_y = float(player_data.get("y", 0.0))
                ghost_name = str(player_data.get("name", "User"))
                if ghost_name.strip().lower() == "spieler":
                    ghost_name = "User"
                ghost.name = ghost_name
                ghost.dead = bool(player_data.get("dead", False))
                new_remote.append(ghost)
            self.remote_players = new_remote
            self.remote_portals = snapshot.get("portals", {})

            if self_data and self.is_downed and not bool(self_data.get("dead", True)):
                self.is_downed = False
                self.player_health = self.player_health_max
                self.respawn_timer = 0.0

            now = time.time()
            updated_remote_bullets = []
            for event in snapshot.get("bullets", []):
                event_id = int(event.get("id", -1))
                owner_id = int(event.get("owner_id", -1))
                if event_id in self.remote_bullet_seen or owner_id == self.online_client.player_id:
                    continue
                t0 = float(event.get("t0", now))
                ttl = float(event.get("ttl", 0.0))
                age = max(0.0, now - t0)
                if age > ttl:
                    self.remote_bullet_seen.add(event_id)
                    continue
                bullet = type("RemoteBullet", (), {})()
                bullet.id = event_id
                bullet.center_x = float(event.get("x", 0.0)) + float(event.get("vx", 0.0)) * age
                bullet.center_y = float(event.get("y", 0.0)) + float(event.get("vy", 0.0)) * age
                bullet.change_x = float(event.get("vx", 0.0))
                bullet.change_y = float(event.get("vy", 0.0))
                bullet.expires_at = t0 + ttl
                updated_remote_bullets.append(bullet)
            self.remote_bullets = updated_remote_bullets
        elif self.online_client and not self.online_client.connected:
            # Bei Verbindungsabbruch alle Remote-Skins sofort entfernen.
            self.remote_players = []
            self.remote_bullets = []
            self.remote_portals = {}

        if self.state == "lobby":
            # Bewegung auch in der Lobby erlauben.
            self.player.change_x = 0
            self.player.change_y = 0
            speed = PLAYER_SPEED

            move_x = 0
            move_y = 0
            if arcade.key.A in self.keys or arcade.key.LEFT in self.keys:
                move_x -= 1
            if arcade.key.D in self.keys or arcade.key.RIGHT in self.keys:
                move_x += 1
            if arcade.key.W in self.keys or arcade.key.UP in self.keys:
                move_y += 1
            if arcade.key.S in self.keys or arcade.key.DOWN in self.keys:
                move_y -= 1

            if move_x != 0 or move_y != 0:
                length = math.hypot(move_x, move_y)
                self.player.change_x = (move_x / length) * speed
                self.player.change_y = (move_y / length) * speed

            self.player.center_x += self.player.change_x * delta_time
            self.player.center_y += self.player.change_y * delta_time
            self.player.center_x = max(-LOBBY_WIDTH//2, min(LOBBY_WIDTH//2, self.player.center_x))
            self.player.center_y = max(-LOBBY_HEIGHT//2, min(LOBBY_HEIGHT//2, self.player.center_y))
            self.camera.position = (self.player.center_x, self.player.center_y)
            # Lobby-Kreise dynamisch auf aktuelle Fenstergröße legen.
            spacing = 520
            radius = 190
            base_x = 0
            y = LOBBY_HEIGHT / 2 - 460
            self.lobby_circles = [
                (base_x - spacing, y, radius),
                (base_x, y, radius),
                (base_x + spacing, y, radius),
            ]

            player_screen_x = self.player.center_x
            player_screen_y = self.player.center_y
            # Solange ein Teleporter aktiv ist, bleibt der Spieler darin gefangen
            # bis Teleport oder bis er aktiv "Verlassen" klickt.
            if self.lobby_active_circle >= 0:
                cx, cy, _r = self.lobby_circles[self.lobby_active_circle]
                self.player.center_x = cx
                self.player.center_y = cy
                portal_info = self.remote_portals.get(str(self.lobby_active_circle), self.remote_portals.get(self.lobby_active_circle, {}))
                # Servermodus: Countdown aus Snapshot.
                # Offline/kein Snapshot: lokaler Fallback-Countdown.
                if portal_info:
                    shared_remaining = float(portal_info.get("remaining", self.lobby_timer))
                    self.lobby_timer = shared_remaining
                    ready = bool(portal_info.get("ready", False)) or shared_remaining <= 0
                else:
                    self.lobby_timer = max(0.0, self.lobby_timer - delta_time)
                    ready = self.lobby_timer <= 0
                if ready:
                    self.state = "game"
                    self.player.center_x = 0
                    self.player.center_y = 0
                    self.start_prep()
                    self.lobby_timer = self.lobby_wait_time
                    self.lobby_active_circle = -1
                return

            active = -1
            for idx, (cx, cy, r) in enumerate(self.lobby_circles):
                if math.hypot(player_screen_x - cx, player_screen_y - cy) <= r:
                    active = idx
                    break

            if active >= 0:
                self.lobby_active_circle = active
                portal_info = self.remote_portals.get(str(active), self.remote_portals.get(active, {}))
                # Countdown wird nur vom ersten Spieler gestartet (Server-Quelle).
                # Wer später beitritt, übernimmt die bereits laufende Restzeit.
                if portal_info:
                    self.lobby_timer = float(portal_info.get("remaining", self.lobby_wait_time))
                else:
                    self.lobby_timer = self.lobby_wait_time
                cx, cy, _r = self.lobby_circles[self.lobby_active_circle]
                self.player.center_x = cx
                self.player.center_y = cy
            else:
                self.lobby_active_circle = -1
                self.lobby_timer = self.lobby_wait_time
            return

        if self.state != "game":
            return

        if self.is_downed:
            if self.respawn_timer > 0:
                self.respawn_timer -= delta_time
                if self.respawn_timer < 0:
                    self.respawn_timer = 0.0
            return

        if self.player_damage_cooldown > 0:
            self.player_damage_cooldown -= delta_time
            if self.player_damage_cooldown < 0:
                self.player_damage_cooldown = 0.0

        # Auto-Schuss auslösen, falls gekauft
        if self.auto_shot_owned and self.wave_active and self.auto_shot_cooldown <= 0:
            moving_now = abs(self.player.change_x) > 0.01 or abs(self.player.change_y) > 0.01
            if not moving_now:
                target_enemy = None
                target_dist = None
                for enemy in self.enemies:
                    if enemy.is_dying or enemy.is_spawning:
                        continue
                    dist = arcade.get_distance_between_sprites(self.player, enemy)
                    if dist <= SHOT_RADIUS and (target_dist is None or dist < target_dist):
                        target_dist = dist
                        target_enemy = enemy
                if target_enemy is not None:
                    self.fire_bullet_towards(target_enemy.center_x, target_enemy.center_y, apply_cooldown=False)
                    self.auto_shot_cooldown = 0.4

        # Gedrueckt halten = kontinuierlich schiessen (Cooldown der Waffe bleibt aktiv).
        if self.mouse_left_down and self.weapon_hold_timer <= 0:
            if self.fire_bullet(self.mouse_x, self.mouse_y):
                self.weapon_hold_timer = self.mouse_hold_repeat_delay

        # Auto-Start nach Vorbereitung
        if not self.wave_active:
            self.wave_auto_timer -= delta_time
            if self.wave_auto_timer <= 0:
                self.start_wave()
        else:
            self.wave_auto_timer = 5.0

        # Bullets bewegen und Lebensdauer prüfen
        for bullet in list(self.bullet_list):
            bullet.center_x += bullet.change_x * delta_time
            bullet.center_y += bullet.change_y * delta_time
            bullet.life_time -= delta_time
                # Kugeln außerhalb der Arena entfernen
            if (bullet.center_x < -MAP_WIDTH / 2 or
                bullet.center_x > MAP_WIDTH / 2 or
                bullet.center_y < -MAP_HEIGHT / 2 or
                bullet.center_y > MAP_HEIGHT / 2):
                bullet.kill()
                continue
            if bullet.life_time <= 0:
                bullet.kill()
                continue
            hits = arcade.check_for_collision_with_list(bullet, self.enemies)
            for enemy in hits:
                if enemy.is_dying or enemy.is_spawning:
                    continue
                enemy.hit_points -= 1
                if enemy.hit_points > 0:
                    bullet.kill()
                    break
                enemy.kill()
                bullet.kill()
                self.wave_kills += 1
                self.total_enemy_kills += 1
                self.gems += enemy.gem_reward
                break

        self.prev_player_pos = (self.player.center_x, self.player.center_y)
        self.player.change_x = 0
        self.player.change_y = 0
        speed = PLAYER_SPEED

        move_x = 0
        move_y = 0
        if arcade.key.A in self.keys or arcade.key.LEFT in self.keys:
            move_x -= 1
        if arcade.key.D in self.keys or arcade.key.RIGHT in self.keys:
            move_x += 1
        if arcade.key.W in self.keys or arcade.key.UP in self.keys:
            move_y += 1
        if arcade.key.S in self.keys or arcade.key.DOWN in self.keys:
            move_y -= 1

        if move_x != 0 or move_y != 0:
            length = math.hypot(move_x, move_y)
            self.player.change_x = (move_x / length) * speed
            self.player.change_y = (move_y / length) * speed

        self.player.center_x += self.player.change_x * delta_time
        self.player.center_y += self.player.change_y * delta_time

        if self.wave_number >= 5:
            smoke_left = -MAP_WIDTH / 2 + SMOKE_BORDER_THICKNESS
            smoke_right = MAP_WIDTH / 2 - SMOKE_BORDER_THICKNESS
            smoke_bottom = -MAP_HEIGHT / 2 + SMOKE_BORDER_THICKNESS
            smoke_top = MAP_HEIGHT / 2 - SMOKE_BORDER_THICKNESS
            in_smoke = (
                self.player.center_x <= smoke_left or
                self.player.center_x >= smoke_right or
                self.player.center_y <= smoke_bottom or
                self.player.center_y >= smoke_top
            )
            if in_smoke:
                self.smoke_damage_acc += SMOKE_DAMAGE_PER_SECOND * delta_time
                while self.smoke_damage_acc >= 1.0 and self.player_health > 0:
                    self.player_health = max(0, self.player_health - 1)
                    self.smoke_damage_acc -= 1.0
            else:
                self.smoke_damage_acc = 0.0
        else:
            self.smoke_damage_acc = 0.0

        moving = self.player.change_x != 0 or self.player.change_y != 0
        self.sprint_drain_acc = 0.0

        energy_int = int(self.energy)
        if energy_int != self.last_energy_int:
            self.last_energy_int = energy_int
            self.cached_energy_cost = None

        # Keine Fades mehr: nichts zu tun

        # Map Grenzen
        self.player.center_x = max(-MAP_WIDTH//2, min(MAP_WIDTH//2, self.player.center_x))
        self.player.center_y = max(-MAP_HEIGHT//2, min(MAP_HEIGHT//2, self.player.center_y))

        if self.portal_cooldown_timer > 0:
            self.portal_cooldown_timer -= delta_time
            if self.portal_cooldown_timer < 0:
                self.portal_cooldown_timer = 0.0

        if not self.wave_active and self.portal_cooldown_timer <= 0:
            pass

        # Wave System
        if self.wave_message_timer > 0:
            self.wave_message_timer -= delta_time
            if self.wave_message_timer <= 0:
                self.wave_message = ""
                self.wave_message_timer = 0.0

        if self.wave_active:
            self.wave_timer += delta_time
            self.spawn_timer += delta_time

            if self.spawn_timer >= self.current_spawn_interval and self.wave_spawned_total < self.wave_spawn_goal:
                self.spawn_enemies()
                self.spawn_timer = 0
                self.wave_spawned_total += 1

            alive_enemies = 0
            for enemy in self.enemies:
                if not enemy.is_dying:
                    alive_enemies += 1

            if self.wave_spawned_total >= self.wave_spawn_goal and alive_enemies == 0:
                self.wave_active = False
                self.stop_bg()
                if self.state == "game":
                    self.start_prep()
                self.player_health = self.player_health_max
                self.player_damage_cooldown = 0.0
                self.wave_completed = True
                self.wave_message = "WELLE BESTANDEN"
                self.wave_message_timer = 3.0
                self.wave_reward_coins = self.wave_kills - self.wave_lives_lost + (self.wave_number * 10)
                self.total_coins += self.wave_reward_coins

        # Enemy Update
        for enemy in self.enemies:
            if enemy.is_spawning:
                enemy.spawn_timer -= delta_time
                if enemy.spawn_timer <= 0:
                    enemy.is_spawning = False
                    enemy.texture = enemy.final_texture
                    enemy.scale = enemy.final_scale
                continue
            if enemy.is_dying:
                enemy.death_timer -= delta_time
                if enemy.death_timer <= 0:
                    enemy.kill()
                continue

            targets = self.get_ai_targets()
            nearest = None
            nearest_dist = None
            for target in targets:
                tdx = target.center_x - enemy.center_x
                tdy = target.center_y - enemy.center_y
                d = math.hypot(tdx, tdy)
                if nearest is None or d < nearest_dist:
                    nearest = target
                    nearest_dist = d
            if nearest is None:
                continue

            dx = nearest.center_x - enemy.center_x
            dy = nearest.center_y - enemy.center_y
            dist = math.hypot(dx, dy)

            if dist > 0:
                enemy.center_x += (dx / dist) * enemy.base_speed * delta_time
                enemy.center_y += (dy / dist) * enemy.base_speed * delta_time

            enemy.center_x = max(-MAP_WIDTH//2, min(MAP_WIDTH//2, enemy.center_x))
            enemy.center_y = max(-MAP_HEIGHT//2, min(MAP_HEIGHT//2, enemy.center_y))

            if arcade.check_for_collision(enemy, self.player) and self.player_damage_cooldown <= 0:
                self.player_health = max(0, self.player_health - enemy.touch_damage)
                self.wave_lives_lost += 1
                self.player_damage_cooldown = 0.35

        if self.player_health <= 0:
            if self.online_client and len(self.remote_players) > 0:
                self.is_downed = True
                self.respawn_timer = 20.0
                self.player_health = 0
            else:
                self.state = "gameover"

        self.camera.position = (self.player.center_x, self.player.center_y)

    # ---------------- SPAWN ----------------
    def spawn_enemies(self):
        amount = 1
        for _ in range(amount):
            # Ab Welle 10: auch Typ 3, ab Welle 5: auch Typ 2, davor nur Typ 1.
            if self.wave_number >= 10:
                enemy_type = random.choice((1, 2, 3))
            elif self.wave_number >= 5:
                enemy_type = random.choice((1, 2))
            else:
                enemy_type = 1

            if enemy_type == 3:
                spawn_texture = str(IMG_DIR / "loch3.png")
                final_texture = self.enemy3_texture
                hit_points = 25
                base_speed = self.current_enemy_speed * 1.5
                gem_reward = 25
                touch_damage = 24
            elif enemy_type == 2:
                spawn_texture = str(IMG_DIR / "loch2.png")
                final_texture = self.enemy2_texture
                hit_points = 10
                base_speed = self.current_enemy_speed
                gem_reward = 10
                touch_damage = 16
            else:
                spawn_texture = str(IMG_DIR / "loch.png")
                final_texture = self.enemy_texture
                hit_points = 5
                base_speed = self.current_enemy_speed
                gem_reward = 10
                touch_damage = 10

            enemy = Enemy(spawn_texture)
            enemy.scale = 0.25
            enemy.base_speed = base_speed
            enemy.hit_points = hit_points
            enemy.max_hit_points = hit_points
            enemy.enemy_type = enemy_type
            enemy.gem_reward = gem_reward
            enemy.touch_damage = touch_damage
            enemy.final_texture = final_texture
            enemy.final_scale = 0.25
            enemy.is_spawning = True
            enemy.spawn_timer = SPAWN_PREVIEW_DURATION
            for _attempt in range(24):
                spawn_x = random.uniform(-MAP_WIDTH / 2, MAP_WIDTH / 2)
                spawn_y = random.uniform(-MAP_HEIGHT / 2, MAP_HEIGHT / 2)
                if math.hypot(spawn_x - self.player.center_x, spawn_y - self.player.center_y) >= 420:
                    enemy.center_x = spawn_x
                    enemy.center_y = spawn_y
                    break
            else:
                enemy.center_x = random.uniform(-MAP_WIDTH / 2, MAP_WIDTH / 2)
                enemy.center_y = random.uniform(-MAP_HEIGHT / 2, MAP_HEIGHT / 2)
            self.enemies.append(enemy)

    # ---------------- DRAW ----------------
    def on_draw(self):
        self.clear()
        self.ensure_ui_rects()

        if self.state == "menu":

            arcade.draw_text("SURVIVAL MAP",
                             self.width/2, self.height/2+150,
                             arcade.color.WHITE, 60,
                             anchor_x="center")
            caret = "|" if self.caret_visible else ""
            if self.menu_mode == "choice":
                lbx, lby, lbw, lbh = self.ui_rects["menu_login"]
                gbx, gby, gbw, gbh = self.ui_rects["menu_guest"]
                lvl_login = self.ease(self.hover_level.get("menu_login", 0.0))
                lvl_guest = self.ease(self.hover_level.get("menu_guest", 0.0))
                c_login = self.lerp_color(arcade.color.DARK_BLUE_GRAY, arcade.color.BLUE_GRAY, lvl_login)
                c_guest = self.lerp_color(arcade.color.DARK_SPRING_GREEN, arcade.color.SPRING_GREEN, lvl_guest)
                self.draw_scaled_rect(lbx, lby, lbw, lbh, c_login, lvl_login, scale_factor=0.18)
                self.draw_scaled_rect(gbx, gby, gbw, gbh, c_guest, lvl_guest, scale_factor=0.18)
                arcade.draw_text("Registrieren",
                                 lbx + lbw/2, lby + lbh/2,
                                 arcade.color.WHITE, 30,
                                 anchor_x="center", anchor_y="center")
                arcade.draw_text("Anmelden",
                                 gbx + gbw/2, gby + gbh/2,
                                 arcade.color.WHITE, 30,
                                 anchor_x="center", anchor_y="center")
                self.start_button = None
            elif self.menu_mode in ("login", "guest"):
                bx, by, bw, bh = self.ui_rects["menu_login_play"]
                level = self.ease(self.hover_level.get("menu_login_play", 0.0))
                start_color = self.lerp_color(arcade.color.GRAY, arcade.color.LIGHT_GRAY, level)
                self.draw_scaled_rect(bx, by, bw, bh, start_color, level, scale_factor=0.22)
                arcade.draw_text("Spielen",
                                 bx + bw/2, by + bh/2,
                                 arcade.color.WHITE, 30,
                                 anchor_x="center", anchor_y="center")
                self.start_button = (bx, by, bw, bh)
            if self.menu_mode == "name":
                bx, by, bw, bh = self.ui_rects["menu_login_play"]
                level = self.ease(self.hover_level.get("menu_login_play", 0.0))
                start_color = self.lerp_color(arcade.color.GRAY, arcade.color.LIGHT_GRAY, level)
                self.draw_scaled_rect(bx, by, bw, bh, start_color, level, scale_factor=0.22)
                arcade.draw_text("Spielen",
                                 bx + bw/2, by + bh/2,
                                 arcade.color.WHITE, 30,
                                 anchor_x="center", anchor_y="center")
                self.start_button = (bx, by, bw, bh)
                nx, ny, nw, nh = self.ui_rects["menu_name_field"]
                arcade.draw_text("Name:", nx, ny + nh + 8, arcade.color.WHITE, 24)
                name_border = arcade.color.GOLD if self.menu_focus_field == "name" else arcade.color.WHITE
                arcade.draw_lbwh_rectangle_outline(nx, ny, nw, nh, name_border, border_width=3)
                name_caret = "|" if self.caret_visible else ""
                arcade.draw_text(self.player_name + name_caret,
                                 nx + 10, ny + nh/2,
                                 arcade.color.WHITE, 26,
                                 anchor_y="center")
                arcade.draw_text("Enter oder Klick auf Spielen",
                                 self.width/2, by - 30,
                                 arcade.color.LIGHT_GRAY, 20,
                                 anchor_x="center")

        elif self.state == "lobby":
            with self.camera.activate():
                arcade.draw_lbwh_rectangle_outline(-LOBBY_WIDTH/2, -LOBBY_HEIGHT/2, LOBBY_WIDTH, LOBBY_HEIGHT,
                                                   arcade.color.WHITE, border_width=4)
                for idx, (cx, cy, r) in enumerate(self.lobby_circles):
                    tex_size = r * 2
                    arcade.draw_texture_rect(
                        self.teleporter_texture,
                        arcade.LBWH(cx - r, cy - r, tex_size, tex_size),
                    )
                    portal_info = self.remote_portals.get(str(idx), self.remote_portals.get(idx, {}))
                    players_in_this = int(portal_info.get("count", 0))
                    if not portal_info:
                        if idx == self.lobby_active_circle:
                            players_in_this += 1
                        for ghost in self.remote_players:
                            if math.hypot(ghost.center_x - cx, ghost.center_y - cy) <= r:
                                players_in_this += 1
                    arcade.draw_text(f"{players_in_this}/3",
                                     cx, cy + r + 26,
                                     arcade.color.WHITE, 22,
                                     anchor_x="center")
                    if idx == self.lobby_active_circle or players_in_this > 0:
                        # Graue Basis-Ringlinie + gruener Countdown-Ring, der mit der Zeit ablaeuft.
                        ring_radius = r + 6
                        arcade.draw_circle_outline(cx, cy, ring_radius, arcade.color.DARK_GRAY, 5)
                        rem_secs = float(portal_info.get("remaining", self.lobby_timer))
                        remaining = max(0.0, min(1.0, rem_secs / self.lobby_wait_time))
                        sweep = 360.0 * remaining
                        if sweep > 0:
                            segments = max(12, int(80 * remaining))
                            start_angle = 90.0
                            for seg_idx in range(segments):
                                a1 = math.radians(start_angle - (sweep * seg_idx / segments))
                                a2 = math.radians(start_angle - (sweep * (seg_idx + 1) / segments))
                                x1 = cx + math.cos(a1) * ring_radius
                                y1 = cy + math.sin(a1) * ring_radius
                                x2 = cx + math.cos(a2) * ring_radius
                                y2 = cy + math.sin(a2) * ring_radius
                                arcade.draw_line(x1, y1, x2, y2, arcade.color.SPRING_GREEN, 5)
                self.player_list.draw()
                arcade.draw_text(
                    self.player_name if self.player_name else "",
                    self.player.center_x,
                    self.player.center_y + self.player.height / 2 + 20,
                    arcade.color.WHITE,
                    16,
                    anchor_x="center",
                )
                for ghost in self.remote_players:
                    w = self.player.width
                    h = self.player.height
                    arcade.draw_texture_rect(
                        self.remote_player_texture,
                        arcade.LBWH(ghost.center_x - w / 2, ghost.center_y - h / 2, w, h),
                    )
                    arcade.draw_text(
                        ghost.name,
                        ghost.center_x,
                        ghost.center_y + h / 2 + 20,
                        arcade.color.WHITE,
                        14,
                        anchor_x="center",
                    )

            if self.lobby_active_circle >= 0:
                progress = 1.0 - max(0.0, min(1.0, self.lobby_timer / self.lobby_wait_time))
                p_w, p_h = 320, 18
                p_x = self.width / 2 - p_w / 2
                p_y = self.height - 64
                arcade.draw_lbwh_rectangle_filled(p_x, p_y, p_w, p_h, arcade.color.DARK_BLUE_GRAY)
                arcade.draw_lbwh_rectangle_filled(p_x, p_y, p_w * progress, p_h, arcade.color.SPRING_GREEN)
                arcade.draw_lbwh_rectangle_outline(p_x, p_y, p_w, p_h, arcade.color.WHITE, 2)
                leave_rect = (20, self.height - 86, 170, 56)
                self.ui_rects["lobby_leave"] = leave_rect
                lbx, lby, lbw, lbh = leave_rect
                arcade.draw_lbwh_rectangle_filled(lbx, lby, lbw, lbh, arcade.color.DARK_RED)
                arcade.draw_lbwh_rectangle_outline(lbx, lby, lbw, lbh, arcade.color.WHITE, 2)
                arcade.draw_text("Verlassen",
                                 lbx + lbw / 2, lby + lbh / 2,
                                 arcade.color.WHITE, 22,
                                 anchor_x="center", anchor_y="center")
            else:
                self.ui_rects["lobby_leave"] = (0, 0, 0, 0)

        elif self.state == "game":

            with self.camera.activate():
                if self.wave_number >= 5:
                    smoke_left = -MAP_WIDTH / 2
                    smoke_bottom = -MAP_HEIGHT / 2
                    smoke_right = MAP_WIDTH / 2
                    smoke_top = MAP_HEIGHT / 2
                    tile = 160
                    # Rauch-Rand als giftige Außenlinie
                    x = smoke_left
                    while x < smoke_right:
                        arcade.draw_texture_rect(
                            self.smoke_texture,
                            arcade.LBWH(x, smoke_bottom, tile, tile),
                        )
                        arcade.draw_texture_rect(
                            self.smoke_texture,
                            arcade.LBWH(x, smoke_top - tile, tile, tile),
                        )
                        x += tile
                    y = smoke_bottom + tile
                    while y < smoke_top - tile:
                        arcade.draw_texture_rect(
                            self.smoke_texture,
                            arcade.LBWH(smoke_left, y, tile, tile),
                        )
                        arcade.draw_texture_rect(
                            self.smoke_texture,
                            arcade.LBWH(smoke_right - tile, y, tile, tile),
                        )
                        y += tile
                arcade.draw_lbwh_rectangle_outline(-MAP_WIDTH/2, -MAP_HEIGHT/2, MAP_WIDTH, MAP_HEIGHT,
                                                   arcade.color.RED, border_width=6)
                self.decor_list.draw()
                self.enemies.draw()
                for bullet in self.bullet_list:
                    arcade.draw_circle_filled(bullet.center_x, bullet.center_y, 5.5, arcade.color.ORANGE_PEEL)
                now = time.time()
                active_remote_bullets = []
                for remote_bullet in self.remote_bullets:
                    if now >= remote_bullet.expires_at:
                        self.remote_bullet_seen.add(remote_bullet.id)
                        continue
                    remote_bullet.center_x += remote_bullet.change_x * (1.0 / 240.0)
                    remote_bullet.center_y += remote_bullet.change_y * (1.0 / 240.0)
                    arcade.draw_circle_filled(remote_bullet.center_x, remote_bullet.center_y, 5.5, arcade.color.LIGHT_BLUE)
                    active_remote_bullets.append(remote_bullet)
                self.remote_bullets = active_remote_bullets
                self.player_list.draw()
                for ghost in self.remote_players:
                    w = self.player.width
                    h = self.player.height
                    arcade.draw_texture_rect(
                        self.remote_player_texture,
                        arcade.LBWH(ghost.center_x - w / 2, ghost.center_y - h / 2, w, h),
                    )
                    arcade.draw_text(
                        ghost.name,
                        ghost.center_x,
                        ghost.center_y + h / 2 + 20,
                        arcade.color.WHITE,
                        14,
                        anchor_x="center",
                    )
                # Kleine HP-Leiste ueber jedem aktiven Gegner.
                for enemy in self.enemies:
                    if enemy.is_dying or enemy.is_spawning:
                        continue
                    hp_ratio = max(0.0, min(1.0, enemy.hit_points / enemy.max_hit_points))
                    bar_w = 146
                    bar_h = 9
                    bar_x = enemy.center_x - bar_w / 2
                    bar_y = enemy.center_y + enemy.height / 2 + 8
                    arcade.draw_lbwh_rectangle_filled(bar_x, bar_y, bar_w, bar_h, arcade.color.DARK_RED)
                    arcade.draw_lbwh_rectangle_filled(bar_x, bar_y, bar_w * hp_ratio, bar_h, arcade.color.SPRING_GREEN)
                    arcade.draw_lbwh_rectangle_outline(bar_x, bar_y, bar_w, bar_h, arcade.color.WHITE, 1)
                arcade.draw_text(self.player_name,
                                 self.player.center_x,
                                 self.player.center_y + self.player.height/2 + 20,
                                 arcade.color.BLACK, 18,
                                 anchor_x="center")
                # Markiere Gegner im Radius
                for enemy in self.enemies:
                    if enemy.is_dying:
                        continue
                    dist = arcade.get_distance_between_sprites(self.player, enemy)
                    if dist <= SHOT_RADIUS:
                        pass

            # Wave Button
            # Anzeigen
            hud_left_x = 20
            hud_left_y = self.height - 40
            name_text = self.player_name if self.player_name else ""
            health_ratio = 0 if self.player_health_max <= 0 else self.player_health / self.player_health_max
            arcade.draw_text("Leben",
                             hud_left_x, hud_left_y + 20,
                             arcade.color.WHITE, 18)
            arcade.draw_lbwh_rectangle_filled(hud_left_x, hud_left_y - 6, 220, 22, arcade.color.DARK_RED)
            arcade.draw_lbwh_rectangle_filled(hud_left_x, hud_left_y - 6, 220 * health_ratio, 22, arcade.color.SPRING_GREEN)
            arcade.draw_lbwh_rectangle_outline(hud_left_x, hud_left_y - 6, 220, 22, arcade.color.WHITE, 2)
            arcade.draw_text(f"{int(self.player_health)}/{self.player_health_max}",
                             hud_left_x + 110, hud_left_y + 5,
                             arcade.color.WHITE, 14,
                             anchor_x="center", anchor_y="center")
            arcade.draw_text(f"Name: {name_text}",
                             hud_left_x, hud_left_y - 36,
                             arcade.color.WHITE, 20)
            panel_x = 20
            panel_y = self.height - 240
            panel_w = 340
            panel_h = 250
            box_h = 58
            inner_x = panel_x + 14
            inner_w = panel_w - 28
            arcade.draw_lbwh_rectangle_filled(panel_x, panel_y, panel_w, panel_h, (10, 12, 14, 185))
            arcade.draw_lbwh_rectangle_outline(panel_x, panel_y, panel_w, panel_h, arcade.color.LIGHT_GRAY, 2)
            arcade.draw_text("UPGRADES",
                             panel_x + 16, panel_y + panel_h - 34,
                             arcade.color.GOLD, 22)
            weapon_box_y = panel_y + 160
            health_box_y = panel_y + 96
            auto_box_y = panel_y + 32

            arcade.draw_lbwh_rectangle_filled(inner_x, weapon_box_y, inner_w, box_h, (34, 28, 24, 220))
            arcade.draw_lbwh_rectangle_outline(inner_x, weapon_box_y, inner_w, box_h,
                                               arcade.color.GOLD, 2)
            next_weapon_name = self.get_next_weapon_name()
            next_cost = self.get_weapon_upgrade_cost()
            arcade.draw_text(next_weapon_name,
                             inner_x + 14, weapon_box_y + box_h - 22,
                             arcade.color.WHITE, 16)
            if next_cost is None:
                next_weapon_cost_text = "Kein weiteres Upgrade"
                next_weapon_cost_color = arcade.color.GOLD
            else:
                next_weapon_cost_text = f"{next_cost} Gems"
                next_weapon_cost_color = arcade.color.SPRING_GREEN if self.gems >= next_cost else arcade.color.LIGHT_GRAY
            arcade.draw_text(next_weapon_cost_text,
                             inner_x + 14, weapon_box_y + 12,
                             next_weapon_cost_color, 15)

            health_cost = self.get_health_upgrade_cost()
            arcade.draw_lbwh_rectangle_filled(inner_x, health_box_y, inner_w, box_h, (24, 30, 36, 220))
            arcade.draw_lbwh_rectangle_outline(inner_x, health_box_y, inner_w, box_h,
                                               arcade.color.SPRING_GREEN, 2)
            arcade.draw_text("Lebensupgrade +20",
                             inner_x + 14, health_box_y + box_h - 22,
                             arcade.color.WHITE, 16)
            arcade.draw_text(f"{health_cost} Gems",
                             inner_x + 14, health_box_y + 12,
                             arcade.color.SPRING_GREEN if self.gems >= health_cost else arcade.color.LIGHT_GRAY, 15)

            auto_label = "Autoschuss"
            arcade.draw_lbwh_rectangle_filled(inner_x, auto_box_y, inner_w, box_h, (34, 24, 34, 220))
            arcade.draw_lbwh_rectangle_outline(inner_x, auto_box_y, inner_w, box_h,
                                               arcade.color.MAGENTA, 2)
            arcade.draw_text(auto_label,
                             inner_x + 14, auto_box_y + box_h - 22,
                             arcade.color.WHITE, 16)
            arcade.draw_text("500 Gems",
                             inner_x + 14, auto_box_y + 12,
                             arcade.color.SPRING_GREEN if self.gems >= 500 else arcade.color.LIGHT_GRAY, 15)
            arcade.draw_text("Nur wenn du stillstehst",
                             inner_x + 14, auto_box_y + 28,
                             arcade.color.LIGHT_GRAY, 12)
            arcade.draw_text(f"💎 Gems: {int(self.gems)}",
                             20, 165,
                             arcade.color.GOLD, 20)
            # Wave-Button ausgeblendet
            # Waffen-Slot unten links
            slot_w, slot_h = 120, 120
            slot_x, slot_y = 20, 20
            slot_color = arcade.color.GOLD if self.weapon_equipped else arcade.color.GRAY
            arcade.draw_lbwh_rectangle_outline(slot_x, slot_y, slot_w, slot_h, slot_color, border_width=4)
            arcade.draw_text("1", slot_x + slot_w/2, slot_y + slot_h - 22, arcade.color.WHITE, 22, anchor_x="center")
            if self.pistol_texture:
                self.pistol_icon_sprite.center_x = slot_x + slot_w/2
                self.pistol_icon_sprite.center_y = slot_y + slot_h/2
                self.pistol_icon_list.draw()
            if self.wave_active:
                arcade.draw_text(f"WELLE {self.wave_number}",
                                 self.width - 10, self.height - 15,
                                 arcade.color.RED, 34,
                                 anchor_x="right", anchor_y="top")
            else:
                prep_secs = max(0, math.ceil(self.wave_auto_timer))
                arcade.draw_text(f"Vorbereitung {prep_secs}s",
                                 self.width - 10, self.height - 15,
                                 arcade.color.GREEN, 34,
                                 anchor_x="right", anchor_y="top")

            if self.wave_message:
                arcade.draw_text(self.wave_message,
                                 self.width / 2, self.height - 90,
                                 arcade.color.GOLD, 30,
                                 anchor_x="center")
                # Keine Münz-Anzeige mehr
            if self.is_downed:
                self.draw_cached_text(
                    "downed_title",
                    "DU BIST KO",
                    self.width / 2,
                    self.height / 2 + 48,
                    arcade.color.RED,
                    46,
                    anchor_x="center",
                )
                if self.respawn_timer > 0:
                    self.draw_cached_text(
                        "downed_timer",
                        f"Restart in {int(math.ceil(self.respawn_timer))}s",
                        self.width / 2,
                        self.height / 2 - 8,
                        arcade.color.WHITE,
                        22,
                        anchor_x="center",
                    )
                    self.ui_rects["downed_respawn"] = (0, 0, 0, 0)
                else:
                    bx, by, bw, bh = (self.width / 2 - 170, self.height / 2 - 90, 340, 80)
                    self.ui_rects["downed_respawn"] = (bx, by, bw, bh)
                    arcade.draw_lbwh_rectangle_filled(bx, by, bw, bh, arcade.color.DARK_RED)
                    arcade.draw_lbwh_rectangle_outline(bx, by, bw, bh, arcade.color.WHITE, 2)
                    arcade.draw_text(
                        "Restart",
                        bx + bw / 2,
                        by + bh / 2,
                        arcade.color.WHITE,
                        30,
                        anchor_x="center",
                        anchor_y="center",
                    )

        elif self.state == "settings":
            arcade.draw_lbwh_rectangle_filled(0, 0, self.width, self.height, (0, 0, 0, 220))
            arcade.draw_text("Einstellungen",
                             self.width / 2, self.height - 120,
                             arcade.color.WHITE, 58,
                             anchor_x="center")
            if not self.settings_unlocked:
                arcade.draw_text("Gebe den Admin-Code ein:",
                                 self.width / 2, self.height - 220,
                                 arcade.color.WHITE, 28,
                                 anchor_x="center")
                arcade.draw_lbwh_rectangle_outline(self.width / 2 - 250, self.height - 300, 500, 60, arcade.color.WHITE, 3)
                caret = "|" if (self.admin_focus and self.caret_visible) else ""
                arcade.draw_text(self.admin_input + caret,
                                 self.width / 2 - 240, self.height - 280,
                                 arcade.color.WHITE, 26,
                                 anchor_x="left", anchor_y="center")
                if self.admin_message:
                    arcade.draw_text(self.admin_message,
                                     self.width / 2, self.height - 360,
                                     arcade.color.RED, 24,
                                     anchor_x="center")
            else:
                arcade.draw_lbwh_rectangle_outline(self.width / 2 - 320, self.height / 2 - 240, 640, 480, arcade.color.WHITE, 3)
                # Buttons
                bx, by, bw, bh = self.ui_rects["settings_ammo"]
                lvl_ammo = self.ease(self.hover_level.get("settings_ammo", 0.0))
                color_ammo = self.lerp_color(arcade.color.DARK_SPRING_GREEN, arcade.color.SPRING_GREEN, lvl_ammo)
                self.draw_scaled_rect(bx, by, bw, bh, color_ammo, lvl_ammo, scale_factor=0.12)
                arcade.draw_text("Unendlich Schüsse", bx + bw/2, by + bh/2,
                                 arcade.color.WHITE, 26, anchor_x="center", anchor_y="center")

                bx, by, bw, bh = self.ui_rects["settings_health"]
                lvl_hp = self.ease(self.hover_level.get("settings_health", 0.0))
                color_hp = self.lerp_color(arcade.color.DARK_SPRING_GREEN, arcade.color.SPRING_GREEN, lvl_hp)
                self.draw_scaled_rect(bx, by, bw, bh, color_hp, lvl_hp, scale_factor=0.13)
                arcade.draw_text("Unendlich Leben", bx + bw/2, by + bh/2,
                                 arcade.color.WHITE, 26, anchor_x="center", anchor_y="center")

                bx, by, bw, bh = self.ui_rects["settings_energy"]
                lvl_en = self.ease(self.hover_level.get("settings_energy", 0.0))
                color_en = self.lerp_color(arcade.color.DARK_SPRING_GREEN, arcade.color.SPRING_GREEN, lvl_en)
                self.draw_scaled_rect(bx, by, bw, bh, color_en, lvl_en, scale_factor=0.13)
                arcade.draw_text("Energie auffüllen", bx + bw/2, by + bh/2,
                                 arcade.color.WHITE, 26, anchor_x="center", anchor_y="center")

                bx, by, bw, bh = self.ui_rects["settings_coins"]
                lvl_co = self.ease(self.hover_level.get("settings_coins", 0.0))
                color_co = self.lerp_color(arcade.color.DARK_SPRING_GREEN, arcade.color.SPRING_GREEN, lvl_co)
                self.draw_scaled_rect(bx, by, bw, bh, color_co, lvl_co, scale_factor=0.13)
                arcade.draw_text("Unendlich Münzen", bx + bw/2, by + bh/2,
                                 arcade.color.WHITE, 26, anchor_x="center", anchor_y="center")

            bx, by, bw, bh = self.ui_rects["settings_back"]
            back_level = self.ease(self.hover_level.get("settings_back", 0.0))
            leave_color = self.lerp_color(arcade.color.GRAY, arcade.color.LIGHT_GRAY, back_level)
            self.draw_scaled_rect(bx, by, bw, bh, leave_color, back_level, scale_factor=0.15)
            arcade.draw_text("Abbruch",
                             bx + bw / 2, by + bh / 2,
                             arcade.color.WHITE, 26,
                             anchor_x="center", anchor_y="center")
            if self.admin_message:
                arcade.draw_text(self.admin_message,
                                 self.width / 2, self.height - 360,
                                 arcade.color.RED, 24,
                                 anchor_x="center")

        elif self.state == "shop":
            self.state = "game"
            return

        elif self.state == "gameover":

            self.draw_cached_text("gameover_title", "GAME OVER",
                                  self.width//2, self.height//2 + 40,
                                  arcade.color.RED, 50,
                                  anchor_x="center")
            bx, by, bw, bh = self.ui_rects["gameover_restart"]
            restart_level = self.ease(self.hover_level.get("gameover_restart", 0.0))
            restart_color = self.lerp_color(arcade.color.GRAY, arcade.color.LIGHT_GRAY, restart_level)
            self.draw_scaled_rect(bx, by, bw, bh, restart_color, restart_level, scale_factor=0.15)
            self.draw_cached_text("gameover_restart_label", "Restart",
                                  bx + bw / 2, by + bh / 2,
                                  arcade.color.WHITE, 30,
                                  anchor_x="center", anchor_y="center")
    @staticmethod
    def _normalize_name(name: str) -> str:
        # Sichtbar saubere Namen: ohne Steuerzeichen/Mehrfachspaces.
        cleaned = "".join(ch for ch in name if ch.isprintable() and ch not in "\r\n\t")
        cleaned = " ".join(cleaned.strip().split())
        return cleaned[:24]

    @staticmethod
    def _translate_error_message(code: str) -> str:
        mapping = {
            "name_taken": "Name vergeben",
            "auth_failed": "Ungültiges Passwort",
            "account_missing": "Kein Konto für diese IP",
            "account_exists": "Konto existiert bereits",
            "auth_invalid": "Ungültige Eingabe",
            "invalid_token": "Ungültiger Server-Token",
            "name_required": "Name erforderlich",
        }
        return mapping.get(code, code if code else "Unbekannter Fehler")

    def _submit_name_and_start(self):
        self.player_name = self._normalize_name(self.player_name) or "Spieler"
        self.name_confirmed = True
        if self.online_client and self.online_client.connected:
            self.online_client.send_name(self.player_name)
        self.setup_game()
        self.state = "lobby"
        self.lobby_timer = self.lobby_wait_time
        self.lobby_active_circle = -1
