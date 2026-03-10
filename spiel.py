import arcade
import math

# ---------------- SETTINGS ----------------
SCREEN_TITLE = "Survival Map"
MAP_WIDTH = 10000
MAP_HEIGHT = 10000

PLAYER_WIDTH = 300
PLAYER_HEIGHT = 168
PLAYER_SPEED = 15

SPAWN_INTERVAL = 2.0
WAVE_DURATION = 30

ENEMY_SPEED = 5
MINIMAP_SCALE = 0.05

SHOT_RADIUS = 500
MAX_SHOTS = 30
AMMO_REWARD_PER_WAVE = 30
EXPLOSION_DURATION = 0.25

# ---------------- ENEMY ----------------
class Enemy(arcade.Sprite):
    def __init__(self, image):
        super().__init__(image, scale=0.5)
        self.base_speed = ENEMY_SPEED
        self.is_dying = False
        self.death_timer = 0.0

# ---------------- GAME ----------------
class SurvivalGame(arcade.Window):

    def __init__(self):
        super().__init__(fullscreen=True, title=SCREEN_TITLE)
        arcade.set_background_color(arcade.color.DARK_GREEN)

        self.state = "menu"
        self.camera = arcade.Camera2D()
        self.keys = set()

        self.wave_active = False
        self.wave_timer = 0
        self.spawn_timer = 0
        self.wave_number = 1
        self.current_spawn_interval = SPAWN_INTERVAL
        self.current_enemy_speed = ENEMY_SPEED
        self.wave_reward_given = False

        self.player_health = 100
        self.shots_left = MAX_SHOTS

        self.start_button = None
        self.wave_button = None
        self.hit_sound = arcade.load_sound("getroffen.wav")

        self.setup_game()

    # ---------------- SETUP ----------------
    def setup_game(self):
        self.player_list = arcade.SpriteList()
        self.enemies = arcade.SpriteList()
        self.spawner_list = arcade.SpriteList()

        self.player = arcade.Sprite("spieler.png")
        self.player.width = PLAYER_WIDTH
        self.player.height = PLAYER_HEIGHT
        self.player.center_x = 0
        self.player.center_y = 0
        self.player_list.append(self.player)

        self.player_health = 100
        self.shots_left = MAX_SHOTS

        positions = [
            (-MAP_WIDTH//2, -MAP_HEIGHT//2),
            (MAP_WIDTH//2, -MAP_HEIGHT//2),
            (-MAP_WIDTH//2, MAP_HEIGHT//2),
            (MAP_WIDTH//2, MAP_HEIGHT//2)
        ]

        self.spawners = []
        for pos in positions:
            spawner = arcade.Sprite("spawner.png")
            spawner.center_x, spawner.center_y = pos
            self.spawner_list.append(spawner)
            self.spawners.append(spawner)

        self.wave_active = False
        self.wave_timer = 0
        self.spawn_timer = 0
        self.wave_number = 1
        self.current_spawn_interval = SPAWN_INTERVAL
        self.current_enemy_speed = ENEMY_SPEED
        self.wave_reward_given = False

    # ---------------- INPUT ----------------
    def on_key_press(self, key, modifiers):
        self.keys.add(key)

        if self.state == "game":
            if key == arcade.key.SPACE and self.shots_left > 0:
                self.radius_shot()

    def on_key_release(self, key, modifiers):
        self.keys.discard(key)

    def on_mouse_press(self, x, y, button, modifiers):

        if self.state == "menu" and self.start_button:
            bx, by, bw, bh = self.start_button
            if bx <= x <= bx + bw and by <= y <= by + bh:
                self.setup_game()
                self.state = "game"

        elif self.state == "game":

            bx, by, bw, bh = self.wave_button
            if bx <= x <= bx + bw and by <= y <= by + bh:
                if not self.wave_active:
                    self.wave_active = True
                    self.wave_timer = 0
                    self.spawn_timer = 0

        elif self.state == "gameover":
            self.state = "menu"

    # ---------------- RADIUS SHOT ----------------
    def radius_shot(self):
        self.shots_left -= 1

        enemies_to_kill = []
        for enemy in self.enemies:
            dist = arcade.get_distance_between_sprites(self.player, enemy)
            if dist <= SHOT_RADIUS:
                enemies_to_kill.append(enemy)

        for enemy in enemies_to_kill:
            enemy.kill()

    # ---------------- UPDATE ----------------
    def on_update(self, delta_time):

        if self.state != "game":
            return

        # Movement
        self.player.change_x = 0
        self.player.change_y = 0

        if arcade.key.UP in self.keys:
            self.player.change_y = PLAYER_SPEED
        if arcade.key.DOWN in self.keys:
            self.player.change_y = -PLAYER_SPEED
        if arcade.key.LEFT in self.keys:
            self.player.change_x = -PLAYER_SPEED
        if arcade.key.RIGHT in self.keys:
            self.player.change_x = PLAYER_SPEED

        self.player.center_x += self.player.change_x
        self.player.center_y += self.player.change_y

        # Map Grenzen
        self.player.center_x = max(-MAP_WIDTH//2, min(MAP_WIDTH//2, self.player.center_x))
        self.player.center_y = max(-MAP_HEIGHT//2, min(MAP_HEIGHT//2, self.player.center_y))

        # Wave System
        if self.wave_active:
            self.wave_timer += delta_time
            self.spawn_timer += delta_time

            if self.spawn_timer >= SPAWN_INTERVAL:
                self.spawn_enemies()
                self.spawn_timer = 0

            if self.wave_timer >= WAVE_DURATION:
                self.wave_active = False

        # Enemy Update
        for enemy in self.enemies:

            dx = self.player.center_x - enemy.center_x
            dy = self.player.center_y - enemy.center_y
            dist = math.hypot(dx, dy)

            if dist > 0:
                enemy.center_x += (dx / dist) * ENEMY_SPEED
                enemy.center_y += (dy / dist) * ENEMY_SPEED

            enemy.center_x = max(-MAP_WIDTH//2, min(MAP_WIDTH//2, enemy.center_x))
            enemy.center_y = max(-MAP_HEIGHT//2, min(MAP_HEIGHT//2, enemy.center_y))

            if arcade.check_for_collision(enemy, self.player):
                enemy.kill()
                self.player_health -= 1  # nur 1 Schaden

        if self.player_health <= 0:
            self.state = "gameover"

        self.camera.position = (self.player.center_x, self.player.center_y)

    # ---------------- SPAWN ----------------
    def spawn_enemies(self):
        images = ["gegner.png", "gegner2.png", "gegner3.png", "gegner4.png"]

        for i, spawner in enumerate(self.spawners):
            enemy = Enemy(images[i])
            enemy.center_x = spawner.center_x
            enemy.center_y = spawner.center_y
            self.enemies.append(enemy)

    # ---------------- DRAW ----------------
    def on_draw(self):
        self.clear()

        if self.state == "menu":

            arcade.draw_text("SURVIVAL MAP",
                             self.width/2, self.height/2+150,
                             arcade.color.WHITE, 60,
                             anchor_x="center")

            bw, bh = 300, 80
            bx = self.width//2 - bw//2
            by = self.height//2 - bh//2

            arcade.draw_lbwh_rectangle_filled(bx, by, bw, bh, arcade.color.GRAY)
            arcade.draw_text("START",
                             self.width//2, self.height//2,
                             arcade.color.WHITE, 30,
                             anchor_x="center", anchor_y="center")

            self.start_button = (bx, by, bw, bh)

        elif self.state == "game":

            with self.camera.activate():
                self.spawner_list.draw()
                self.enemies.draw()
                self.player_list.draw()

            # Wave Button
            bw, bh = 250, 50
            bx, by = 20, 20

            arcade.draw_lbwh_rectangle_filled(bx, by, bw, bh, arcade.color.GRAY)
            arcade.draw_text("Welle starten",
                             bx + bw/2, by + bh/2,
                             arcade.color.WHITE, 20,
                             anchor_x="center", anchor_y="center")

            self.wave_button = (bx, by, bw, bh)

            # Anzeigen
            arcade.draw_text(f"❤️ Leben: {self.player_health}",
                             20, self.height-40,
                             arcade.color.WHITE, 20)

            arcade.draw_text(f"🔫 Schüsse: {self.shots_left}",
                             20, self.height-70,
                             arcade.color.WHITE, 20)

            # MiniMap
            minimap_w = MAP_WIDTH * MINIMAP_SCALE
            minimap_h = MAP_HEIGHT * MINIMAP_SCALE
            minimap_x = self.width - minimap_w - 20
            minimap_y = 20

            arcade.draw_lbwh_rectangle_filled(minimap_x, minimap_y,
                                              minimap_w, minimap_h,
                                              arcade.color.DARK_SLATE_GRAY)

            px = minimap_x + (self.player.center_x + MAP_WIDTH/2) * MINIMAP_SCALE
            py = minimap_y + (self.player.center_y + MAP_HEIGHT/2) * MINIMAP_SCALE
            arcade.draw_circle_filled(px, py, 5, arcade.color.BLUE)

            for enemy in self.enemies:
                ex = minimap_x + (enemy.center_x + MAP_WIDTH/2) * MINIMAP_SCALE
                ey = minimap_y + (enemy.center_y + MAP_HEIGHT/2) * MINIMAP_SCALE
                arcade.draw_circle_filled(ex, ey, 4, arcade.color.RED)

        elif self.state == "gameover":

            arcade.draw_text("GAME OVER",
                             self.width//2, self.height//2,
                             arcade.color.RED, 50,
                             anchor_x="center")

# ---------------- START ----------------
if __name__ == "__main__":
    game = SurvivalGame()
    arcade.run()
