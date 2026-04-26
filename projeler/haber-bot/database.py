import sqlite3
import hashlib
import os
from datetime import datetime, timedelta
from config import DB_CLEANUP_DAYS

DB_PATH = os.path.join(os.path.dirname(__file__), "news.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Veritabanı ve tabloları oluştur."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS seen_articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url_hash TEXT UNIQUE NOT NULL,
            title TEXT,
            source TEXT,
            seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Bot durumu (son çalışma tarihi vb.)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bot_state (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    # Gönderilen mesaj kayıtları (debug + inceleme)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sent_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url_hash TEXT,
            url TEXT,
            raw_article TEXT,
            translated_article TEXT,
            formatted_message TEXT,
            send_success INTEGER DEFAULT 0,
            telegram_message_id INTEGER,
            message_type TEXT DEFAULT 'article',
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
    print("[DB] Veritabanı hazır.")


def url_hash(url: str) -> str:
    """URL'nin MD5 hash'ini döndür."""
    return hashlib.md5(url.encode("utf-8")).hexdigest()


def is_seen(url: str) -> bool:
    """Haber daha önce gönderildi mi?"""
    conn = get_connection()
    cursor = conn.cursor()
    h = url_hash(url)
    cursor.execute("SELECT 1 FROM seen_articles WHERE url_hash = ?", (h,))
    result = cursor.fetchone()
    conn.close()
    return result is not None


def mark_seen(url: str, title: str, source: str):
    """Haberi görüldü olarak işaretle."""
    conn = get_connection()
    cursor = conn.cursor()
    h = url_hash(url)
    try:
        cursor.execute(
            "INSERT OR IGNORE INTO seen_articles (url_hash, title, source) VALUES (?, ?, ?)",
            (h, title, source),
        )
        conn.commit()
    except Exception as e:
        print(f"[DB] Kayıt hatası: {e}")
    finally:
        conn.close()


def cleanup_old_records():
    """Eski kayıtları temizle."""
    threshold = datetime.now() - timedelta(days=DB_CLEANUP_DAYS)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM seen_articles WHERE seen_at < ?",
        (threshold.strftime("%Y-%m-%d %H:%M:%S"),),
    )
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    if deleted > 0:
        print(f"[DB] {deleted} eski kayıt silindi.")


def log_sent_message(
    url: str,
    raw_article: dict,
    translated_article: dict,
    formatted_message: str,
    send_success: bool,
    telegram_message_id: int | None = None,
    message_type: str = "article",
):
    """Gönderilen mesajı tüm detaylarıyla kaydet."""
    import json

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO sent_messages
               (url_hash, url, raw_article, translated_article,
                formatted_message, send_success, telegram_message_id, message_type)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                url_hash(url) if url else None,
                url,
                json.dumps(raw_article, ensure_ascii=False, default=str),
                json.dumps(translated_article, ensure_ascii=False, default=str),
                formatted_message,
                1 if send_success else 0,
                telegram_message_id,
                message_type,
            ),
        )
        conn.commit()
    except Exception as e:
        print(f"[DB] Mesaj kayıt hatası: {e}")
    finally:
        conn.close()


def log_system_message(
    formatted_message: str,
    send_success: bool,
    telegram_message_id: int | None = None,
    message_type: str = "header",
):
    """Başlık / kapanış gibi sistem mesajlarını kaydet."""
    import json

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO sent_messages
               (url_hash, url, raw_article, translated_article,
                formatted_message, send_success, telegram_message_id, message_type)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                None, None,
                json.dumps({}, ensure_ascii=False),
                json.dumps({}, ensure_ascii=False),
                formatted_message,
                1 if send_success else 0,
                telegram_message_id,
                message_type,
            ),
        )
        conn.commit()
    except Exception as e:
        print(f"[DB] Sistem mesajı kayıt hatası: {e}")
    finally:
        conn.close()


def get_sent_messages(limit: int = 50, only_failed: bool = False) -> list[dict]:
    """Gönderilen mesajları listele (inceleme amaçlı)."""
    import json

    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM sent_messages"
    if only_failed:
        query += " WHERE send_success = 0"
    query += " ORDER BY sent_at DESC LIMIT ?"

    cursor.execute(query, (limit,))
    rows = cursor.fetchall()
    conn.close()

    results = []
    for row in rows:
        r = dict(row)
        r["raw_article"] = json.loads(r["raw_article"]) if r["raw_article"] else {}
        r["translated_article"] = json.loads(r["translated_article"]) if r["translated_article"] else {}
        results.append(r)
    return results


def get_last_run_date() -> str | None:
    """Son çalışma tarihini döndür (YYYY-MM-DD)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM bot_state WHERE key = 'last_run_date'")
    row = cursor.fetchone()
    conn.close()
    return row["value"] if row else None


def set_last_run_date(date_str: str):
    """Son çalışma tarihini kaydet (YYYY-MM-DD)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO bot_state (key, value) VALUES ('last_run_date', ?)",
        (date_str,),
    )
    conn.commit()
    conn.close()
