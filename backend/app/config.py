"""Central configuration. Everything overridable through environment / .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
CSV_PATH = Path(os.getenv("CSV_PATH", r"D:\Panaroma\Test_sales_dataset(ecommerce_sales_dataset).csv"))

# --- database: XAMPP MariaDB (MySQL-compatible) -----------------------------
# Two accounts on purpose (least privilege): the web app connects as DB_USER, which can only read the data views and
# touch its own app tables.  Schema changes, bulk loads and admin tools use DB_OWNER_USER.  Passwords live in backend/.env.
XAMPP_DIR = Path(os.getenv("XAMPP_DIR", r"D:\IDE\xampp"))
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3307"))            # XAMPP's my.ini uses 3307 (3306 is taken by another MySQL on this PC)
DB_NAME = os.getenv("DB_NAME", "panorama")
DB_USER = os.getenv("DB_USER", "panorama_app")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_OWNER_USER = os.getenv("DB_OWNER_USER", "panorama_owner")
DB_OWNER_PASSWORD = os.getenv("DB_OWNER_PASSWORD", "")
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "8"))
MIGRATIONS_DIR = BASE_DIR / "migrations"
BACKUP_DIR = BASE_DIR.parent / "backups"

# --- auth ---------------------------------------------------------------
_secret_file = DATA_DIR / ".jwt_secret"
if not _secret_file.exists():
    _secret_file.write_text(os.urandom(32).hex())
JWT_SECRET = os.getenv("JWT_SECRET", _secret_file.read_text().strip())
JWT_ALG = "HS256"
JWT_TTL_HOURS = int(os.getenv("JWT_TTL_HOURS", "8"))          # absolute session lifetime
SESSION_IDLE_MINUTES = int(os.getenv("SESSION_IDLE_MINUTES", "60"))  # sliding idle timeout
SESSION_COOKIE = "panorama_session"
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "0") == "1"           # set to 1 when served over HTTPS
DEMO_MODE = os.getenv("DEMO_MODE", "1") == "1"                    # shows demo accounts (with passwords) on the login screen
MAX_LOGIN_FAILS = 5
LOGIN_LOCK_SECONDS = 300

# --- LLM / embeddings (Ollama, fully local) -----------------------------
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
CHAT_MODEL = os.getenv("CHAT_MODEL", "qwen2.5:7b")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "180"))

# --- misc ---------------------------------------------------------------
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "300"))
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
