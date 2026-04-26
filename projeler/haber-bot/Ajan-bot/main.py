#!/usr/bin/env python3
"""
Ajan-Bot — Fuar Lead Generator
Main CLI entry point.

Usage:
    python main.py scrape <fair_name>           Scrape exhibitor list from a fair
    python main.py scrape-url <url> [--name X]  Scrape from any URL
    python main.py enrich <fair_name>           Enrich companies with contacts
    python main.py export <fair_name>           Export to Excel
    python main.py telegram <fair_name>         Send results to Telegram
    python main.py stats                        Show database statistics
    python main.py list-fairs                   List all scraped fairs
    python main.py search <query>               Search companies
    python main.py full <fair_name>             Full pipeline: scrape + enrich + export
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

import config
from database.db import Database
from scrapers.idef_scraper import IDEFScraper
from scrapers.saha_expo_scraper import SahaExpoScraper
from scrapers.generic_scraper import GenericScraper
from scrapers.selenium_scraper import SeleniumIDEFScraper
from scrapers.smart_discoverer import SmartFairDiscoverer
from enrichment.enricher import Enricher
from export.excel_export import export_to_excel, export_to_csv
from export.telegram_export import send_fair_summary, send_company_list
from export.google_sheets import export_to_gsheet

console = Console()

# ─── Banner ───────────────────────────────────────────────────
BANNER = """
[bold blue]
   ╔═══════════════════════════════════════════╗
   ║     🕵️  AJAN-BOT — Lead Generator  🎯    ║
   ║     Fuar Katılımcı & Kontak Bulucu        ║
   ╚═══════════════════════════════════════════╝
[/bold blue]"""


def get_scraper(fair_name: str, use_selenium: bool = False):
    """Get the appropriate scraper for a fair."""
    if use_selenium:
        scrapers = {
            "idef": SeleniumIDEFScraper,
            "saha_expo": SahaExpoScraper,
            "saha": SahaExpoScraper,
            "sahaexpo": SahaExpoScraper,
        }
    else:
        scrapers = {
            "idef": IDEFScraper,
            "saha_expo": SahaExpoScraper,
            "saha": SahaExpoScraper,
            "sahaexpo": SahaExpoScraper,
        }
    scraper_class = scrapers.get(fair_name.lower())
    if scraper_class:
        return scraper_class()
    return None


def cmd_scrape(fair_name: str, use_selenium: bool = False):
    """Scrape exhibitor list from a known fair."""
    console.print(BANNER)

    scraper = get_scraper(fair_name, use_selenium=use_selenium)
    if not scraper:
        console.print(f"[red]Unknown fair: {fair_name}[/red]")
        console.print("[dim]Known fairs: idef, saha_expo[/dim]")
        console.print("[dim]For custom URLs, use: python main.py scrape-url <URL>[/dim]")
        return

    # Scrape
    companies = scraper.scrape()
    scraper.print_summary()

    if not companies:
        console.print("[yellow]No companies found. The fair site may not have the list available yet.[/yellow]")
        return

    # Save to database
    with Database() as db:
        fair_id = db.upsert_fair(
            slug=scraper.fair_slug,
            name=scraper.fair_name,
            url=scraper.fair_url,
        )

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
                logo_url=data.get("logo_url"),
                raw_data=data.get("raw_data"),
            )
            saved += 1

        console.print(f"\n[green]✓ Saved {saved} companies to database[/green]")
        console.print(f"[dim]Fair ID: {fair_id} | DB: {config.DB_PATH}[/dim]")


def cmd_scrape_url(url: str, name: str = None):
    """Scrape exhibitor list from a custom URL."""
    console.print(BANNER)

    scraper = GenericScraper(url=url, name=name)
    companies = scraper.scrape()
    scraper.print_summary()

    if not companies:
        console.print("[yellow]No companies found at this URL.[/yellow]")
        return

    # Save to database
    with Database() as db:
        fair_id = db.upsert_fair(
            slug=scraper.fair_slug,
            name=scraper.fair_name,
            url=scraper.fair_url,
        )

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
                logo_url=data.get("logo_url"),
                raw_data=data.get("raw_data"),
            )
            saved += 1

        console.print(f"\n[green]✓ Saved {saved} companies to database[/green]")


def cmd_find(fair_name: str, enrich: bool = False, limit: int = None, enrich_details: bool = True):
    """🔍 Smart find: Give a fair name → find exhibitors → optionally enrich contacts."""
    console.print(BANNER)
    console.print(f"[bold magenta]🕵️ Fuar adı: '{fair_name}'[/bold magenta]")
    console.print(f"[dim]Otomatik keşif başlıyor...[/dim]\n")

    discoverer = SmartFairDiscoverer()
    result = discoverer.discover_and_scrape(fair_name, enrich_details=enrich_details)

    companies = result["companies"]
    if not companies:
        console.print(f"\n[red]❌ '{fair_name}' için katılımcı bulunamadı.[/red]")
        console.print("[dim]İpuçları:[/dim]")
        console.print("  [dim]• Fuar adını tam yazın (ör: 'IDEF 2025', 'SAHA EXPO')[/dim]")
        console.print("  [dim]• Doğrudan URL ile deneyin: python main.py scrape-url <URL>[/dim]")
        return

    # Save to database
    with Database() as db:
        slug = fair_name.lower().replace(" ", "_").replace("-", "_")[:30]
        fair_id = db.upsert_fair(
            slug=slug,
            name=fair_name,
            url=result.get("fair_url"),
        )

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
                logo_url=data.get("logo_url"),
                raw_data=data.get("raw_data"),
                email=data.get("email"),
                phone=data.get("phone"),
                address=data.get("address"),
            )
            saved += 1

        console.print(f"\n[green]✓ {saved} firma veritabanına kaydedildi[/green]")
        console.print(f"[dim]Fair ID: {fair_id} | Slug: {slug}[/dim]")

        # Auto-enrich if requested
        if enrich:
            console.print(f"\n[bold]═══ Kontak Zenginleştirme ═══[/bold]")
            enricher = Enricher(db)
            enricher.enrich_fair(fair_id=fair_id, use_hunter=True, limit=limit)

            # Auto-export
            console.print(f"\n[bold]═══ Excel Export ═══[/bold]")
            export_to_excel(db, fair_id)

        # Show summary table
        console.print(f"\n")
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
        console.print(f"  [cyan]python main.py enrich {slug} --no-hunter --limit 10[/cyan]  ← Kontak bul")
        console.print(f"  [cyan]python main.py export {slug}[/cyan]                        ← Excel'e aktar")


def cmd_enrich(fair_name: str, limit: int = None, no_hunter: bool = False):
    """Enrich companies with contact information."""
    console.print(BANNER)

    with Database() as db:
        fair = db.get_fair(fair_name)
        if not fair:
            # Try to find by partial name
            all_fairs = db.get_all_fairs()
            for f in all_fairs:
                if fair_name.lower() in f["slug"].lower() or fair_name.lower() in f["name"].lower():
                    fair = f
                    break

        if not fair:
            console.print(f"[red]Fair '{fair_name}' not found in database.[/red]")
            console.print("[dim]Run 'python main.py scrape <fair>' first.[/dim]")
            return

        enricher = Enricher(db)
        enricher.enrich_fair(
            fair_id=fair["id"],
            use_hunter=not no_hunter,
            limit=limit,
        )


def cmd_export(fair_name: str, format: str = "excel"):
    """Export data to Excel or CSV."""
    console.print(BANNER)

    with Database() as db:
        fair = db.get_fair(fair_name)
        if not fair:
            all_fairs = db.get_all_fairs()
            for f in all_fairs:
                if fair_name.lower() in f["slug"].lower():
                    fair = f
                    break

        if not fair:
            console.print(f"[red]Fair '{fair_name}' not found.[/red]")
            return

        if format == "csv":
            export_to_csv(db, fair["id"])
        else:
            export_to_excel(db, fair["id"])


def cmd_gsheet(fair_name: str, sheet_url: str = None):
    """Export data to Google Sheets."""
    console.print(BANNER)

    with Database() as db:
        fair = db.get_fair(fair_name)
        if not fair:
            all_fairs = db.get_all_fairs()
            for f in all_fairs:
                if fair_name.lower() in f["slug"].lower() or fair_name.lower() in f["name"].lower():
                    fair = f
                    break

        if not fair:
            console.print(f"[red]Fair '{fair_name}' not found.[/red]")
            console.print("[dim]Run 'python main.py find \"FUAR ADI\"' first.[/dim]")
            return

        url = export_to_gsheet(db, fair, sheet_url=sheet_url)
        if url:
            console.print(f"\n[bold]📋 Link'i tarayıcıda aç:[/bold]")
            console.print(f"  [cyan]{url}[/cyan]")


def cmd_telegram(fair_name: str):
    """Send results to Telegram."""
    console.print(BANNER)

    with Database() as db:
        fair = db.get_fair(fair_name)
        if not fair:
            all_fairs = db.get_all_fairs()
            for f in all_fairs:
                if fair_name.lower() in f["slug"].lower():
                    fair = f
                    break

        if not fair:
            console.print(f"[red]Fair '{fair_name}' not found.[/red]")
            return

        console.print(f"[bold]Sending results for {fair['name']} to Telegram...[/bold]")
        if send_fair_summary(db, fair["id"]):
            console.print("[green]✓ Summary sent![/green]")
        else:
            console.print("[red]✗ Failed to send summary[/red]")


def cmd_stats():
    """Show database statistics."""
    console.print(BANNER)

    with Database() as db:
        fairs = db.get_all_fairs()

        if not fairs:
            console.print("[yellow]No data yet. Run 'python main.py scrape <fair>' first.[/yellow]")
            return

        overall = db.get_stats()

        # Overall stats panel
        console.print(Panel(
            f"[bold]Toplam Fuar:[/bold] {overall['total_fairs']}\n"
            f"[bold]Toplam Firma:[/bold] {overall['total_companies']}\n"
            f"[bold]Toplam Kontak:[/bold] {overall['total_contacts']}\n"
            f"[bold]E-postası Bulunan:[/bold] {overall['with_email']}\n"
            f"[bold]Telefonu Bulunan:[/bold] {overall['with_phone']}",
            title="📊 Genel İstatistikler",
            border_style="blue",
        ))

        # Per-fair table
        table = Table(title="Fuarlar", box=box.ROUNDED)
        table.add_column("ID", style="dim")
        table.add_column("Fuar", style="bold")
        table.add_column("Firma Sayısı", justify="center")
        table.add_column("E-posta", justify="center", style="green")
        table.add_column("Telefon", justify="center", style="cyan")
        table.add_column("Scrape Tarihi", style="dim")

        for fair in fairs:
            stats = db.get_stats(fair["id"])
            table.add_row(
                str(fair["id"]),
                fair["name"][:40],
                str(stats["total_companies"]),
                str(stats["with_email"]),
                str(stats["with_phone"]),
                fair.get("scraped_at", "")[:16] if fair.get("scraped_at") else "",
            )

        console.print(table)


def cmd_list_fairs():
    """List all scraped fairs."""
    cmd_stats()  # Same output


def cmd_search(query: str):
    """Search companies across all fairs."""
    console.print(BANNER)

    with Database() as db:
        results = db.search_companies(query)

        if not results:
            console.print(f"[yellow]No companies found matching '{query}'[/yellow]")
            return

        table = Table(title=f"🔍 Arama: '{query}' — {len(results)} sonuç", box=box.ROUNDED)
        table.add_column("ID", style="dim")
        table.add_column("Firma", style="bold")
        table.add_column("Fuar", style="dim")
        table.add_column("Web Sitesi", style="cyan")
        table.add_column("Sektör")

        for company in results[:50]:
            table.add_row(
                str(company["id"]),
                (company.get("name") or "")[:40],
                (company.get("fair_name") or "")[:30],
                (company.get("website") or "")[:40],
                (company.get("sector") or "")[:30],
            )

        console.print(table)


def cmd_full(fair_name: str, limit: int = None):
    """Full pipeline: scrape + enrich + export."""
    console.print(BANNER)
    console.print("[bold magenta]🚀 Running full pipeline...[/bold magenta]\n")

    # Step 1: Scrape
    console.print("[bold]═══ Step 1/3: Scraping ═══[/bold]")
    cmd_scrape(fair_name)

    # Step 2: Enrich
    console.print(f"\n[bold]═══ Step 2/3: Enrichment ═══[/bold]")
    cmd_enrich(fair_name, limit=limit)

    # Step 3: Export
    console.print(f"\n[bold]═══ Step 3/3: Export ═══[/bold]")
    cmd_export(fair_name)

    console.print(f"\n[bold green]🎉 Pipeline complete![/bold green]")


def print_help():
    """Show usage help."""
    console.print(BANNER)
    console.print(Panel(
        "[bold]Kullanım:[/bold]\n\n"
        "  [bold cyan]python main.py find '<fuar adı>'[/bold cyan]     ← 🔍 ANA KOMUT: Fuar adı ver, firmalar bulunsun\n"
        "  [cyan]python main.py scrape <fuar>[/cyan]          Bilinen fuardan katılımcı çek\n"
        "  [cyan]python main.py scrape-url <url>[/cyan]       URL'den çek\n"
        "  [cyan]python main.py enrich <fuar>[/cyan]          Kontak bilgisi zenginleştir\n"
        "  [cyan]python main.py export <fuar>[/cyan]          Excel'e aktar\n"
        "  [bold cyan]python main.py gsheet <fuar>[/bold cyan]         📊 Google Sheets'e aktar\n"
        "  [cyan]python main.py telegram <fuar>[/cyan]        Telegram'a gönder\n"
        "  [cyan]python main.py stats[/cyan]                  İstatistikler\n"
        "  [cyan]python main.py search <sorgu>[/cyan]         Firma ara\n\n"
        "[bold]Örnekler:[/bold]\n"
        "  python main.py find 'SAHA EXPO'\n"
        "  python main.py find 'IDEF 2025'\n"
        "  python main.py find 'WIN Eurasia' --enrich\n"
        "  python main.py enrich saha_expo --no-hunter --limit 10\n"
        "  python main.py export idef",
        title="🕵️ Ajan-Bot — Yardım",
        border_style="blue",
    ))


# ─── Main Entry Point ────────────────────────────────────────
if __name__ == "__main__":
    args = sys.argv[1:]

    if not args:
        print_help()
        sys.exit(0)

    command = args[0].lower()

    try:
        if command == "find" and len(args) >= 2:
            fair_name = args[1]
            do_enrich = "--enrich" in args
            limit = None
            if "--limit" in args:
                idx = args.index("--limit")
                if idx + 1 < len(args):
                    limit = int(args[idx + 1])
            no_detail = "--no-detail" in args
            cmd_find(fair_name, enrich=do_enrich, limit=limit, enrich_details=not no_detail)

        elif command == "scrape" and len(args) >= 2:
            use_sel = "--selenium" in args
            cmd_scrape(args[1], use_selenium=use_sel)

        elif command == "scrape-url" and len(args) >= 2:
            name = None
            if "--name" in args:
                idx = args.index("--name")
                if idx + 1 < len(args):
                    name = args[idx + 1]
            cmd_scrape_url(args[1], name=name)

        elif command == "enrich" and len(args) >= 2:
            limit = None
            no_hunter = "--no-hunter" in args
            if "--limit" in args:
                idx = args.index("--limit")
                if idx + 1 < len(args):
                    limit = int(args[idx + 1])
            cmd_enrich(args[1], limit=limit, no_hunter=no_hunter)

        elif command == "export" and len(args) >= 2:
            fmt = "csv" if "--csv" in args else "excel"
            cmd_export(args[1], format=fmt)

        elif command == "gsheet" and len(args) >= 2:
            sheet_url = None
            if "--url" in args:
                idx = args.index("--url")
                if idx + 1 < len(args):
                    sheet_url = args[idx + 1]
            cmd_gsheet(args[1], sheet_url=sheet_url)

        elif command == "telegram" and len(args) >= 2:
            cmd_telegram(args[1])

        elif command == "stats":
            cmd_stats()

        elif command in ["list-fairs", "fairs"]:
            cmd_list_fairs()

        elif command == "search" and len(args) >= 2:
            cmd_search(" ".join(args[1:]))

        elif command == "full" and len(args) >= 2:
            limit = None
            if "--limit" in args:
                idx = args.index("--limit")
                if idx + 1 < len(args):
                    limit = int(args[idx + 1])
            cmd_full(args[1], limit=limit)

        elif command in ["help", "--help", "-h"]:
            print_help()

        else:
            console.print(f"[red]Unknown command: {command}[/red]")
            print_help()

    except KeyboardInterrupt:
        console.print("\n[yellow]İptal edildi.[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        import traceback
        traceback.print_exc()
