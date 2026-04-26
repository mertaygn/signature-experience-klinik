"""
Telegram Export
Send enriched data summaries to Telegram bot.
"""

import requests
from typing import Optional
from rich.console import Console

import config
from database.db import Database

console = Console()


def send_telegram_message(text: str, chat_id: str = None, parse_mode: str = "HTML") -> bool:
    """Send a message via Telegram bot."""
    token = config.TELEGRAM_BOT_TOKEN
    chat = chat_id or config.TELEGRAM_CHAT_ID

    if not token or token == "your_telegram_bot_token_here":
        console.print("[yellow]Telegram bot token not configured.[/yellow]")
        return False

    if not chat or chat == "your_telegram_chat_id_here":
        console.print("[yellow]Telegram chat ID not configured.[/yellow]")
        return False

    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        response.raise_for_status()
        return True
    except requests.RequestException as e:
        console.print(f"[red]Telegram error: {e}[/red]")
        return False


def send_fair_summary(db: Database, fair_id: int) -> bool:
    """Send a summary of fair enrichment results to Telegram."""
    fair = None
    for f in db.get_all_fairs():
        if f["id"] == fair_id:
            fair = f
            break

    if not fair:
        return False

    stats = db.get_stats(fair_id)
    companies = db.get_all_enriched_data(fair_id)

    # Build summary message
    msg_parts = [
        f"🎯 <b>Fuar Lead Raporu</b>",
        f"📋 <b>{fair['name']}</b>",
        f"",
        f"📊 <b>Genel İstatistikler:</b>",
        f"  • Toplam firma: <b>{stats['total_companies']}</b>",
        f"  • E-posta bulunan: <b>{stats['with_email']}</b> "
        f"({stats['with_email']/stats['total_companies']*100:.0f}%)" if stats['total_companies'] else "",
        f"  • Telefon bulunan: <b>{stats['with_phone']}</b> "
        f"({stats['with_phone']/stats['total_companies']*100:.0f}%)" if stats['total_companies'] else "",
        f"  • Toplam kontak: <b>{stats['total_contacts']}</b>",
    ]

    # Top companies with most contacts
    companies_with_contacts = [(c, len(c.get("contacts", []))) for c in companies]
    companies_with_contacts.sort(key=lambda x: x[1], reverse=True)
    top_5 = companies_with_contacts[:5]

    if top_5:
        msg_parts.append("")
        msg_parts.append("🏆 <b>En Çok Kontak Bulunan 5 Firma:</b>")
        for c, count in top_5:
            emails = [ct["value"] for ct in c.get("contacts", []) if ct["contact_type"] == "email"]
            email_str = f" — {emails[0]}" if emails else ""
            msg_parts.append(f"  • <b>{c['name']}</b> ({count} kontak){email_str}")

    # Companies without any contacts
    no_contacts = sum(1 for c, count in companies_with_contacts if count == 0)
    if no_contacts > 0:
        msg_parts.append("")
        msg_parts.append(f"⚠️ {no_contacts} firma için kontak bulunamadı.")

    msg_parts.append("")
    msg_parts.append(f"🤖 <i>Ajan-Bot — Fuar Lead Generator</i>")

    message = "\n".join(msg_parts)

    # Telegram has a 4096 character limit
    if len(message) > 4000:
        message = message[:3990] + "\n..."

    return send_telegram_message(message)


def send_company_list(db: Database, fair_id: int, batch_size: int = 20) -> int:
    """
    Send detailed company list in batches to Telegram.
    Returns number of messages sent.
    """
    companies = db.get_all_enriched_data(fair_id)
    messages_sent = 0

    for i in range(0, len(companies), batch_size):
        batch = companies[i:i + batch_size]
        msg_parts = [f"📋 <b>Firma Listesi ({i+1}-{i+len(batch)}/{len(companies)})</b>\n"]

        for company in batch:
            contacts = company.get("contacts", [])
            emails = [c["value"] for c in contacts if c["contact_type"] == "email"]
            phones = [c["value"] for c in contacts if c["contact_type"] == "phone"]

            line = f"🏢 <b>{company['name']}</b>"
            if company.get("website"):
                line += f"\n    🌐 {company['website']}"
            if emails:
                line += f"\n    📧 {', '.join(emails[:2])}"
            if phones:
                line += f"\n    📞 {', '.join(phones[:2])}"
            line += "\n"
            msg_parts.append(line)

        message = "\n".join(msg_parts)
        if len(message) > 4000:
            message = message[:3990] + "\n..."

        if send_telegram_message(message):
            messages_sent += 1

        import time
        time.sleep(1)  # Rate limit

    return messages_sent
