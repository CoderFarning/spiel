from pathlib import Path

# ---------------- SETTINGS ----------------
SCREEN_TITLE = "Survival Map"
SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080
MAP_WIDTH = 10000
MAP_HEIGHT = 10000
# Assets liegen jetzt im selben Ordner wie diese Datei
ASSET_BASE = Path(__file__).resolve().parent
IMG_DIR = ASSET_BASE            # Bilder liegen jetzt direkt hier
SOUND_DIR = ASSET_BASE          # Sounds liegen jetzt direkt hier

PLAYER_WIDTH = 180
PLAYER_HEIGHT = 240
PLAYER_SPEED = 145         # px/s

SPAWN_INTERVAL = 3.0
WAVE_DURATION = 30

ENEMY_SPEED = 95           # px/s
MINIMAP_SCALE = 0.05

SHOT_RADIUS = 500
MAX_SHOTS = 30.0
EXPLOSION_DURATION = 0.25
PORTAL_RADIUS = 140
PORTAL_COOLDOWN = 0.4
AMMO_COST = 2
