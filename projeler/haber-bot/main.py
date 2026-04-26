#!/usr/bin/env python3
"""
Stand & Expo İş Fırsatı Dedektörü — Ana Giriş Noktası

Kullanım:
  HABER BOTU:
    python main.py           → Scheduler'ı başlat (günlük 09:00)
    python main.py --now     → Şimdi çalıştır (test için)
    python main.py --test    → Sadece Telegram bağlantısını test et
    python main.py --once    → LaunchAgent modu: 1 kez çalıştır, çık

  RADAR (Proaktif Satış):
    python main.py radar                → Fuar takvimi + aksiyon zonları
    python main.py radar --send         → Telegram'a radar raporu gönder
    python main.py radar --scrape       → Altın zaman fuarlarının exhibitor'ını çek

  DISCOVER (Global Fuar Keşfi):
    python main.py discover                      → 20 ülke tara
    python main.py discover --country Germany     → Tek ülke tara
    python main.py discover --details             → Tarih bilgilerini de çek

  AJAN-BOT (Lead Keşif):
    python main.py find "FUAR ADI"              → Fuar bul + exhibitor çek
    python main.py find "FUAR ADI" --enrich     → + kontak zenginleştir
    python main.py enrich SLUG --limit 10       → Kontak zenginleştir
    python main.py leads                        → Lead istatistikleri
    python main.py search SORGU                 → Firma ara
"""

import sys
import os
import time
import logging
import schedule
from datetime import datetime, date

from config import DAILY_SEND_HOUR, DAILY_SEND_MINUTE, TELEGRAM_CHAT_ID
from database import init_db, get_last_run_date, set_last_run_date
from sender import send_test_message
from job import run_job

# ── Ajan-Bot path'ini ekle ─────────────────────────────────────────────────
AJAN_BOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Ajan-bot")
if AJAN_BOT_DIR not in sys.path:
    sys.path.insert(0, AJAN_BOT_DIR)

# ── Loglama ─────────────────────────────────────────────────────────────────
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "bot.log"), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("haber-bot")


def check_config():
    """Konfigürasyonu doğrula."""
    if not TELEGRAM_CHAT_ID or TELEGRAM_CHAT_ID == "BURAYA_CHAT_ID_YAZIN":
        logger.error("❌ HATA: .env dosyasına TELEGRAM_CHAT_ID eklenmedi!")
        return False
    return True


def run_job_once():
    """Bugün daha önce çalıştırılmadıysa çalıştır."""
    today = date.today().isoformat()
    last = get_last_run_date()
    if last == today:
        logger.info(f"⏭️  Bugün ({today}) zaten çalıştırıldı, atlanıyor.")
        return

    logger.info(f"🚀 Günlük iş başlatılıyor ({today})...")
    try:
        run_job()
        set_last_run_date(today)
        logger.info(f"✅ Bugün ({today}) başarıyla tamamlandı.")
    except Exception as e:
        logger.error(f"❌ İş başarısız oldu: {e}", exc_info=True)


# ═══════════════════════════════════════════════════════════════════════════
# AJAN-BOT KOMUTLARI
# ═══════════════════════════════════════════════════════════════════════════

def ajan_find(fair_name: str, do_enrich: bool = False, limit: int = None):
    """Fuar bul + exhibitor listesi çek."""
    from ajan_bridge import AjanBot
    from rich.console import Console
    from rich.table import Table
    from rich import box

    Database = AjanBot.get_database()
    SmartFairDiscoverer = AjanBot.get_discoverer()

    console = Console()
    console.print(f"\n[bold magenta]🕵️ Ajan-Bot: '{fair_name}' aranıyor...[/bold magenta]\n")

    discoverer = SmartFairDiscoverer()
    result = discoverer.discover_and_scrape(fair_name)

    companies = result["companies"]
    if not companies:
        console.print(f"\n[red]❌ '{fair_name}' için katılımcı bulunamadı.[/red]")
        return

    # DB'ye kaydet
    with Database() as db:
        slug = fair_name.lower().replace(" ", "_").replace("-", "_")[:30]
        fair_id = db.upsert_fair(slug=slug, name=fair_name, url=result.get("fair_url"))

        saved = 0
        for company in companies:
            data = company.to_dict()
            db.upsert_company(
                fair_id=fair_id,
                name=data["name"],
                website=data.get("website"),
                booth_number=data.get("booth_number"),
                sector=data.get("sector"),
                country=data.get("country"),
                city=data.get("city"),
                description=data.get("description"),
                email=data.get("email"),
                phone=data.get("phone"),
                address=data.get("address"),
            )
            saved += 1

        console.print(f"\n[green]✓ {saved} firma veritabanına kaydedildi[/green]")

        # Enrich
        if do_enrich:
            Enricher = AjanBot.get_enricher()
            console.print(f"\n[bold]═══ Kontak Zenginleştirme ═══[/bold]")
            enricher = Enricher(db)
            enricher.enrich_fair(fair_id=fair_id, use_hunter=False, limit=limit)

        # Tablo
        table = Table(title=f"📋 {fair_name} — İlk 20 Firma", box=box.ROUNDED)
        table.add_column("#", style="dim", width=4)
        table.add_column("Firma", style="bold")
        table.add_column("Web Sitesi", style="cyan")
        table.add_column("Ülke")

        for i, company in enumerate(companies[:20], 1):
            table.add_row(
                str(i),
                (company.name or "")[:45],
                (company.website or "")[:45],
                (company.country or ""),
            )

        if len(companies) > 20:
            table.add_row("...", f"... ve {len(companies) - 20} firma daha", "", "")

        console.print(table)
        console.print(f"\n[bold]Sonraki adımlar:[/bold]")
        console.print(f"  [cyan]python main.py enrich {slug} --limit 10[/cyan]  ← Kontak bul")
        console.print(f"  [cyan]python main.py export {slug}[/cyan]             ← Excel'e aktar")


def ajan_enrich(fair_slug: str, limit: int = None):
    """Firma kontaklarını zenginleştir."""
    from ajan_bridge import AjanBot
    from rich.console import Console
    Database = AjanBot.get_database()
    Enricher = AjanBot.get_enricher()
    console = Console()

    with Database() as db:
        fair = db.get_fair(fair_slug)
        if not fair:
            # Partial match
            for f in db.get_all_fairs():
                if fair_slug.lower() in f["slug"].lower() or fair_slug.lower() in f["name"].lower():
                    fair = f
                    break
        if not fair:
            console.print(f"[red]Fuar '{fair_slug}' bulunamadı. Önce 'find' çalıştırın.[/red]")
            return

        enricher_obj = Enricher(db)
        enricher_obj.enrich_fair(fair_id=fair["id"], use_hunter=False, limit=limit)


def ajan_export(fair_slug: str):
    """Excel'e aktar."""
    from ajan_bridge import AjanBot
    from rich.console import Console
    Database = AjanBot.get_database()
    console = Console()
    console.print("[yellow]Excel export henüz bridge üzerinden desteklenmiyor. Doğrudan Ajan-bot kullanın.[/yellow]")
    return

    with Database() as db:
        fair = db.get_fair(fair_slug)
        if not fair:
            for f in db.get_all_fairs():
                if fair_slug.lower() in f["slug"].lower():
                    fair = f
                    break
        if not fair:
            console.print(f"[red]Fuar '{fair_slug}' bulunamadı.[/red]")
            return
        export_to_excel(db, fair["id"])


def ajan_gsheet(fair_slug: str):
    """Google Sheets'e aktar."""
    from ajan_bridge import AjanBot
    from rich.console import Console
    Database = AjanBot.get_database()
    console = Console()
    console.print("[yellow]GSheet export henüz bridge üzerinden desteklenmiyor. Doğrudan Ajan-bot kullanın.[/yellow]")
    return

    with Database() as db:
        fair = db.get_fair(fair_slug)
        if not fair:
            for f in db.get_all_fairs():
                if fair_slug.lower() in f["slug"].lower() or fair_slug.lower() in f["name"].lower():
                    fair = f
                    break
        if not fair:
            console.print(f"[red]Fuar '{fair_slug}' bulunamadı.[/red]")
            return
        url = export_to_gsheet(db, fair)
        if url:
            console.print(f"\n[bold]📋 Link:[/bold] [cyan]{url}[/cyan]")


def ajan_stats():
    """Lead istatistikleri."""
    from ajan_bridge import AjanBot
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import box
    Database = AjanBot.get_database()
    console = Console()

    with Database() as db:
        fairs = db.get_all_fairs()
        if not fairs:
            console.print("[yellow]Henüz veri yok. 'find' ile fuar arayın.[/yellow]")
            return

        overall = db.get_stats()
        console.print(Panel(
            f"[bold]Toplam Fuar:[/bold] {overall['total_fairs']}\n"
            f"[bold]Toplam Firma:[/bold] {overall['total_companies']}\n"
            f"[bold]Toplam Kontak:[/bold] {overall['total_contacts']}\n"
            f"[bold]E-postası Bulunan:[/bold] {overall['with_email']}\n"
            f"[bold]Telefonu Bulunan:[/bold] {overall['with_phone']}",
            title="📊 Lead İstatistikleri",
            border_style="blue",
        ))

        table = Table(title="Fuarlar", box=box.ROUNDED)
        table.add_column("ID", style="dim")
        table.add_column("Fuar", style="bold")
        table.add_column("Firma", justify="center")
        table.add_column("E-posta", justify="center", style="green")
        table.add_column("Telefon", justify="center", style="cyan")

        for fair in fairs:
            stats = db.get_stats(fair["id"])
            table.add_row(
                str(fair["id"]),
                fair["name"][:40],
                str(stats["total_companies"]),
                str(stats["with_email"]),
                str(stats["with_phone"]),
            )
        console.print(table)


def ajan_search(query: str):
    """Firma ara."""
    from ajan_bridge import AjanBot
    from rich.console import Console
    from rich.table import Table
    from rich import box
    Database = AjanBot.get_database()
    console = Console()

    with Database() as db:
        results = db.search_companies(query)
        if not results:
            console.print(f"[yellow]'{query}' ile eşleşen firma bulunamadı.[/yellow]")
            return

        table = Table(title=f"🔍 '{query}' — {len(results)} sonuç", box=box.ROUNDED)
        table.add_column("#", style="dim")
        table.add_column("Firma", style="bold")
        table.add_column("Fuar", style="dim")
        table.add_column("Web", style="cyan")
        table.add_column("Ülke")

        for i, c in enumerate(results[:30], 1):
            table.add_row(
                str(i),
                (c.get("name") or "")[:40],
                (c.get("fair_name") or "")[:25],
                (c.get("website") or "")[:35],
                (c.get("country") or ""),
            )
        console.print(table)


# ═══════════════════════════════════════════════════════════════════════════
# RADAR — Proaktif Fuar Takvimi
# ═══════════════════════════════════════════════════════════════════════════

def cmd_radar(send_telegram: bool = False, auto_scrape: bool = False):
    """Global Expo Radar — Hangi fuara ne zaman aksiyon alınmalı."""
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import box
    from fair_calendar import (
        get_upcoming_fairs, get_actionable_fairs,
        get_past_fairs_for_next_edition, format_radar_telegram, _get_flag,
    )

    console = Console()

    console.print("\n[bold blue]📡 GLOBAL EXPO RADAR[/bold blue]")
    console.print(f"[dim]Bugün: {date.today().strftime('%d/%m/%Y')}[/dim]\n")

    # ── Aksiyon alınması gereken fuarlar ──
    actionable = get_actionable_fairs()

    if actionable:
        table = Table(
            title="🔥 AKSİYON AL — Outreach Başla",
            box=box.ROUNDED,
            show_lines=True,
        )
        table.add_column("⏱", justify="center", width=6)
        table.add_column("Fuar", style="bold", min_width=25)
        table.add_column("📍", min_width=10)
        table.add_column("Sektör", min_width=15)
        table.add_column("Tarih", style="dim")
        table.add_column("Zon", justify="center")
        table.add_column("Aksiyon", style="italic")

        for fair in actionable:
            timing = fair["timing"]
            flag = _get_flag(fair.get("country", ""))

            table.add_row(
                f"{fair['days_until']}g",
                fair["name"],
                f"{flag} {fair['city']}",
                fair["sector"][:20],
                fair["start"],
                timing["color"],
                timing["action"][:25],
            )

        console.print(table)

    # ── Tüm yaklaşan fuarlar ──
    all_upcoming = get_upcoming_fairs(days_ahead=365)
    if all_upcoming:
        console.print(f"\n[dim]📅 Önümüzdeki 365 gün: {len(all_upcoming)} fuar[/dim]")

        table2 = Table(title="📅 Tüm Yaklaşan Fuarlar", box=box.SIMPLE)
        table2.add_column("Gün", justify="right", width=5)
        table2.add_column("Zon", width=3)
        table2.add_column("Fuar", style="bold")
        table2.add_column("Şehir")
        table2.add_column("Sektör")
        table2.add_column("Boyut", style="dim")

        for fair in all_upcoming:
            timing = fair["timing"]
            table2.add_row(
                str(fair["days_until"]),
                timing["color"],
                fair["name"],
                f"{fair['city']}, {fair['country']}",
                fair["sector"][:25],
                fair.get("size", ""),
            )

        console.print(table2)

    # ── Geçmiş fuarlar (exhibitor çek, sonraki edisyona hazırlan) ──
    past = get_past_fairs_for_next_edition()
    if past:
        console.print(f"\n[dim]📋 Geçmiş 1 yıl: {len(past)} fuar (exhibitor listesi çekilebilir)[/dim]")

    # ── Keşfedilmiş fuarlar (DB'den) — aksiyon zonunda olanlar ──
    try:
        from fair_discoverer import get_discovered_fairs, get_db_stats
        db_stats = get_db_stats()

        if db_stats["total_fairs"] > 0:
            # B2B fuarları 30-180 gün aralığında
            db_actionable = get_discovered_fairs(min_days=30, max_days=180)
            b2b_actionable = [f for f in db_actionable if f.get("professional_only", 0) == 1]

            if b2b_actionable:
                from fair_calendar import classify_timing

                table_db = Table(
                    title=f"🌍 KEŞFEDİLEN FUARLAR — Aksiyon Zonunda ({len(b2b_actionable)} B2B fuar)",
                    box=box.ROUNDED,
                    show_lines=True,
                )
                table_db.add_column("⏱", justify="center", width=5)
                table_db.add_column("Fuar", style="bold", min_width=25)
                table_db.add_column("📍 Şehir", min_width=12)
                table_db.add_column("🌍 Ülke", min_width=8)
                table_db.add_column("Sektör", min_width=15)
                table_db.add_column("Exhib.", justify="right", width=6)
                table_db.add_column("Zon", justify="center")

                shown = 0
                for fair in sorted(b2b_actionable, key=lambda x: x.get("days_until", 999)):
                    timing = classify_timing(fair["days_until"])
                    exhib = fair.get("exhibitor_count", "")
                    table_db.add_row(
                        f"{fair['days_until']}g",
                        fair["name"][:30],
                        fair.get("city", "")[:15],
                        fair.get("country", "")[:10],
                        (fair.get("sector") or "")[:20],
                        str(exhib) if exhib else "-",
                        timing["color"],
                    )
                    shown += 1
                    if shown >= 30:  # Max 30 göster
                        break

                console.print(table_db)

            console.print(
                f"\n[dim]🌍 Keşif DB: {db_stats['total_fairs']} fuar, "
                f"{db_stats['countries']} ülke "
                f"(güncelle: python main.py discover --details)[/dim]"
            )
    except Exception as e:
        console.print(f"[dim]⚠️ Keşif DB: {e}[/dim]")

    # ── Telegram gönder ──
    if send_telegram:
        from sender import send_message
        msg = format_radar_telegram()
        result = send_message(msg)
        if result:
            console.print("\n[green]✅ Radar raporu Telegram'a gönderildi![/green]")
        else:
            console.print("\n[red]❌ Telegram gönderimi başarısız[/red]")

    # ── Otomatik exhibitor scrape ──
    if auto_scrape and actionable:
        console.print("\n[bold]🕵️ Aksiyon zonu fuarlar için exhibitor keşfi başlıyor...[/bold]")
        for fair in actionable[:5]:  # Max 5 fuar bir seferde
            try:
                console.print(f"\n[cyan]📋 {fair['name']}...[/cyan]")
                ajan_find(fair["name"])
            except Exception as e:
                console.print(f"[red]❌ {fair['name']}: {e}[/red]")

    # Sonraki adımlar
    console.print(f"\n[bold]Komutlar:[/bold]")
    console.print(f"  [cyan]python main.py radar --send[/cyan]     ← Telegram'a gönder")
    console.print(f"  [cyan]python main.py radar --scrape[/cyan]   ← Altın zaman fuarlarının exhibitor'ını çek")
    console.print(f"  [cyan]python main.py discover[/cyan]          ← Dünya genelinde fuar keşfi")
    console.print(f"  [cyan]python main.py find 'FUAR'[/cyan]      ← Tek fuar için exhibitor çek")


# ═══════════════════════════════════════════════════════════════════════════
# DISCOVER — Dinamik Fuar Keşfi
# ═══════════════════════════════════════════════════════════════════════════

def cmd_discover(countries: list[str] = None, details: bool = False):
    """TradeFairDates + Organizer takvimlerinden dünya genelinde fuar keşfi."""
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import box
    from fair_discoverer import discover_all, get_db_stats, TARGET_COUNTRIES

    console = Console()

    console.print("\n[bold magenta]🌍 Global Fair Discovery Engine[/bold magenta]")
    console.print(f"[dim]Hedef: {len(countries or TARGET_COUNTRIES)} ülke[/dim]\n")

    stats = discover_all(
        countries=countries,
        fetch_details=details,
        max_per_country=100,
    )

    # İstatistikler
    db_stats = get_db_stats()
    console.print(Panel(
        f"[bold]Bu Tarama:[/bold] {stats['total']} fuar keşfedildi\n"
        f"[bold]Ülke:[/bold] {stats['countries_scanned']} ülke tarandı\n"
        f"[bold]Veritabanı Toplamı:[/bold] {db_stats['total_fairs']} fuar\n"
        f"[bold]Tarihli:[/bold] {db_stats['with_date']}\n"
        f"[bold]Ülke:[/bold] {db_stats['countries']}",
        title="📊 Keşif Sonuçları",
        border_style="green",
    ))

    # Detay ile çektiyse tarihli fuarları göster
    if details:
        from fair_discoverer import get_discovered_fairs
        upcoming = get_discovered_fairs(max_days=365)
        if upcoming:
            table = Table(title="📅 Tarihli Yaklaşan Fuarlar", box=box.ROUNDED)
            table.add_column("Gün", justify="right", width=5)
            table.add_column("Fuar", style="bold")
            table.add_column("Şehir")
            table.add_column("Ülke")
            for fair in upcoming[:30]:
                table.add_row(
                    str(fair.get("days_until", "?")),
                    fair["name"][:35],
                    fair.get("city", "")[:20],
                    fair.get("country", ""),
                )
            console.print(table)

    console.print(f"\n[bold]Sonraki adımlar:[/bold]")
    console.print(f"  [cyan]python main.py discover --details[/cyan]  ← Tarih bilgilerini de çek")
    console.print(f"  [cyan]python main.py radar[/cyan]                ← Fuar takvimini göster")


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    args = sys.argv[1:]

    # Veritabanını başlat
    init_db()

    # ── Ajan-Bot komutları ─────────────────────────────────────────────────
    if args and args[0].lower() == "find" and len(args) >= 2:
        fair_name = args[1]
        do_enrich = "--enrich" in args
        limit = None
        if "--limit" in args:
            idx = args.index("--limit")
            if idx + 1 < len(args):
                limit = int(args[idx + 1])
        ajan_find(fair_name, do_enrich=do_enrich, limit=limit)
        return

    if args and args[0].lower() == "enrich" and len(args) >= 2:
        limit = None
        if "--limit" in args:
            idx = args.index("--limit")
            if idx + 1 < len(args):
                limit = int(args[idx + 1])
        ajan_enrich(args[1], limit=limit)
        return

    if args and args[0].lower() == "export" and len(args) >= 2:
        ajan_export(args[1])
        return

    if args and args[0].lower() == "gsheet" and len(args) >= 2:
        ajan_gsheet(args[1])
        return

    if args and args[0].lower() in ["leads", "stats"]:
        ajan_stats()
        return

    if args and args[0].lower() == "search" and len(args) >= 2:
        ajan_search(" ".join(args[1:]))
        return

    # ── Radar komutu ───────────────────────────────────────────────────
    if args and args[0].lower() == "radar":
        cmd_radar(send_telegram="--send" in args, auto_scrape="--scrape" in args)
        return

    # ── Discover komutu ──────────────────────────────────────────────
    if args and args[0].lower() == "discover":
        countries = None
        if "--country" in args:
            idx = args.index("--country")
            if idx + 1 < len(args):
                countries = [args[idx + 1]]
        cmd_discover(countries=countries, details="--details" in args)
        return

    # ── Enrich-exhibitors komutu ──────────────────────────────────────
    if args and args[0].lower() in ("enrich-exhibitors", "enrich-ex"):
        from fair_discoverer import enrich_exhibitor_coverage
        zone = "gold"
        max_fairs = 50
        for i, arg in enumerate(args):
            if arg == "--zone" and i + 1 < len(args):
                zone = args[i + 1]
            if arg == "--max" and i + 1 < len(args):
                max_fairs = int(args[i + 1])
        print(f"\n🔍 Exhibitor Coverage Enrichment")
        print(f"  Zone: {zone} | Max: {max_fairs} fuar\n")
        stats = enrich_exhibitor_coverage(zone=zone, max_fairs=max_fairs)
        return

    # ── Haber botu komutları ───────────────────────────────────────────────

    # Test modu
    if "--test" in args:
        logger.info("🔧 Test modu: Telegram bağlantısı test ediliyor...")
        if not check_config():
            sys.exit(1)
        send_test_message()
        return

    # Hemen çalıştır
    if "--now" in args:
        logger.info("⚡ Hemen çalıştırma modu...")
        if not check_config():
            sys.exit(1)
        run_job()
        today = date.today().isoformat()
        set_last_run_date(today)
        return

    # LaunchAgent modu
    if "--once" in args:
        logger.info("🕐 LaunchAgent modu: Tek seferlik çalıştırma...")
        if not check_config():
            sys.exit(1)
        run_job_once()
        return

    # Yardım
    if args and args[0] in ["help", "--help", "-h"]:
        print(__doc__)
        return

    # ── Scheduler modu (varsayılan) ───────────────────────────────────────
    if not check_config():
        sys.exit(1)

    send_time = f"{DAILY_SEND_HOUR:02d}:{DAILY_SEND_MINUTE:02d}"
    logger.info(f"⏰ Scheduler başlatıldı. Her gün {send_time}'de çalışacak.")
    logger.info(f"📡 Haftalık radar: Her Pazartesi 08:00")

    schedule.every().day.at(send_time).do(run_job_once)

    # Haftalık radar raporu — her Pazartesi 08:00
    def weekly_radar():
        logger.info("📡 Haftalık radar raporu gönderiliyor...")
        try:
            from fair_calendar import format_radar_telegram
            from sender import send_message
            msg = format_radar_telegram()
            send_message(msg)
            logger.info("✅ Radar raporu gönderildi.")
        except Exception as e:
            logger.error(f"❌ Radar raporu gönderilemedi: {e}")

    schedule.every().monday.at("08:00").do(weekly_radar)

    logger.info("🔄 Başlangıç kontrolü yapılıyor...")
    run_job_once()

    while True:
        schedule.run_pending()
        next_run = schedule.next_run()
        if next_run:
            remaining = next_run - datetime.now()
            hours, rem = divmod(int(remaining.total_seconds()), 3600)
            minutes = rem // 60
            print(f"\r⏳ Sonraki çalıştırma: {hours}s {minutes}dk sonra", end="", flush=True)
        time.sleep(60)


if __name__ == "__main__":
    main()
