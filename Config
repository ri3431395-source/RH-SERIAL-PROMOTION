import os

# --- Telegram credentials (from https://my.telegram.org) ---
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# --- Admin user IDs (comma separated in env, e.g. "123456,789012") ---
ADMIN_IDS = [int(x.strip()) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip()]

# --- Storage paths (mount a Railway Volume at /data for persistence) ---
DATA_DIR = os.environ.get("DATA_DIR", "/data")
DB_PATH = os.path.join(DATA_DIR, "bot.db")
WORK_DIR = os.path.join(DATA_DIR, "work")  # temp download/render folder

# --- Insertion points (in seconds, based on ORIGINAL main video timeline) ---
PROMO_TIME_1 = int(os.environ.get("PROMO_TIME_1", str(7 * 60)))   # 7 minutes
PROMO_TIME_2 = int(os.environ.get("PROMO_TIME_2", str(16 * 60)))  # 16 minutes

# --- Encoding settings (used only when re-encode fallback triggers) ---
TARGET_WIDTH = int(os.environ.get("TARGET_WIDTH", "1280"))
TARGET_HEIGHT = int(os.environ.get("TARGET_HEIGHT", "720"))
TARGET_FPS = int(os.environ.get("TARGET_FPS", "30"))
X264_PRESET = os.environ.get("X264_PRESET", "veryfast")  # ultrafast/superfast/veryfast/fast
X264_CRF = os.environ.get("X264_CRF", "23")

# Max file size we accept (Telegram hard cap via MTProto is ~2GB for normal accounts)
MAX_FILE_SIZE = int(os.environ.get("MAX_FILE_SIZE", str(2 * 1024 * 1024 * 1024)))

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(WORK_DIR, exist_ok=True)
