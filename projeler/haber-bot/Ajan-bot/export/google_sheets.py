"""
Google Sheets Export Module
Exports fair exhibitor data directly to Google Sheets.
"""

import gspread
from google.oauth2.service_account import Credentials
from rich.console import Console
from pathlib import Path

import config
from database.db import Database

console = Console()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

CREDENTIALS_PATH = config.BASE_DIR / "credentials.json"


def get_gspread_client():
    """Authenticate and return gspread client."""
    if not CREDENTIALS_PATH.exists():
        console.print("[red]❌ credentials.json bulunamadı![/red]")
        return None

    creds = Credentials.from_service_account_file(
        str(CREDENTIALS_PATH), scopes=SCOPES
    )
    return gspread.authorize(creds)


def export_to_gsheet(db: Database, fair: dict, sheet_url: str = None, spreadsheet_name: str = None):
    """Export fair data to Google Spreadsheet.
    
    If sheet_url is provided, writes to existing sheet.
    Otherwise creates a new one.
    """
    fair_name = fair.get("name", "Fair")
    fair_id = fair.get("id")
    if not spreadsheet_name:
        spreadsheet_name = f"Ajan-Bot — {fair_name}"

    console.print(f"\n[bold blue]📊 Google Sheets Export: {fair_name}[/bold blue]")

    console.print(f"  [dim]Authenticating...[/dim]")
    gc = get_gspread_client()
    if not gc:
        return None

    companies = db.get_companies_by_fair(fair_id)
    if not companies:
        console.print(f"  [red]❌ Firma bulunamadı.[/red]")
        return None

    console.print(f"  [dim]{len(companies)} firma bulundu[/dim]")

    # Open existing or create new spreadsheet
    if sheet_url:
        console.print(f"  [dim]Mevcut spreadsheet açılıyor...[/dim]")
        try:
            sh = gc.open_by_url(sheet_url)
        except Exception as e:
            console.print(f"  [red]❌ Sheet açılamadı: {e}[/red]")
            console.print(f"  [dim]Sheet'i bu e-posta ile paylaşın:[/dim]")
            console.print(f"  [cyan]ajan-bot@peak-haven-199523.iam.gserviceaccount.com[/cyan]")
            return None
    else:
        console.print(f"  [dim]Yeni spreadsheet oluşturuluyor...[/dim]")
        try:
            sh = gc.create(spreadsheet_name)
            sh.share("", perm_type="anyone", role="writer")
        except Exception as e:
            console.print(f"  [red]❌ Oluşturulamadı: {e}[/red]")
            console.print(f"\n  [yellow]💡 Alternatif: Boş bir Google Sheet oluşturup URL'sini verin:[/yellow]")
            console.print(f"  [cyan]python main.py gsheet idef --url 'SHEET_URL'[/cyan]")
            return None

    # Get or create worksheet tab
    tab_name = fair_name[:50]  # Sheet tab name limit
    if sheet_url:
        # Try to find existing tab with this name, or create new one
        try:
            worksheet = sh.worksheet(tab_name)
            console.print(f"  [dim]Mevcut '{tab_name}' sekmesi bulundu, üzerine yazılıyor...[/dim]")
        except gspread.exceptions.WorksheetNotFound:
            worksheet = sh.add_worksheet(title=tab_name, rows=100, cols=10)
            console.print(f"  [dim]Yeni '{tab_name}' sekmesi oluşturuldu[/dim]")
    else:
        worksheet = sh.sheet1
        worksheet.update_title(tab_name)

    headers = [
        "No", "Firma Adı", "Web Sitesi", "E-posta", "Telefon",
        "Ülke", "Sektör", "Stant No", "Adres"
    ]

    rows = [headers]
    for i, company in enumerate(companies, 1):
        row = [
            i,
            company.get("name", ""),
            company.get("website", "") or "",
            company.get("email", "") or "",
            company.get("phone", "") or "",
            company.get("country", "") or "",
            company.get("sector", "") or "",
            company.get("booth_number", "") or "",
            company.get("address", "") or "",
        ]
        rows.append(row)

    # Resize worksheet to fit all data
    needed_rows = len(rows) + 10
    worksheet.resize(rows=needed_rows, cols=10)
    worksheet.clear()

    console.print(f"  [dim]{len(rows)-1} satır yazılıyor...[/dim]")

    BATCH_SIZE = 500
    for start in range(0, len(rows), BATCH_SIZE):
        end = min(start + BATCH_SIZE, len(rows))
        batch = rows[start:end]
        cell_range = f"A{start+1}"
        worksheet.update(cell_range, batch)
        if start > 0:
            console.print(f"  [dim]  {min(end-1, len(rows)-1)}/{len(rows)-1} satır yazıldı...[/dim]")

    try:
        worksheet.format("A1:H1", {
            "backgroundColor": {"red": 0.1, "green": 0.3, "blue": 0.6},
            "textFormat": {
                "bold": True,
                "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                "fontSize": 11,
            },
            "horizontalAlignment": "CENTER",
        })
        worksheet.columns_auto_resize(0, 8)
        worksheet.freeze(rows=1)
    except Exception:
        pass

    url = sh.url
    console.print(f"\n  [bold green]✓ Google Sheets oluşturuldu![/bold green]")
    console.print(f"  [bold cyan]🔗 {url}[/bold cyan]")
    console.print(f"  [dim]{len(companies)} firma yazıldı[/dim]")
    return url
