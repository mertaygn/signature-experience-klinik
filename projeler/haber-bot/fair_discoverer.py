"""
Fair Discoverer — 3 Katmanlı Dinamik Fuar Takvimi Keşif Motoru

Katman 1: 🏢 ORGANIZER — Büyük organizatörlerin etkinlik takvimleri
Katman 2: 🌍 AGGREGATOR — TradeFairDates, 10times vb. sitelerden toplu çekme
Katman 3: 🌐 DİL — Çoklu dilde arama (DE, CN, ES, IT, FR + EN, TR)

"Dünyadaki tüm önemli B2B fuarlarını yakalamak"
"""

import re
import time
import json
import sqlite3
import requests
from datetime import datetime, date
from typing import Optional
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

# ═══════════════════════════════════════════════════════════════════════════
# VERİTABANI — Keşfedilen fuarları saklar
# ═══════════════════════════════════════════════════════════════════════════

DB_PATH = Path(__file__).parent / "data" / "fair_radar.db"

def _get_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS discovered_fairs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            city TEXT,
            country TEXT,
            sector TEXT,
            start_date TEXT,
            end_date TEXT,
            organizer TEXT,
            venue TEXT,
            website TEXT,
            exhibitor_count TEXT,
            source TEXT,              -- 'organizer', 'aggregator', 'manual'
            source_url TEXT,
            professional_only INTEGER DEFAULT 1,
            last_updated TEXT DEFAULT (datetime('now')),
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    return conn


def upsert_fair(conn, fair: dict) -> int:
    """Fuar ekle veya güncelle."""
    slug = fair.get("slug") or _make_slug(fair["name"], fair.get("city", ""))
    cursor = conn.execute("""
        INSERT INTO discovered_fairs
            (slug, name, city, country, sector, start_date, end_date,
             organizer, venue, website, exhibitor_count, source, source_url,
             professional_only, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(slug) DO UPDATE SET
            name=COALESCE(excluded.name, discovered_fairs.name),
            city=COALESCE(excluded.city, discovered_fairs.city),
            country=COALESCE(excluded.country, discovered_fairs.country),
            sector=COALESCE(excluded.sector, discovered_fairs.sector),
            start_date=COALESCE(excluded.start_date, discovered_fairs.start_date),
            end_date=COALESCE(excluded.end_date, discovered_fairs.end_date),
            organizer=COALESCE(excluded.organizer, discovered_fairs.organizer),
            venue=COALESCE(excluded.venue, discovered_fairs.venue),
            website=COALESCE(excluded.website, discovered_fairs.website),
            exhibitor_count=COALESCE(excluded.exhibitor_count, discovered_fairs.exhibitor_count),
            source=COALESCE(excluded.source, discovered_fairs.source),
            source_url=COALESCE(excluded.source_url, discovered_fairs.source_url),
            last_updated=datetime('now')
        RETURNING id
    """, (slug, fair["name"], fair.get("city"), fair.get("country"),
          fair.get("sector"), fair.get("start_date"), fair.get("end_date"),
          fair.get("organizer"), fair.get("venue"), fair.get("website"),
          fair.get("exhibitor_count"), fair.get("source", "aggregator"),
          fair.get("source_url"), fair.get("professional_only", 1)))
    fid = cursor.fetchone()[0]
    conn.commit()
    return fid


def _make_slug(name: str, city: str = "") -> str:
    s = f"{name}_{city}".lower()
    s = re.sub(r'[^a-z0-9]+', '_', s)
    return s.strip('_')[:50]


# ═══════════════════════════════════════════════════════════════════════════
# HTTP İSTEMCİSİ
# ═══════════════════════════════════════════════════════════════════════════

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,tr;q=0.8,de;q=0.7",
})


def _fetch(url: str, timeout: int = 15) -> Optional[BeautifulSoup]:
    try:
        r = SESSION.get(url, timeout=timeout)
        if r.status_code == 200:
            return BeautifulSoup(r.text, "lxml")
    except requests.RequestException:
        pass
    return None


# ═══════════════════════════════════════════════════════════════════════════
# KATMAN 1: ORGANIZER TAKVİMLERİ
# ═══════════════════════════════════════════════════════════════════════════

# Büyük organizatörlerin event listesi URL'leri ve parse stratejileri
ORGANIZERS = {
    "messe_frankfurt": {
        "name": "Messe Frankfurt",
        "urls": [
            "https://www.messefrankfurt.com/frankfurt/en/events.html",
        ],
        "country": "Almanya",
    },
    "koelnmesse": {
        "name": "Koelnmesse",
        "urls": [
            "https://www.koelnmesse.com/trade-fairs-and-events/trade-fair-calendar/all-trade-fairs/",
        ],
        "country": "Almanya",
    },
    "messe_duesseldorf": {
        "name": "Messe Düsseldorf",
        "urls": [
            "https://www.messe-duesseldorf.com/en/portfolio",
        ],
        "country": "Almanya",
    },
    "messe_muenchen": {
        "name": "Messe München",
        "urls": [
            "https://messe-muenchen.de/en/trade-fairs/trade-fair-calendar.php",
        ],
        "country": "Almanya",
    },
    "fiera_milano": {
        "name": "Fiera Milano",
        "urls": [
            "https://www.fieramilano.it/en/calendar.html",
        ],
        "country": "İtalya",
    },
    "dwtc": {
        "name": "Dubai World Trade Centre",
        "urls": [
            "https://www.dwtc.com/en/events",
        ],
        "country": "BAE",
    },
    "rx_global": {
        "name": "RX Global",
        "urls": [
            "https://rxglobal.com/events",
        ],
        "country": "Global",
    },
    "informa": {
        "name": "Informa Markets",
        "urls": [
            "https://www.informamarkets.com/en/home.html",
        ],
        "country": "Global",
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# KATMAN 2: AGGREGATOR — TradeFairDates
# ═══════════════════════════════════════════════════════════════════════════

# Hedef ülkeler ve TradeFairDates URL kodları
TARGET_COUNTRIES = {
    "Germany": {"code": "Z55", "country_tr": "Almanya"},
    "Turkey": {"code": "Z220", "country_tr": "Türkiye"},
    "UAE": {"code": "Z2", "country_tr": "BAE"},
    "Italy": {"code": "Z108", "country_tr": "İtalya"},
    "France": {"code": "Z73", "country_tr": "Fransa"},
    "Spain": {"code": "Z66", "country_tr": "İspanya"},
    "China": {"code": "Z47", "country_tr": "Çin"},
    "USA": {"code": "Z228", "country_tr": "ABD"},
    "UK": {"code": "Z75", "country_tr": "İngiltere"},
    "Saudi Arabia": {"code": "Z190", "country_tr": "Suudi Arabistan"},
    "India": {"code": "Z103", "country_tr": "Hindistan"},
    "Japan": {"code": "Z112", "country_tr": "Japonya"},
    "South Korea": {"code": "Z120", "country_tr": "Güney Kore"},
    "Brazil": {"code": "Z30", "country_tr": "Brezilya"},
    "Netherlands": {"code": "Z163", "country_tr": "Hollanda"},
    "Singapore": {"code": "Z195", "country_tr": "Singapur"},
    "Qatar": {"code": "Z184", "country_tr": "Katar"},
    "Egypt": {"code": "Z63", "country_tr": "Mısır"},
    "Poland": {"code": "Z176", "country_tr": "Polonya"},
    "Indonesia": {"code": "Z99", "country_tr": "Endonezya"},
}


def _parse_fair_links(soup, country_tr: str, source_url: str) -> list[dict]:
    """Bir TradeFairDates sayfasından fuar linklerini parse et."""
    fairs = []
    fair_links = soup.find_all("a", href=re.compile(r'-M\d+/'))

    seen = set()
    for link in fair_links:
        href = link.get("href", "")
        name = link.get_text(strip=True)

        if not name or len(name) < 3 or name in seen:
            continue
        if not re.search(r'-M\d+/', href):
            continue

        city_match = re.search(r'/([^/]+)\.html$', href)
        city = city_match.group(1).replace('+', ' ') if city_match else ""

        seen.add(name)
        full_url = urljoin("https://www.tradefairdates.com/", href)

        fairs.append({
            "name": name,
            "city": city,
            "country": country_tr,
            "website": full_url,
            "source": "tradefairdates",
            "source_url": source_url,
        })

    return fairs


def scrape_tradefairdates_country(country_name: str, country_info: dict,
                                   max_pages: int = 5) -> list[dict]:
    """TradeFairDates'ten bir ülkedeki fuarları çek (çok sayfalı)."""
    code = country_info["code"]
    country_tr = country_info["country_tr"]

    all_fairs = []

    for page in range(1, max_pages + 1):
        url = f"https://www.tradefairdates.com/Fairs-{country_name.replace(' ', '-')}-{code}-S{page}.html"

        if page == 1:
            print(f"  [TFD] {country_name}...", end="", flush=True)

        soup = _fetch(url)
        if not soup:
            break

        page_fairs = _parse_fair_links(soup, country_tr, url)
        if not page_fairs:
            break  # Boş sayfa = son sayfa

        all_fairs.extend(page_fairs)

        # Sonraki sayfa mevcut mu kontrol et
        next_link = soup.find("a", href=re.compile(f'-S{page + 1}\\.html'))
        if not next_link:
            break

        time.sleep(0.3)

    # Duplicate'leri temizle
    unique_fairs = {}
    for f in all_fairs:
        key = f["name"].lower()
        if key not in unique_fairs:
            unique_fairs[key] = f

    result = list(unique_fairs.values())
    pages_str = f" ({page}p)" if page > 1 else ""
    print(f" ✓ {len(result)} fuar{pages_str}")
    return result


def scrape_tradefairdates_detail(fair_url: str) -> dict:
    """
    Tek bir fuarın detay sayfasından TÜM bilgileri çek.

    Kaynak önceliği:
    1. Google Calendar linki (en güvenilir tarih)
    2. Metin içindeki tarih formatları
    3. Exhibitor sayısı
    4. Sektör (Product groups + Category linkleri)
    5. Venue, Audience, Description
    """
    soup = _fetch(fair_url)
    if not soup:
        return {}

    details = {}
    text = soup.get_text(" ", strip=True)

    # ─── 1. TARİH: Google Calendar linkinden çek (EN GÜVENİLİR) ────
    gcal_link = soup.find("a", href=re.compile(r'calendar\.google\.com'))
    if gcal_link:
        href = gcal_link.get("href", "")
        date_match = re.search(r'dates=(\d{8})/(\d{8})', href)
        if date_match:
            try:
                start = datetime.strptime(date_match.group(1), "%Y%m%d")
                end = datetime.strptime(date_match.group(2), "%Y%m%d")
                details["start_date"] = start.strftime("%Y-%m-%d")
                details["end_date"] = end.strftime("%Y-%m-%d")
            except ValueError:
                pass

    # Fallback: Metin içinde "dd. - dd. Month yyyy" veya "dd.mm.yyyy"
    if "start_date" not in details:
        date_pattern = re.compile(r'(\d{2})\.\s*-\s*(\d{2})\.\s*((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})')
        d_match = date_pattern.search(text)
        if d_match:
            try:
                end_d = datetime.strptime(f"{d_match.group(2)}. {d_match.group(3)}", "%d. %B %Y")
                start_d = end_d.replace(day=int(d_match.group(1)))
                details["start_date"] = start_d.strftime("%Y-%m-%d")
                details["end_date"] = end_d.strftime("%Y-%m-%d")
            except ValueError:
                pass

    if "start_date" not in details:
        date_pattern2 = re.compile(r'(\d{2}\.\d{2}\.\d{4})\s*[-–]\s*(\d{2}\.\d{2}\.\d{4})')
        d_match2 = date_pattern2.search(text)
        if d_match2:
            try:
                start = datetime.strptime(d_match2.group(1), "%d.%m.%Y")
                end = datetime.strptime(d_match2.group(2), "%d.%m.%Y")
                details["start_date"] = start.strftime("%Y-%m-%d")
                details["end_date"] = end.strftime("%Y-%m-%d")
            except ValueError:
                pass

    # ─── 2. EXHİBİTOR SAYISI ──────────────────────────────────────────
    exhib_match = re.search(r'(\d[\d,.]+)\s+exhibitors?', text, re.IGNORECASE)
    if exhib_match:
        details["exhibitor_count"] = exhib_match.group(1).replace(",", "").replace(".", "")

    # ─── 3. SEKTÖR (Category linkleri) ────────────────────────────────
    category_links = soup.find_all("a", href=re.compile(r'-Y\d+-S1\.html'))
    if category_links:
        sectors = []
        for cl in category_links[:5]:
            sector_name = cl.get_text(strip=True)
            if sector_name and len(sector_name) > 2:
                sectors.append(sector_name)
        if sectors:
            details["sector"] = ", ".join(dict.fromkeys(sectors))  # deduplicate

    # Product groups
    if "sector" not in details:
        pg_match = re.search(r'Product groups?:\s*(.+?)(?:\n|$)', text)
        if pg_match:
            details["sector"] = pg_match.group(1).strip()[:200]

    # ─── 4. VENUE ─────────────────────────────────────────────────────
    venue_link = soup.find("a", href=re.compile(r'-ZS\d+'))
    if venue_link:
        details["venue"] = venue_link.get_text(strip=True)

    # ─── 5. AUDIENCE (B2B filtresi için kritik) ────────────────────────
    text_lower = text.lower()
    if "professional visitors only" in text_lower:
        details["professional_only"] = 1
    elif "professional visitors and general public" in text_lower:
        details["professional_only"] = 1  # hala B2B potansiyeli var
    elif "public event" in text_lower or "publicly accessible" in text_lower:
        details["professional_only"] = 0

    # ─── 6. DESCRIPTION (ilk cümle) ────────────────────────────────────
    # İlk anlamlı paragraf
    for p_tag in soup.find_all(["p", "div"]):
        p_text = p_tag.get_text(strip=True)
        if len(p_text) > 50 and not p_text.startswith("Trade shows are"):
            details["description"] = p_text[:300]
            break

    # ─── 7. CYCLE (frekans) ────────────────────────────────────────────
    cycle_match = re.search(r'Cycle:\s*(\w+)', text)
    if cycle_match:
        details["cycle"] = cycle_match.group(1)

    # ─── 8. ORGANIZER ──────────────────────────────────────────────────
    # Google Calendar linkindeki location veya sayfadaki "organized by" referansı
    org_match = re.search(r'(?:organized?|organised?) by\s+(.+?)(?:\.|,|\n|and\s)', text, re.IGNORECASE)
    if org_match:
        details["organizer"] = org_match.group(1).strip()[:100]

    # Display e-mail bilgisi varsa (bazen organizer name olarak kullanılabilir)
    if "organizer" not in details:
        # Breadcrumb'da ülke adı var ama organizer yok, en azından venue'yu organizer olarak kullan
        pass

    return details


def _fetch_detail_worker(args):
    """Paralel detay çekimi için worker fonksiyonu."""
    fair, url = args
    try:
        details = scrape_tradefairdates_detail(url)
        if details:
            fair.update(details)
    except Exception:
        pass
    return fair


# ═══════════════════════════════════════════════════════════════════════════
# KATMAN 3: ÇOK DİLLİ ANAHTAR KELİMELER
# ═══════════════════════════════════════════════════════════════════════════

MULTILANG_KEYWORDS = {
    "de": {  # Almanca
        "fair": ["Messe", "Fachmesse", "Ausstellung", "Industriemesse"],
        "exhibition": ["Ausstellung", "Leitmesse"],
        "trade_fair": ["Handelsmesse", "Gewerbemesse"],
    },
    "zh": {  # Çince
        "fair": ["展览会", "博览会", "交易会", "展会"],
        "exhibition": ["国际展览", "工业展"],
    },
    "es": {  # İspanyolca
        "fair": ["feria", "exposición", "salón"],
        "exhibition": ["feria industrial", "feria comercial"],
    },
    "it": {  # İtalyanca
        "fair": ["fiera", "salone", "mostra"],
        "exhibition": ["fiera campionaria", "fiera internazionale"],
    },
    "fr": {  # Fransızca
        "fair": ["salon", "foire", "exposition"],
        "exhibition": ["salon professionnel", "salon industriel"],
    },
    "en": {
        "fair": ["trade fair", "exhibition", "expo", "trade show"],
        "exhibition": ["industrial fair", "world expo"],
    },
    "tr": {
        "fair": ["fuar", "sergi", "fuarı"],
        "exhibition": ["uluslararası fuar", "endüstri fuarı"],
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# ANA ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════

def discover_all(countries: list[str] = None, fetch_details: bool = False,
                 max_per_country: int = None) -> dict:
    """
    Tüm katmanlardan fuarları keşfet ve veritabanına kaydet.

    Args:
        countries: Taranacak ülkeler (None = tümü)
        fetch_details: Her fuarın detay sayfasını da tara
        max_per_country: Ülke başına max fuar (None = sınırsız)

    Returns:
        İstatistikler dict'i
    """
    conn = _get_db()
    stats = {"total": 0, "new": 0, "with_date": 0, "countries_scanned": 0}

    target = countries or list(TARGET_COUNTRIES.keys())

    print(f"\n📡 Fair Discoverer — {len(target)} ülke taranacak")
    print("=" * 50)

    all_fairs = []

    for country_name in target:
        info = TARGET_COUNTRIES.get(country_name)
        if not info:
            print(f"  ⚠️ '{country_name}' bilinen ülkeler arasında değil, atlanıyor")
            continue

        fairs = scrape_tradefairdates_country(country_name, info)
        stats["countries_scanned"] += 1

        if max_per_country:
            fairs = fairs[:max_per_country]

        all_fairs.extend(fairs)
        time.sleep(0.5)

    print(f"\n📋 Toplam {len(all_fairs)} fuar listelendi")

    # ── Detay sayfalarını paralel çek ──
    if fetch_details and all_fairs:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        fairs_with_urls = [(f, f["website"]) for f in all_fairs if f.get("website")]
        print(f"📄 {len(fairs_with_urls)} detay sayfası çekiliyor (paralel)...")

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(_fetch_detail_worker, args): i
                       for i, args in enumerate(fairs_with_urls)}

            done = 0
            for future in as_completed(futures):
                done += 1
                if done % 50 == 0:
                    print(f"    {done}/{len(fairs_with_urls)} sayfa çekildi...")

        print(f"  ✓ {done}/{len(fairs_with_urls)} detay sayfası tamamlandı")

    # ── Geçmiş tarihleri temizle ──
    today_str = date.today().isoformat()
    future_fairs = []
    past_count = 0
    for fair in all_fairs:
        sd = fair.get("start_date")
        if sd and sd < today_str:
            past_count += 1
        else:
            future_fairs.append(fair)

    if past_count:
        print(f"🧹 {past_count} geçmiş tarihli fuar elendi")

    # ── Veritabanına kaydet ──
    for fair in future_fairs:
        upsert_fair(conn, fair)
        stats["total"] += 1
        if fair.get("start_date"):
            stats["with_date"] += 1

    conn.close()

    stats["new"] = stats["total"]
    stats["past_removed"] = past_count
    print(f"\n✅ Tamamlandı: {stats['total']} fuar, {stats['with_date']} tarihli, {stats['countries_scanned']} ülke")
    return stats


def get_discovered_fairs(country: str = None, min_days: int = 0,
                          max_days: int = 365) -> list[dict]:
    """Veritabanındaki fuarları listele."""
    conn = _get_db()
    today = date.today().isoformat()

    if country:
        rows = conn.execute("""
            SELECT * FROM discovered_fairs
            WHERE country = ? AND start_date >= ?
            ORDER BY start_date
        """, (country, today)).fetchall()
    else:
        rows = conn.execute("""
            SELECT * FROM discovered_fairs
            WHERE start_date IS NOT NULL AND start_date >= ?
            ORDER BY start_date
        """, (today,)).fetchall()

    # days_until ekle
    results = []
    for row in rows:
        fair = dict(row)
        if fair.get("start_date"):
            try:
                start = date.fromisoformat(fair["start_date"])
                days_until = (start - date.today()).days
                if min_days <= days_until <= max_days:
                    fair["days_until"] = days_until
                    from fair_calendar import classify_timing
                    fair["timing"] = classify_timing(days_until)
                    results.append(fair)
            except ValueError:
                pass

    return results


def get_db_stats() -> dict:
    """Veritabanı istatistikleri."""
    conn = _get_db()
    total = conn.execute("SELECT COUNT(*) FROM discovered_fairs").fetchone()[0]
    with_date = conn.execute(
        "SELECT COUNT(*) FROM discovered_fairs WHERE start_date IS NOT NULL"
    ).fetchone()[0]
    countries = conn.execute(
        "SELECT COUNT(DISTINCT country) FROM discovered_fairs"
    ).fetchone()[0]
    conn.close()
    return {
        "total_fairs": total,
        "with_date": with_date,
        "countries": countries,
    }


# ═══════════════════════════════════════════════════════════════════════════
# EXHIBITOR ENRICHMENT — Coverage artırma
# ═══════════════════════════════════════════════════════════════════════════

def _extract_exhibitor_count_from_page(url: str) -> Optional[int]:
    """Bir web sayfasından exhibitor/katılımcı sayısını çıkart."""
    soup = _fetch(url)
    if not soup:
        return None

    text = soup.get_text(" ", strip=True)

    # Exhibitor sayısı pattern'leri (çoklu dil)
    patterns = [
        # "1,200 exhibitors", "1.200 Aussteller", "1200 katılımcı"
        r'(\d[\d,.]*)\s*(?:exhibitor|aussteller|katılımcı|exposant|espositore|expositore|participant)',
        # "exhibitors: 1,200"
        r'(?:exhibitor|aussteller|katılımcı|exposant)s?\s*[:\-–]\s*(\d[\d,.]*)',
        # "more than 1,200 companies"  
        r'(?:more than|over|plus de|oltre|más de)\s*(\d[\d,.]*)\s*(?:compan|firm|brand|exhibitor|aussteller)',
        # "1,200+ exhibitors"
        r'(\d[\d,.]*)\+?\s*(?:exhibitor|compan|firm|brand)',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            num_str = match.group(1).replace(',', '').replace('.', '')
            try:
                num = int(num_str)
                if 20 <= num <= 50000:  # Mantıklı aralık
                    return num
            except ValueError:
                pass

    return None


def enrich_exhibitor_coverage(zone: str = "gold", max_fairs: int = 50) -> dict:
    """
    Exhibitor count eksik olan fuarları zenginleştir.
    
    Strateji:
    1. TradeFairDates detail sayfasını tekrar kontrol et
    2. Fuarın resmi web sitesinden exhibitor sayısı çekmeye çalış
    """
    from concurrent.futures import ThreadPoolExecutor

    conn = _get_db()
    today = date.today()

    # Zone'a göre filtrele
    if zone == "gold":
        min_days, max_days = 120, 180
    elif zone == "yellow":
        min_days, max_days = 60, 120
    elif zone == "all":
        min_days, max_days = 30, 365
    else:
        min_days, max_days = 120, 180

    # Exhibitor count OLMAYAN B2B fuarları bul
    rows = conn.execute("""
        SELECT * FROM discovered_fairs
        WHERE professional_only = 1
          AND start_date IS NOT NULL
          AND (exhibitor_count IS NULL OR exhibitor_count = '')
        ORDER BY start_date
    """).fetchall()

    targets = []
    for r in rows:
        try:
            start = date.fromisoformat(r['start_date'])
            days = (start - today).days
            if min_days <= days <= max_days:
                targets.append(dict(r))
        except:
            pass

    if not targets:
        print(f"✅ {zone} zonunda exhibitor count eksik fuar yok!")
        conn.close()
        return {"enriched": 0, "total_checked": 0}

    targets = targets[:max_fairs]
    print(f"🔍 {len(targets)} fuar enrichment'a alınıyor ({zone} zon)...")

    enriched = 0

    def _enrich_one(fair):
        """Tek bir fuarı zenginleştir."""
        nonlocal enriched
        result = {"fair": fair["name"], "count": None, "source": None}

        # 1. TradeFairDates detail sayfası (website alanında kayıtlı)
        tfd_url = fair.get("website", "")
        if tfd_url and "tradefairdates.com" in tfd_url:
            details = scrape_tradefairdates_detail(tfd_url)
            if details.get("exhibitor_count"):
                result["count"] = details["exhibitor_count"]
                result["source"] = "tradefairdates_retry"
                return result

        # 2. Fuarın resmi websitesinden çek
        # TradeFairDates detail sayfasında resmi site linki olabilir
        if tfd_url and "tradefairdates.com" in tfd_url:
            soup = _fetch(tfd_url)
            if soup:
                # "Homepage" veya resmi site linki bul
                for link in soup.find_all("a", href=True):
                    href = link.get("href", "")
                    text = link.get_text(strip=True).lower()
                    if ("homepage" in text or "website" in text or "official" in text) and "http" in href:
                        if "tradefairdates" not in href:
                            count = _extract_exhibitor_count_from_page(href)
                            if count:
                                result["count"] = str(count)
                                result["source"] = "official_website"
                                return result
                            break

        return result

    # Paralel enrichment
    results = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = list(executor.map(_enrich_one, targets))
        done = 0
        for result in futures:
            done += 1
            if done % 10 == 0:
                print(f"    {done}/{len(targets)} kontrol edildi...")

            if result["count"]:
                enriched += 1
                # DB güncelle
                conn.execute("""
                    UPDATE discovered_fairs
                    SET exhibitor_count = ?, last_updated = datetime('now')
                    WHERE slug = ?
                """, (result["count"], _make_slug(result["fair"], "")))
                conn.commit()
                print(f"  ✅ {result['fair']}: {result['count']} exhibitor ({result['source']})")
            results.append(result)

    conn.close()

    stats = {
        "zone": zone,
        "total_checked": len(targets),
        "enriched": enriched,
        "coverage_before": f"{51}/{263}",  # approximate
    }

    # Yeni coverage hesapla
    conn2 = _get_db()
    zone_total = conn2.execute("""
        SELECT COUNT(*) FROM discovered_fairs
        WHERE professional_only = 1 AND start_date IS NOT NULL
    """).fetchone()[0]
    zone_exhib = conn2.execute("""
        SELECT COUNT(*) FROM discovered_fairs
        WHERE professional_only = 1 AND start_date IS NOT NULL
          AND exhibitor_count IS NOT NULL AND exhibitor_count != ''
    """).fetchone()[0]
    conn2.close()

    print(f"\n📊 Enrichment sonucu:")
    print(f"  Kontrol edilen: {len(targets)}")
    print(f"  Yeni exhibitor bulundu: {enriched}")
    print(f"  Toplam exhibitor coverage: {zone_exhib}/{zone_total} ({zone_exhib*100//zone_total}%)")

    return stats

