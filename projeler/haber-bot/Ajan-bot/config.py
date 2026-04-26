"""
Ajan-Bot Configuration — Haber-Bot Entegrasyonu
Fuar Lead Generator — Ana bot ile paylaşılan ortam değişkenleri.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Ana bot'un .env dosyasını yükle
HABER_BOT_DIR = Path(__file__).parent.parent  # haber-bot/
load_dotenv(HABER_BOT_DIR / ".env")

# Kendi .env dosyasını da yükle (override)
load_dotenv(Path(__file__).parent / ".env", override=True)

# ─── Base Paths ──────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATA_DIR = HABER_BOT_DIR / "data"  # Paylaşılan data klasörü
EXPORT_DIR = HABER_BOT_DIR / "exports"
DB_PATH = DATA_DIR / "ajan_bot.db"

# Create directories
DATA_DIR.mkdir(exist_ok=True)
EXPORT_DIR.mkdir(exist_ok=True)

# ─── API Keys ────────────────────────────────────────────────
HUNTER_API_KEY = os.getenv("HUNTER_API_KEY", "")
APOLLO_API_KEY = os.getenv("APOLLO_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ─── Scraper Settings ────────────────────────────────────────
REQUEST_TIMEOUT = 10
REQUEST_DELAY = 0.5
MAX_RETRIES = 1
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# ─── Enrichment Settings ─────────────────────────────────────
HUNTER_FREE_LIMIT = 25
ENRICHMENT_BATCH_SIZE = 10
ENRICHMENT_DELAY = 3

# ─── Email Patterns ──────────────────────────────────────────
EMAIL_PATTERNS = [
    "{first}.{last}@{domain}",
    "{first}{last}@{domain}",
    "{f}{last}@{domain}",
    "{first}@{domain}",
    "{last}@{domain}",
]

# ─── Contact Page Keywords ───────────────────────────────────
CONTACT_PAGE_KEYWORDS = {
    "tr": ["iletisim", "iletişim", "bize-ulasin", "bize-ulaşın", "kontak", "contact"],
    "en": ["contact", "contact-us", "get-in-touch", "reach-us"],
}

# ─── Supported Fairs ─────────────────────────────────────────
SUPPORTED_FAIRS = {
    "idef": {
        "name": "IDEF - International Defence Exhibition",
        "url": "https://www.idef.com.tr",
        "scraper": "idef",
    },
    "saha_expo": {
        "name": "SAHA EXPO - Defence, Aviation & Space Industry Fair",
        "url": "https://sahaexpo.com",
        "scraper": "saha_expo",
    },
    "win_eurasia": {
        "name": "WIN EURASIA - Industry Fair",
        "url": "https://www.win-eurasia.com",
        "scraper": "generic",
    },
}
