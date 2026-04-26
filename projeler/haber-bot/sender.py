import requests
import time
from datetime import datetime
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from database import log_sent_message, log_system_message

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# Her mesaj arası bekleme (rate limit için)
MSG_DELAY = 3.5
MAX_RETRY = 3


def send_message(text: str, parse_mode: str = "HTML", retry: int = 0) -> int | None:
    """Telegram'a mesaj gönder. Başarılıysa message_id döndür, değilse None."""
    url = f"{TELEGRAM_API}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": False,
    }
    try:
        response = requests.post(url, json=payload, timeout=20)
        data = response.json()

        if response.status_code == 200:
            msg_id = data.get("result", {}).get("message_id")
            return msg_id  # int veya None

        if response.status_code == 429 and retry < MAX_RETRY:
            wait = data.get("parameters", {}).get("retry_after", 30)
            print(f"[SENDER] ⏳ Rate limit — {wait}sn bekleniyor...")
            time.sleep(wait + 2)
            return send_message(text, parse_mode, retry + 1)

        print(f"[SENDER] ❌ Telegram hatası: {response.status_code} — {data.get('description', '')}")
        return None

    except Exception as e:
        print(f"[SENDER] ❌ Bağlantı hatası: {e}")
        return None


def format_article(article: dict) -> str:
    """Haberi satış aksiyonu formatında döndür."""
    title   = article.get("title", "Başlık yok")
    url     = article.get("url", "")
    source  = article.get("source", "")
    pub     = article.get("published")

    # Sinyal bilgisi
    sig_icon  = article.get("signal_icon", "🟠")
    sig_label = article.get("signal_label", "İZLE")
    sig_tag   = article.get("signal_tag", "")

    # Lead bilgisi
    lead = article.get("lead", {})
    event    = lead.get("event_name", "")
    country  = lead.get("country", "")
    industry = lead.get("industry", "")
    organizer = lead.get("organizer", "")
    reason   = lead.get("reason", "")
    strategy = lead.get("strategy", {})
    offer    = lead.get("offer", {})

    # Kaynak
    source_clean = source.split(":")[0].strip() if ":" in source else source

    # Yayın saati
    time_str = ""
    if pub:
        try:
            from datetime import timezone
            local = pub.astimezone()
            time_str = local.strftime("%d/%m %H:%M")
        except Exception:
            pass

    lines = []

    # ── Başlık satırı ─────────────────────────────────────────────────────
    tag_str = f" — {sig_tag}" if sig_tag else ""
    lines.append(f"{sig_icon} <b>{sig_label}{tag_str}</b>")

    # ── Haber başlığı (link) ──────────────────────────────────────────────
    if url:
        lines.append(f'📰 <a href="{url}">{title}</a>')
    else:
        lines.append(f"📰 {title}")

    # ── Lokasyon / Event bilgisi ──────────────────────────────────────────
    loc_parts = []
    if event:
        loc_parts.append(event)
    if country:
        loc_parts.append(country)
    if loc_parts:
        lines.append(f"\n📍 {' / '.join(loc_parts)}")

    if industry:
        lines.append(f"🏭 Sektör: {industry}")
    if organizer:
        lines.append(f"🏢 Organizatör: {organizer}")

    # ── NEDEN ÖNEMLİ ─────────────────────────────────────────────────────
    if reason:
        lines.append(f"\n💰 <b>NEDEN ÖNEMLİ:</b>\n{reason}")

    # ── KİME SATARSIN ────────────────────────────────────────────────────
    if strategy:
        tip = strategy.get("tip", "")
        if tip:
            lines.append(f"\n🎯 <b>HEDEF:</b> {tip}")

    # ── NE SATARSIN ──────────────────────────────────────────────────────
    if offer:
        stand_type = offer.get("stand", "")
        highlight  = offer.get("öne_çıkan", "")
        if stand_type:
            lines.append(f"\n📦 <b>TEKLİF:</b>\n• {stand_type}")
        if highlight:
            lines.append(f"• {highlight}")

    # ── AKSİYON ──────────────────────────────────────────────────────────
    if strategy:
        aksiyon = strategy.get("aksiyon", "")
        if aksiyon:
            lines.append(f"\n🚀 <b>AKSİYON:</b>\n→ {aksiyon}")

    # ── Alt bilgi ────────────────────────────────────────────────────────
    meta = []
    if source_clean:
        meta.append(f"📡 {source_clean}")
    if time_str:
        meta.append(f"🕐 {time_str}")
    if meta:
        lines.append("\n" + "  |  ".join(meta))

    return "\n".join(lines)


def send_daily_digest(translated_articles: list[dict], raw_articles: list[dict] = None) -> int:
    """Günlük özet — her haber ayrı mesaj olarak gönderilir ve loglanır."""
    if not translated_articles:
        print("[SENDER] Gönderilecek haber yok.")
        return 0

    # raw_articles yoksa boş dict listesi kullan
    if raw_articles is None:
        raw_articles = [{}] * len(translated_articles)

    today = datetime.now().strftime("%-d %B %Y")
    tr_months = {
        "January": "Ocak", "February": "Şubat", "March": "Mart",
        "April": "Nisan", "May": "Mayıs", "June": "Haziran",
        "July": "Temmuz", "August": "Ağustos", "September": "Eylül",
        "October": "Ekim", "November": "Kasım", "December": "Aralık",
    }
    for en, tr in tr_months.items():
        today = today.replace(en, tr)

    # ── Sinyal dağılımı ───────────────────────────────────────────────────
    opp_count = sum(1 for a in translated_articles if a.get("signal_type") == "opportunity")
    watch_count = sum(1 for a in translated_articles if a.get("signal_type") == "watch")

    # ── Başlık mesajı ──────────────────────────────────────────────────────
    parts = []
    if opp_count:
        parts.append(f"🟢 {opp_count} Fırsat")
    if watch_count:
        parts.append(f"🟠 {watch_count} İzle")
    signal_line = "  |  ".join(parts) if parts else "Bugün sinyal yok"

    header = (
        f"🏗️ <b>STAND & EXPO — İş Fırsatı Raporu</b>\n"
        f"📅 {today}\n"
        f"📊 {signal_line}"
    )
    header_msg_id = send_message(header)
    log_system_message(header, header_msg_id is not None, header_msg_id, "header")
    time.sleep(MSG_DELAY)

    # ── Her haberi ayrı mesaj olarak gönder ───────────────────────────────
    sent = 0
    for i, article in enumerate(translated_articles):
        msg = format_article(article)

        # Telegram 4096 karakter limiti
        if len(msg) > 4000:
            msg = msg[:3990] + "…"

        raw = raw_articles[i] if i < len(raw_articles) else {}

        sig_icon = article.get("signal_icon", "🟡")
        print(f"[SENDER] {sig_icon} Gönderiliyor {i+1}/{len(translated_articles)}: {article['title'][:60]}...")
        msg_id = send_message(msg)
        success = msg_id is not None

        # Mesajı tam detayıyla logla
        log_sent_message(
            url=article.get("url", ""),
            raw_article=raw,
            translated_article=article,
            formatted_message=msg,
            send_success=success,
            telegram_message_id=msg_id,
            message_type=article.get("signal_type", "article"),
        )

        if success:
            sent += 1

        time.sleep(MSG_DELAY)

    # ── Kapanış mesajı ────────────────────────────────────────────────────
    footer = (
        f"✅ <b>{sent} sinyal iletildi.</b>\n"
        f"🤖 <i>Evreka Stand — Fuar İş Fırsatı Dedektörü</i>"
    )
    footer_msg_id = send_message(footer)
    log_system_message(footer, footer_msg_id is not None, footer_msg_id, "footer")

    print(f"[SENDER] ✅ {sent}/{len(translated_articles)} haber gönderildi.")
    return sent


def send_fallback_digest(translated_articles: list[dict], raw_articles: list[dict] = None) -> int:
    """
    Fallback özet — yeni haber yokken son 48 saatin en iyileri gönderilir.
    Başlık 'Öne Çıkan Haberler' olarak değiştirilir.
    """
    if not translated_articles:
        print("[SENDER] Fallback için gönderilecek haber yok.")
        return 0

    if raw_articles is None:
        raw_articles = [{}] * len(translated_articles)

    today = datetime.now().strftime("%-d %B %Y")
    tr_months = {
        "January": "Ocak", "February": "Şubat", "March": "Mart",
        "April": "Nisan", "May": "Mayıs", "June": "Haziran",
        "July": "Temmuz", "August": "Ağustos", "September": "Eylül",
        "October": "Ekim", "November": "Kasım", "December": "Aralık",
    }
    for en, tr in tr_months.items():
        today = today.replace(en, tr)

    # ── Başlık mesajı (fallback) ───────────────────────────────────────────
    header = (
        f"📌 <b>FUAR DÜNYASI — Öne Çıkan Sinyaller</b>\n"
        f"📅 {today}\n"
        f"<i>Bugün yeni sinyal bulunamadı. Son 72 saatin en ilgili {len(translated_articles)} sinyali:</i>"
    )
    header_msg_id = send_message(header)
    log_system_message(header, header_msg_id is not None, header_msg_id, "fallback_header")
    time.sleep(MSG_DELAY)

    # ── Her haberi ayrı mesaj olarak gönder ───────────────────────────────
    sent = 0
    for i, article in enumerate(translated_articles):
        msg = format_article(article)
        if len(msg) > 4000:
            msg = msg[:3990] + "…"

        raw = raw_articles[i] if i < len(raw_articles) else {}

        print(f"[SENDER] (Fallback) Gönderiliyor {i+1}/{len(translated_articles)}: {article['title'][:60]}...")
        msg_id = send_message(msg)
        success = msg_id is not None

        log_sent_message(
            url=article.get("url", ""),
            raw_article=raw,
            translated_article=article,
            formatted_message=msg,
            send_success=success,
            telegram_message_id=msg_id,
            message_type="fallback_article",
        )

        if success:
            sent += 1
        time.sleep(MSG_DELAY)

    # ── Kapanış mesajı ────────────────────────────────────────────────────
    footer = (
        f"🔁 <b>{sent} sinyal iletildi.</b>\n"
        f"🤖 <i>Evreka Stand — Fuar İş Fırsatı Dedektörü</i>"
    )
    footer_msg_id = send_message(footer)
    log_system_message(footer, footer_msg_id is not None, footer_msg_id, "fallback_footer")

    print(f"[SENDER] ✅ (Fallback) {sent}/{len(translated_articles)} haber gönderildi.")
    return sent


def send_test_message() -> bool:
    """Test mesajı gönder."""
    msg = (
        "🤖 <b>Fuar Haber Botu — Test Mesajı</b>\n\n"
        "✅ Bot başarıyla bağlandı!\n"
        "📅 Haberler her gün saat 08:00'de gönderilecek.\n"
        "📋 Her haber başlık + özet + kaynak bilgisiyle ayrı ayrı iletilecek.\n\n"
        "<i>Evreka Stand — Global Fuar Haber Ajansı</i>"
    )
    msg_id = send_message(msg)
    success = msg_id is not None
    log_system_message(msg, success, msg_id, "test")

    if success:
        print("[SENDER] ✅ Test mesajı gönderildi!")
    else:
        print("[SENDER] ❌ Test mesajı gönderilemedi!")
    return success
