"""
Exhibitor Pipeline v3 — Data Acquisition Engine

5 Katmanlı Extraction + Akıllı Sınıflandırma:
  Layer 1: STATIC   → requests + bs4 (hızlı, ucuz)
  Layer 2: DETECT   → JS rendering? Login? PDF? (akıllı karar)
  Layer 3: API      → JSON endpoint discovery (browser-free)
  Layer 4: PDF      → Post-show report / exhibitor catalogue (PyMuPDF)
  Layer 5: GOOGLE   → "fair_name exhibitors list" site keşfi

No-List Alt-Kategorileri:
  no_list_search     → Arama motoru bazlı katalog var
  no_list_pdf        → PDF/rapor formatında veri var
  no_list_future     → Liste henüz yayınlanmamış
  no_list_empty      → Sayfa var, veri yok
  login_required     → Giriş gerekli
  js_rendered        → JS rendering, API yok

Recheck Sistemi:
  T-120g → haftada 1
  T-90g  → 3 günde 1
  T-60g  → her gün

Kullanım:
  python exhibitor_pipeline.py                       → Yellow zone, ilk 5
  python exhibitor_pipeline.py --max 20              → Yellow zone, ilk 20
  python exhibitor_pipeline.py --zone gold           → Gold zone
  python exhibitor_pipeline.py --fair "MICAM"        → Tek fuar
  python exhibitor_pipeline.py --status              → İlerleme raporu
  python exhibitor_pipeline.py --recheck             → Başarısızları tekrar dene
  python exhibitor_pipeline.py --diagnose            → No-list fuarları analiz et
"""

import sys
import re
import time
import sqlite3
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, urljoin

# ═══════════════════════════════════════════════════════════════════════════
# PATHS
# ═══════════════════════════════════════════════════════════════════════════

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
FAIR_DB = DATA_DIR / "fair_radar.db"
LEADS_DB = DATA_DIR / "exhibitor_leads.db"

sys.path.insert(0, str(BASE_DIR / "Ajan-bot"))

import requests as req
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
}

STATUS_ICONS = {
    "success": "✅", "partial": "⚠️", "no_list": "📭",
    "no_list_search": "🔎", "no_list_pdf": "📄", "no_list_future": "📅",
    "no_list_empty": "📭", "login_required": "🔒", "js_rendered": "🔄",
    "site_not_found": "🔍", "failed": "❌",
}


# ═══════════════════════════════════════════════════════════════════════════
# LEADS DB
# ═══════════════════════════════════════════════════════════════════════════

def _get_leads_db():
    LEADS_DB.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(LEADS_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS exhibitor_leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fair_slug TEXT NOT NULL,
            fair_name TEXT NOT NULL,
            company_name TEXT NOT NULL,
            website TEXT, email TEXT, phone TEXT,
            country TEXT, booth_number TEXT, sector TEXT, address TEXT,
            scrape_date TEXT DEFAULT (date('now')),
            UNIQUE(fair_slug, company_name)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scrape_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fair_slug TEXT NOT NULL,
            fair_name TEXT NOT NULL,
            status TEXT NOT NULL,
            sub_status TEXT,
            companies_found INTEGER DEFAULT 0,
            method TEXT,
            fair_url TEXT,
            exhibitor_url TEXT,
            error_message TEXT,
            layer TEXT DEFAULT 'static',
            days_until INTEGER,
            scrape_date TEXT DEFAULT (datetime('now'))
        )
    """)
    # sub_status + days_until column migration
    try:
        conn.execute("ALTER TABLE scrape_log ADD COLUMN sub_status TEXT")
    except:
        pass
    try:
        conn.execute("ALTER TABLE scrape_log ADD COLUMN days_until INTEGER")
    except:
        pass
    conn.commit()
    return conn


def _slug(name: str) -> str:
    s = re.sub(r'[^a-z0-9]+', '_', name.lower().strip())
    return s.strip('_')[:50]


# ═══════════════════════════════════════════════════════════════════════════
# DB QUERIES
# ═══════════════════════════════════════════════════════════════════════════

def get_zone_fairs(zone="yellow", with_exhib_only=True):
    conn = sqlite3.connect(str(FAIR_DB))
    conn.row_factory = sqlite3.Row
    today = date.today()
    zones = {"gold": (120, 180), "yellow": (60, 120), "warning": (30, 60), "all": (30, 365)}
    lo, hi = zones.get(zone, (60, 120))
    q = "SELECT * FROM discovered_fairs WHERE professional_only=1 AND start_date IS NOT NULL"
    if with_exhib_only:
        q += " AND exhibitor_count IS NOT NULL AND exhibitor_count != ''"
    q += " ORDER BY CAST(REPLACE(exhibitor_count,',','') AS INTEGER) DESC"
    rows = conn.execute(q).fetchall()
    conn.close()
    out = []
    for r in rows:
        try:
            d = (date.fromisoformat(r['start_date']) - today).days
            if lo <= d <= hi:
                f = dict(r); f['days_until'] = d; out.append(f)
        except:
            pass
    return out


def get_scraped_slugs(success_only=False):
    conn = _get_leads_db()
    where = "WHERE status IN ('success','partial')" if success_only else ""
    rows = conn.execute(f"SELECT DISTINCT fair_slug FROM scrape_log {where}").fetchall()
    conn.close()
    return set(r['fair_slug'] for r in rows)


def get_recheck_candidates():
    """Recheck edilmesi gereken fuarları döndür."""
    conn = _get_leads_db()
    rows = conn.execute("""
        SELECT fair_slug, fair_name, status, sub_status, days_until,
               MAX(scrape_date) as last_scrape, fair_url
        FROM scrape_log
        WHERE status NOT IN ('success')
        GROUP BY fair_slug
        ORDER BY last_scrape ASC
    """).fetchall()
    conn.close()

    today = date.today()
    candidates = []
    for r in rows:
        last = datetime.fromisoformat(r['last_scrape'].replace('Z', ''))
        days_since = (datetime.now() - last).days
        days_until = r['days_until'] or 999

        # Recheck rules
        should_recheck = False
        if days_until > 120:
            should_recheck = days_since >= 7    # Haftada 1
        elif days_until > 90:
            should_recheck = days_since >= 3    # 3 günde 1
        elif days_until > 60:
            should_recheck = days_since >= 1    # Her gün
        else:
            should_recheck = days_since >= 1

        if should_recheck:
            candidates.append(dict(r))

    return candidates


# ═══════════════════════════════════════════════════════════════════════════
# COMPANY NAME VALIDATION
# ═══════════════════════════════════════════════════════════════════════════

SKIP_WORDS = {
    "exhibitor", "filter", "search", "result", "product", "category",
    "all ", "reset", "ana sayfa", "home", "sonuç", "cookie", "participant",
    "premium", "b2b platform", "load more", "show more", "view all",
    "back to", "menu", "navigation", "footer", "header", "login",
    "sign in", "register", "contact", "about", "privacy", "terms",
    "faq", "help", "download", "sponsors", "partner", "accédez",
    "commandez", "contactez", "découvrez", "diffusez", "gagnez",
    "gérez", "guides", "préparez", "visualisez", "questions",
    "votre espace", "candidature", "mot de passe", "identifiant",
}


def _valid_name(name: str) -> bool:
    if not name or len(name) < 3 or len(name) > 150:
        return False
    if re.match(r'^[\d\s,\.]+$', name):
        return False
    if any(skip in name.lower() for skip in SKIP_WORDS):
        return False
    if re.match(r'^(Page|Sayfa)\s+\d+', name):
        return False
    # Mostly non-ASCII navigations (French portal entries etc)
    if len(name.split()) <= 2 and name[0].islower():
        return False
    return True


# ═══════════════════════════════════════════════════════════════════════════
# PARSERS (used across all layers)
# ═══════════════════════════════════════════════════════════════════════════

def _parse_cards(soup) -> list[dict]:
    companies, seen = [], set()
    for h in soup.find_all(["h2", "h3", "h4"]):
        name = h.get_text(strip=True)
        if not _valid_name(name) or name in seen:
            continue
        seen.add(name)
        c = {"name": name}
        parent = h.parent
        if parent:
            for t in parent.stripped_strings:
                t = re.sub(r'\s+', ' ', t).strip()
                if t == name or len(t) < 2 or len(t) > 100:
                    continue
                if any(kw in t for kw in ["Hall", "Salon", "Stand", "Foyer", "Booth"]):
                    c["booth_number"] = t
                elif len(t) < 30 and not c.get("country"):
                    if not any(x in t.lower() for x in ["premium", "logo", "2026", "2025"]):
                        c["country"] = t
        companies.append(c)
    return companies


def _parse_tables(soup) -> list[dict]:
    companies = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 3:
            continue
        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if not cells:
                continue
            name = cells[0].get_text(strip=True)
            if _valid_name(name):
                c = {"name": name}
                if len(cells) > 1: c["country"] = cells[1].get_text(strip=True)[:50]
                if len(cells) > 2: c["booth_number"] = cells[2].get_text(strip=True)
                link = cells[0].find("a", href=True)
                if link and "http" in link.get("href", ""):
                    c["website"] = link["href"]
                companies.append(c)
    return companies


def _parse_links(soup, base_url) -> list[dict]:
    companies, seen = [], set()
    pat = re.compile(r'/(?:exhibitor|katilimci|participant|firma)/[\w-]+$')
    links = soup.find_all("a", href=pat)
    if len(links) < 3:
        return []
    for link in links:
        name = link.get_text(strip=True)
        if _valid_name(name) and name not in seen:
            seen.add(name)
            companies.append({"name": name, "website": urljoin(base_url, link["href"])})
    return companies


def _parse_json_items(items: list) -> list[dict]:
    companies, seen = [], set()
    keys = ["name", "title", "company_name", "company", "exhibitor_name",
            "Name", "Title", "CompanyName", "displayName", "firmName"]
    for item in items:
        if not isinstance(item, dict):
            continue
        name = next((str(item[k]).strip() for k in keys if k in item and item[k]), None)
        if not name or name in seen or not _valid_name(name):
            continue
        seen.add(name)
        companies.append({
            "name": name,
            "website": item.get("website") or item.get("url") or item.get("web"),
            "country": item.get("country") or item.get("Country"),
            "booth_number": item.get("booth") or item.get("stand") or item.get("hall"),
            "sector": item.get("sector") or item.get("category"),
            "email": item.get("email"), "phone": item.get("phone"),
        })
    return companies


# ═══════════════════════════════════════════════════════════════════════════
# LAYER 1: STATIC (requests + bs4)
# ═══════════════════════════════════════════════════════════════════════════

PLAT_PREFIXES = ["platform", "exhibitors", "catalog", "directory", "visitors"]
PLAT_PATHS = ["/participants", "/participants/all", "/exhibitors",
              "/exhibitor-list", "/companies", ""]


def _detect_login(soup, text_lower: str) -> bool:
    pw = soup.find("input", {"type": "password"})
    if pw:
        return True
    markers = ["login", "sign in", "log in", "connexion", "giriş yap",
               "your password", "mot de passe"]
    form = soup.find("form")
    return bool(form and sum(1 for m in markers if m in text_lower) >= 2)


def _layer1_platform(fair_url: str) -> dict:
    if not fair_url:
        return {}
    domain = urlparse(fair_url).netloc.replace("www.", "")
    for prefix in PLAT_PREFIXES:
        for path in PLAT_PATHS:
            url = f"https://{prefix}.{domain}{path}"
            try:
                r = req.get(url, headers=HEADERS, timeout=8, allow_redirects=True)
                if r.status_code == 200 and len(r.text) > 1000:
                    soup = BeautifulSoup(r.text, "html.parser")
                    txt = soup.get_text().lower()
                    if any(kw in txt for kw in ["exhibitor", "participant", "katılımcı",
                                                 "company", "aussteller", "exposant"]):
                        if _detect_login(soup, txt):
                            return {"status": "login_required", "fair_url": fair_url,
                                    "exhibitor_url": url}
                        cos = _parse_cards(soup)
                        if cos:
                            return {"fair_url": fair_url, "exhibitor_url": url,
                                    "companies": cos, "method": "platform_subdomain",
                                    "status": "success" if len(cos) >= 10 else "partial"}
            except:
                continue
    return {}


def _layer1_smart(fair_name: str) -> dict:
    try:
        from scrapers.smart_discoverer import SmartFairDiscoverer
        return SmartFairDiscoverer().discover_and_scrape(fair_name, enrich_details=False)
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# LAYER 2: SMART CLASSIFY — neden veri yok?
# ═══════════════════════════════════════════════════════════════════════════

def _classify_no_list(fair_url: str, exhibitor_url: str = None, days: int = 999) -> dict:
    """
    Neden exhibitor listesi yok? Alt-sınıflandırma.

    Returns:
        status:     ana status
        sub_status: detay
        reason:     açıklama
        needs_browser: JS rendering gerekli mi
        pdf_urls:   bulunan PDF linkleri
        exhibitor_url: bulunan exhibitor sayfası
    """
    target = exhibitor_url or fair_url
    if not target:
        return {"status": "site_not_found", "sub_status": "no_url"}

    try:
        r = req.get(target, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return {"status": "no_list", "sub_status": "http_error",
                    "reason": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"status": "no_list", "sub_status": "connection_error",
                "reason": str(e)}

    soup = BeautifulSoup(r.text, "html.parser")
    html = r.text
    text = soup.get_text(strip=True).lower()

    # ── Login page ──
    if _detect_login(soup, text):
        return {"status": "login_required", "sub_status": "login_wall",
                "exhibitor_url": target}

    # ── PDF discovery ──
    pdf_urls = _find_pdf_links(soup, fair_url, text)
    if pdf_urls:
        return {"status": "no_list_pdf", "sub_status": "pdf_available",
                "pdf_urls": pdf_urls, "exhibitor_url": target,
                "reason": f"{len(pdf_urls)} PDF bulundu"}

    # ── JS rendering signals ──
    js_score = 0
    body = soup.find("body")
    if body and len(body.get_text(strip=True)) < 200:
        js_score += 3
    spa = ['id="app"', 'id="root"', 'id="__next"', 'id="__nuxt"',
           "__NEXT_DATA__", "__NUXT__", "ng-app", "data-reactroot"]
    if any(m in html for m in spa):
        js_score += 2
    if any(x in text for x in ["loading...", "yükleniyor", "chargement"]):
        js_score += 2
    scripts = soup.find_all("script")
    if len(scripts) > 10 and len(text) < 500:
        js_score += 2
    for s in scripts:
        src = s.get("src", "")
        if any(x in src.lower() for x in ["chunk", "bundle", "webpack", "app."]):
            js_score += 1; break

    if js_score >= 3:
        return {"status": "js_rendered", "sub_status": f"js_score_{js_score}",
                "needs_browser": True, "js_signals": js_score,
                "exhibitor_url": target}

    # ── Search-based catalogue ──
    search_markers = ["search exhibitor", "find exhibitor", "exhibitor search",
                      "katılımcı arama", "rechercher", "suche"]
    if any(m in text for m in search_markers):
        search_url = None
        for link in soup.find_all("a", href=True):
            lt = (link.get_text(strip=True) + " " + link["href"]).lower()
            if any(m in lt for m in ["search", "arama", "recherch", "suche"]):
                search_url = urljoin(fair_url, link["href"])
                break
        return {"status": "no_list_search", "sub_status": "search_based",
                "exhibitor_url": search_url or target,
                "reason": "Arama motoru bazlı katalog"}

    # ── "Coming soon" / future ──
    future_markers = ["coming soon", "stay tuned", "will be announced",
                      "registration opens", "açıklanacak", "yakında",
                      "to be confirmed", "tba", "exhibitor list will"]
    if any(m in text for m in future_markers) or days > 120:
        return {"status": "no_list_future", "sub_status": "not_published_yet",
                "exhibitor_url": target,
                "reason": "Liste henüz yayınlanmamış"}

    # ── Exhibitor page discovered but empty ──
    exhib_url = None
    for link in soup.find_all("a", href=True):
        lt = (link.get_text(strip=True) + " " + link["href"]).lower()
        if any(kw in lt for kw in ["exhibitor", "katılımcı", "participant", "exposant"]):
            exhib_url = urljoin(fair_url, link["href"])
            break

    return {"status": "no_list_empty", "sub_status": "page_empty",
            "exhibitor_url": exhib_url or target,
            "reason": "Sayfa var, veri yok"}


def _find_pdf_links(soup, base_url: str, text: str) -> list[str]:
    """PDF exhibitor list / catalogue linkleri bul."""
    pdfs = []
    keywords = ["exhibitor", "catalogue", "catalog", "katılımcı", "participant",
                "exhibitor-list", "company-list", "post-show", "report"]
    for link in soup.find_all("a", href=True):
        href = link["href"]
        link_text = (link.get_text(strip=True) + " " + href).lower()
        if href.lower().endswith(".pdf"):
            if any(kw in link_text for kw in keywords):
                pdfs.append(urljoin(base_url, href))
        elif "download" in link_text and any(kw in link_text for kw in keywords):
            pdfs.append(urljoin(base_url, href))
    return pdfs[:5]


# ═══════════════════════════════════════════════════════════════════════════
# LAYER 3: API DISCOVERY (browser-free)
# ═══════════════════════════════════════════════════════════════════════════

def _layer3_api(fair_url: str, exhibitor_url: str) -> dict:
    target = exhibitor_url or fair_url
    companies = []
    domain = urlparse(target).netloc
    base = f"https://{domain}"

    # 1. __NEXT_DATA__ / inline JSON
    try:
        r = req.get(target, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")

            # Next.js
            ns = soup.find("script", id="__NEXT_DATA__")
            if ns and ns.string:
                try:
                    data = json.loads(ns.string)
                    items = _dig_list(data.get("props", {}).get("pageProps", {}),
                                     ["exhibitors", "companies", "items", "participants",
                                      "data", "results", "list"])
                    if items:
                        companies = _parse_json_items(items)
                except:
                    pass

            # Inline JSON arrays
            if not companies:
                for script in soup.find_all("script"):
                    txt = script.string or ""
                    for m in re.findall(r'(\[{[^]]{500,}}])', txt)[:3]:
                        try:
                            arr = json.loads(m)
                            if isinstance(arr, list) and len(arr) > 5:
                                sample = arr[0] if arr else {}
                                if isinstance(sample, dict) and any(
                                    k in sample for k in ["name", "title", "company",
                                                           "company_name", "Name", "Title"]):
                                    companies = _parse_json_items(arr)
                                    if companies:
                                        break
                        except:
                            pass

            # Script API references
            if not companies:
                for script in soup.find_all("script"):
                    txt = script.string or ""
                    for m in re.findall(r'["\'](https?://[^"\']*?/api/[^"\']*?)["\']', txt):
                        if "exhibitor" in m.lower() or "participant" in m.lower():
                            c = _try_api(m)
                            if c:
                                companies = c; break
                    for m in re.findall(r'fetch\(["\']([^"\']+)["\']', txt):
                        if "exhibitor" in m.lower() or "participant" in m.lower():
                            c = _try_api(urljoin(base, m))
                            if c:
                                companies = c; break
                    if companies:
                        break
    except:
        pass

    # 2. Common REST endpoints
    if not companies:
        paths = ["/api/exhibitors", "/api/v1/exhibitors", "/api/v2/exhibitors",
                 "/api/participants", "/api/companies", "/api/exhibitor/list",
                 "/_api/exhibitors", "/wp-json/wp/v2/exhibitor"]
        main = domain.replace("www.", "")
        bases = [base] + [f"https://{p}.{main}" for p in ["api", "platform", "exhibitors"]]
        for b in bases:
            for p in paths:
                c = _try_api(f"{b}{p}")
                if c:
                    companies = c; break
            if companies:
                break

    # 3. Sitemap exhibitor URLs
    if not companies:
        companies = _try_sitemap(base)

    status = "success" if len(companies) >= 10 else ("partial" if companies else "js_rendered")
    return {"fair_url": fair_url, "exhibitor_url": target,
            "companies": companies, "method": "api_discovery", "status": status}


def _dig_list(data, keys):
    if not isinstance(data, dict):
        return []
    for k in keys:
        if k in data:
            v = data[k]
            if isinstance(v, list) and len(v) > 3:
                return v
            if isinstance(v, dict):
                for sk in keys:
                    if sk in v and isinstance(v[sk], list):
                        return v[sk]
    for v in data.values():
        if isinstance(v, dict):
            r = _dig_list(v, keys)
            if r:
                return r
    return []


def _try_api(url: str) -> list[dict]:
    try:
        r = req.get(url, headers={**HEADERS, "Accept": "application/json"}, timeout=5)
        if r.status_code != 200:
            return []
        ct = r.headers.get("content-type", "")
        if "json" not in ct and "javascript" not in ct:
            return []
        data = r.json()
        items = data if isinstance(data, list) else (
            data.get("data") or data.get("items") or data.get("results") or
            data.get("exhibitors") or data.get("participants") or
            data.get("companies") or data.get("records") or [])
        if isinstance(items, list) and len(items) > 3:
            return _parse_json_items(items)
    except:
        pass
    return []


def _try_sitemap(base_url: str) -> list[dict]:
    companies = []
    for url in [f"{base_url}/sitemap.xml", f"{base_url}/sitemap_index.xml"]:
        try:
            r = req.get(url, headers=HEADERS, timeout=5)
            if r.status_code != 200:
                continue
            for eu in re.findall(
                r'<loc>([^<]*(?:exhibitor|participant|katilimci|firma)/[^<]+)</loc>',
                r.text, re.I):
                slug = eu.rstrip("/").split("/")[-1]
                name = slug.replace("-", " ").replace("_", " ").strip().title()
                if _valid_name(name):
                    companies.append({"name": name, "website": eu})
        except:
            pass
        if companies:
            break
    return companies


# ═══════════════════════════════════════════════════════════════════════════
# LAYER 4: PDF EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════

def _layer4_pdf(pdf_urls: list, fair_url: str) -> dict:
    """PDF'lerden firma isimlerini çıkar."""
    if not pdf_urls:
        return {"status": "no_list_pdf", "companies": []}

    companies = []
    for pdf_url in pdf_urls[:3]:
        try:
            print(f"    📄 PDF: {pdf_url[:60]}...")
            r = req.get(pdf_url, headers=HEADERS, timeout=15)
            if r.status_code != 200 or len(r.content) < 1000:
                continue

            # Save temp PDF
            tmp = DATA_DIR / "_temp.pdf"
            tmp.write_bytes(r.content)

            try:
                import fitz  # PyMuPDF
                doc = fitz.open(str(tmp))
                all_text = ""
                for page in doc:
                    all_text += page.get_text() + "\n"
                doc.close()

                # Extract company names from PDF text
                pdf_companies = _extract_names_from_text(all_text)
                if pdf_companies:
                    companies.extend(pdf_companies)
                    print(f"    ✅ PDF: {len(pdf_companies)} firma")
            except ImportError:
                # Try basic text extraction without PyMuPDF
                print(f"    ⚠️ PyMuPDF yüklü değil, PDF parse edilemedi")
            finally:
                tmp.unlink(missing_ok=True)

        except Exception as e:
            print(f"    ❌ PDF error: {e}")

    # Deduplicate
    seen = set()
    unique = []
    for c in companies:
        if c["name"] not in seen:
            seen.add(c["name"])
            unique.append(c)

    status = "success" if len(unique) >= 10 else ("partial" if unique else "no_list_pdf")
    return {"fair_url": fair_url, "companies": unique,
            "method": "pdf_extraction", "status": status}


def _extract_names_from_text(text: str) -> list[dict]:
    """PDF/text'ten firma isimlerini çıkar."""
    companies = []
    lines = text.split("\n")

    for line in lines:
        line = line.strip()
        if not line or len(line) < 4 or len(line) > 120:
            continue
        # Company name heuristics: starts uppercase, not too long
        if (line[0].isupper() and
            not line.startswith(("Page ", "Table ", "Figure ", "Chapter ")) and
            not re.match(r'^[\d\s,\.\-]+$', line) and
            not any(x in line.lower() for x in
                    ["copyright", "all rights", "www.", "http", "@",
                     "page ", "date:", "venue:", "hall ", "booth "])):
            # Filter: must have at least one uppercase word > 3 chars
            words = line.split()
            upper_words = [w for w in words if len(w) > 3 and w[0].isupper()]
            if upper_words and _valid_name(line):
                companies.append({"name": line})

    return companies[:500]  # cap


# ═══════════════════════════════════════════════════════════════════════════
# LAYER 5: GOOGLE FALLBACK (en son çare)
# ═══════════════════════════════════════════════════════════════════════════

def _layer5_google(fair_name: str) -> dict:
    """Google'da exhibitor list / participant list ara."""
    # Bu şimdilik placeholder — search API veya scraping gerektirir
    return {"status": "no_list", "companies": []}


# ═══════════════════════════════════════════════════════════════════════════
# SAVE
# ═══════════════════════════════════════════════════════════════════════════

def save_result(slug, fair_name, result, layer, days_until=None):
    conn = _get_leads_db()
    companies = result.get("companies", [])
    method = result.get("method", "unknown")
    fair_url = result.get("fair_url", "")
    exhibitor_url = result.get("exhibitor_url", "")
    status = result.get("status", "failed")
    sub_status = result.get("sub_status", "")
    error = result.get("error", "")

    if companies:
        status = "success" if len(companies) >= 10 else "partial"

    conn.execute("""
        INSERT INTO scrape_log (fair_slug, fair_name, status, sub_status,
                                companies_found, method, fair_url, exhibitor_url,
                                error_message, layer, days_until)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (slug, fair_name, status, sub_status, len(companies),
          method, fair_url, exhibitor_url, error, layer, days_until))

    saved = 0
    for c in companies:
        try:
            if hasattr(c, 'to_dict'):
                c = c.to_dict()
            conn.execute("""
                INSERT OR IGNORE INTO exhibitor_leads
                    (fair_slug, fair_name, company_name, website, email,
                     phone, country, booth_number, sector, address)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (slug, fair_name, c.get("name", ""),
                  c.get("website", ""), c.get("email", ""), c.get("phone", ""),
                  c.get("country", ""), c.get("booth_number", ""),
                  c.get("sector", ""), c.get("address", "")))
            saved += 1
        except:
            pass
    conn.commit()
    conn.close()
    return saved, status


# ═══════════════════════════════════════════════════════════════════════════
# MAIN PIPELINE — 5 Layer Orchestration
# ═══════════════════════════════════════════════════════════════════════════

def scrape_fair(fair: dict, use_browser: bool = True) -> dict:
    fair_name = fair['name']
    slug = _slug(fair_name)
    days = fair.get('days_until', 999)

    print(f"\n  🔍 [{fair_name}]")

    # ── Find website ──
    print(f"    L0: Website keşfi...")
    fair_url = _find_url(fair_name)
    if not fair_url:
        print(f"    ❌ Site bulunamadı")
        return {"status": "site_not_found", "fair_url": None}
    print(f"    ✓ {fair_url}")

    # ═════ LAYER 1: STATIC ═════
    print(f"    L1: Static scan...")
    result = _layer1_platform(fair_url)
    if result.get("status") == "login_required":
        print(f"    🔒 Login gerekli")
        return result
    if result.get("companies"):
        n = len(result["companies"])
        print(f"    ✅ L1 Platform: {n} firma")
        result["layer"] = "static"
        return result

    smart = _layer1_smart(fair_name)
    if smart.get("companies"):
        n = len(smart["companies"])
        print(f"    ✅ L1 Smart: {n} firma")
        smart["layer"] = "static"
        smart["status"] = "success" if n >= 10 else "partial"
        return smart

    exhibitor_url = smart.get("exhibitor_url") or result.get("exhibitor_url")

    # ═════ LAYER 1.5: NAVIGATOR (structure-aware) ═════
    if exhibitor_url:
        print(f"    L1.5: Navigator (structure-aware)...")
        nav_result = _layer15_navigator(exhibitor_url, fair_url)
        if nav_result.get("companies"):
            n = len(nav_result["companies"])
            print(f"    ✅ L1.5 Navigator: {n} firma")
            return nav_result

    # ═════ LAYER 2: CLASSIFY ═════
    print(f"    L2: Sınıflandırma...")
    classify = _classify_no_list(fair_url, exhibitor_url, days)

    if classify.get("status") == "login_required":
        print(f"    🔒 Login gerekli")
        return classify

    if classify.get("status") == "no_list_pdf":
        # ═════ LAYER 4: PDF ═════
        pdf_urls = classify.get("pdf_urls", [])
        print(f"    L4: PDF extraction ({len(pdf_urls)} dosya)...")
        pdf_result = _layer4_pdf(pdf_urls, fair_url)
        if pdf_result.get("companies"):
            pdf_result["layer"] = "pdf"
            return pdf_result

    needs_browser = classify.get("needs_browser", False)
    if needs_browser and use_browser:
        # ═════ LAYER 3: API DISCOVERY ═════
        target = classify.get("exhibitor_url") or exhibitor_url or fair_url
        print(f"    L3: API Discovery (JS={classify.get('js_signals', 0)})...")
        api_result = _layer3_api(fair_url, target)
        api_result["layer"] = "api"
        if api_result.get("companies"):
            n = len(api_result["companies"])
            print(f"    ✅ L3 API: {n} firma")
            return api_result
        print(f"    📭 L3: API bulunamadı")

    # ═════ LAYER 5: PAST YEAR EXHIBITOR SEARCH ═════
    print(f"    L5: Geçmiş yıl exhibitor arama...")
    past = _try_past_years(fair_name, fair_url)
    if past.get("companies"):
        n = len(past["companies"])
        print(f"    ✅ L5 Geçmiş yıl: {n} firma")
        past["layer"] = "past_year"
        return past

    # ═════ Final classification ═════
    status = classify.get("status", "no_list")
    sub = classify.get("sub_status", "")
    reason = classify.get("reason", "")
    icon = STATUS_ICONS.get(status, "❓")
    print(f"    {icon} {status}: {reason}")

    return {"status": status, "sub_status": sub,
            "fair_url": fair_url, "exhibitor_url": exhibitor_url,
            "companies": []}


def _try_past_years(fair_name: str, fair_url: str) -> dict:
    """Geçmiş yılların exhibitor listelerini ara."""
    if not fair_url:
        return {"companies": []}

    domain = urlparse(fair_url).netloc
    base = f"https://{domain}"
    name_slug = re.sub(r'[^a-z0-9]+', '-', fair_name.lower()).strip('-')

    # Past year URL patterns
    past_urls = []
    for year in [2025, 2024, 2023]:
        past_urls.extend([
            f"{base}/{year}/exhibitors",
            f"{base}/{year}/exhibitor-list",
            f"{base}/en/{year}/exhibitors",
            f"{base}/{year}/participants",
            f"{base}/exhibitors-{year}",
            f"{base}/exhibitor-list-{year}",
            f"{base}/past-exhibitors",
            f"{base}/exhibitor-archive",
            f"{base}/exhibitor-catalogue",
        ])
    # Also try year-based subdomains / domains
    main_domain = domain.replace("www.", "")
    for year in [2025, 2024]:
        past_urls.extend([
            f"https://{year}.{main_domain}/exhibitors",
            f"https://{main_domain}/{year}/exhibitors",
        ])

    for url in past_urls[:20]:  # limit probes
        try:
            r = req.get(url, headers=HEADERS, timeout=5, allow_redirects=True)
            if r.status_code == 200 and len(r.text) > 2000:
                soup = BeautifulSoup(r.text, "html.parser")
                text = soup.get_text().lower()
                if any(kw in text for kw in ["exhibitor", "participant", "company",
                                              "katılımcı", "aussteller"]):
                    # Try parsing
                    companies = _parse_cards(soup) or _parse_tables(soup) or _parse_links(soup, url)
                    if companies:
                        status = "success" if len(companies) >= 10 else "partial"
                        return {"fair_url": fair_url, "exhibitor_url": url,
                                "companies": companies, "method": f"past_year_{url.split('/')[3] if len(url.split('/'))>3 else ''}",
                                "status": status}
        except:
            continue

    return {"companies": []}


def _layer15_navigator(exhibitor_url: str, fair_url: str) -> dict:
    """Layer 1.5: Structure-aware page navigation using ExhibitorNavigator."""
    try:
        from exhibitor_navigator import ExhibitorNavigator
        nav = ExhibitorNavigator(timeout=12, delay=0.5, max_pages=30)
        result = nav.navigate(exhibitor_url, fair_url)

        if result.companies:
            # Convert navigator company names to pipeline format
            companies = []
            for name in result.companies:
                companies.append({"name": name, "website": None, "country": None})

            status = "success" if len(companies) >= 10 else "partial"
            return {
                "fair_url": fair_url,
                "exhibitor_url": exhibitor_url,
                "companies": companies,
                "method": result.method,
                "status": status,
                "layer": "navigator",
                "nav_meta": {
                    "list_type": result.list_type,
                    "visited_urls": result.visited_urls,
                    "companies_found": result.companies_found,
                    "deduplicated": result.deduplicated_companies,
                    "navigation": result.navigation_detected,
                },
            }
    except Exception as e:
        print(f"    ⚠️ Navigator error: {e}")

    return {"companies": []}


def _find_url(fair_name: str) -> Optional[str]:
    try:
        from scrapers.smart_discoverer import SmartFairDiscoverer
        return SmartFairDiscoverer()._find_fair_website(fair_name)
    except:
        return None


# ═══════════════════════════════════════════════════════════════════════════
# PIPELINE RUNNERS
# ═══════════════════════════════════════════════════════════════════════════

def run_pipeline(zone="yellow", max_fairs=5, fair_filter=None, use_browser=True):
    print("=" * 70)
    print(f"🔥 EXHIBITOR PIPELINE v3 — {zone.upper()} ZONE")
    print(f"   L1:Static → L2:Classify → L3:API → L4:PDF")
    print("=" * 70)

    if fair_filter:
        fairs = []
        for z in ["yellow", "gold", "warning", "all"]:
            cands = get_zone_fairs(z, with_exhib_only=False)
            fairs = [f for f in cands if fair_filter.lower() in f['name'].lower()]
            if fairs:
                break
    else:
        fairs = get_zone_fairs(zone, with_exhib_only=True)

    if not fairs:
        print("⚠️ Fuar bulunamadı!")
        return

    done = get_scraped_slugs()
    remaining = [f for f in fairs if _slug(f['name']) not in done]
    print(f"\n📊 {len(fairs)} fuar | Done: {len(fairs)-len(remaining)} | Kalan: {len(remaining)}")

    targets = remaining[:max_fairs] if not fair_filter else fairs[:max_fairs]
    if not targets:
        print("✅ Tüm fuarlar done!")
        return

    stats = {k: 0 for k in STATUS_ICONS}
    stats["total_companies"] = 0

    for i, fair in enumerate(targets, 1):
        slug = _slug(fair['name'])
        days = fair.get('days_until', '?')
        exhib = fair.get('exhibitor_count', '?')

        print(f"\n{'─' * 70}")
        print(f"[{i}/{len(targets)}] {fair['name']}")
        print(f"  📍 {fair.get('city','')} / {fair.get('country','')} | "
              f"📅 {fair.get('start_date','')} ({days}g) | 👥 {exhib}")
        print(f"{'─' * 70}")

        result = scrape_fair(fair, use_browser)
        saved, final = save_result(slug, fair['name'], result,
                                    result.get("layer", "unknown"),
                                    fair.get('days_until'))
        stats[final] = stats.get(final, 0) + 1
        stats["total_companies"] += saved
        icon = STATUS_ICONS.get(final, "❓")
        print(f"\n  {icon} {final.upper()} | {saved} firma")

        if i < len(targets):
            time.sleep(2)

    print(f"\n{'=' * 70}")
    print(f"📊 PIPELINE v3 SONUCU")
    print(f"{'=' * 70}")
    for k in ["success", "partial", "no_list_pdf", "no_list_search",
              "no_list_future", "no_list_empty", "no_list",
              "login_required", "js_rendered", "site_not_found", "failed"]:
        if stats.get(k, 0) > 0:
            icon = STATUS_ICONS.get(k, " ")
            print(f"  {icon} {k:20s}: {stats[k]}")
    print(f"  📦 {'Toplam firma':20s}: {stats['total_companies']}")
    print(f"{'=' * 70}")


def run_recheck():
    """Başarısız fuarları recheck et."""
    print("=" * 70)
    print("🔄 RECHECK — Başarısız Fuarları Yeniden Dene")
    print("=" * 70)

    candidates = get_recheck_candidates()
    if not candidates:
        print("✅ Recheck edilecek fuar yok!")
        return

    print(f"\n📊 {len(candidates)} fuar recheck edilecek")

    for i, c in enumerate(candidates, 1):
        print(f"\n[{i}/{len(candidates)}] {c['fair_name']} (son: {c['status']})")
        # Find fair in DB
        for z in ["yellow", "gold", "warning", "all"]:
            fairs = get_zone_fairs(z, with_exhib_only=False)
            matches = [f for f in fairs if _slug(f['name']) == c['fair_slug']]
            if matches:
                result = scrape_fair(matches[0])
                save_result(c['fair_slug'], c['fair_name'], result,
                           result.get("layer", "unknown"),
                           matches[0].get('days_until'))
                break
        time.sleep(2)


def run_diagnose():
    """No-list fuarları detaylı analiz et."""
    conn = _get_leads_db()
    rows = conn.execute("""
        SELECT DISTINCT fair_slug, fair_name, status, sub_status, fair_url,
               exhibitor_url, days_until
        FROM scrape_log
        WHERE status NOT IN ('success', 'partial')
        ORDER BY status, fair_name
    """).fetchall()
    conn.close()

    print("=" * 70)
    print("🔬 DİAGNOSTİK — Neden Veri Yok?")
    print("=" * 70)

    by_status = {}
    for r in rows:
        s = r['status']
        if s not in by_status:
            by_status[s] = []
        by_status[s].append(dict(r))

    for status, fairs in sorted(by_status.items()):
        icon = STATUS_ICONS.get(status, "❓")
        print(f"\n{icon} {status.upper()} ({len(fairs)} fuar)")
        print(f"  {'─' * 60}")
        for f in fairs:
            sub = f.get('sub_status') or '-'
            url = (f.get('fair_url') or '-')[:50]
            days = f.get('days_until') or '?'
            print(f"  {f['fair_name'][:35]:35s} | {sub:20s} | {str(days):>4s}g | {url}")

    # Actionable summary
    total = len(rows)
    print(f"\n{'=' * 70}")
    print(f"📊 ÖZET: {total} fuar veri yok")
    print(f"  🔍 site_not_found: {len(by_status.get('site_not_found', []))}")
    print(f"  📭 no_list:        {len(by_status.get('no_list', []) + by_status.get('no_list_empty', []))}")
    print(f"  📅 no_list_future: {len(by_status.get('no_list_future', []))}")
    print(f"  📄 no_list_pdf:    {len(by_status.get('no_list_pdf', []))}")
    print(f"  🔎 no_list_search: {len(by_status.get('no_list_search', []))}")
    print(f"  🔒 login_required: {len(by_status.get('login_required', []))}")
    print(f"  🔄 js_rendered:    {len(by_status.get('js_rendered', []))}")


# ═══════════════════════════════════════════════════════════════════════════
# STATUS
# ═══════════════════════════════════════════════════════════════════════════

def show_status():
    conn = _get_leads_db()
    total_leads = conn.execute("SELECT COUNT(*) FROM exhibitor_leads").fetchone()[0]
    total_fairs = conn.execute("SELECT COUNT(DISTINCT fair_slug) FROM exhibitor_leads").fetchone()[0]

    print("=" * 70)
    print("📊 EXHIBITOR PIPELINE v3 — STATUS")
    print("=" * 70)
    print(f"\n  📦 Toplam firma (lead): {total_leads}")
    print(f"  🏢 Exhibitor listeli fuar: {total_fairs}")

    # Access rate
    all_scrapes = conn.execute("SELECT COUNT(DISTINCT fair_slug) FROM scrape_log").fetchone()[0]
    if all_scrapes > 0:
        rate = (total_fairs * 100) // all_scrapes
        print(f"  📈 Exhibitor Access Rate: {total_fairs}/{all_scrapes} = {rate}%")

    # Status breakdown
    rows = conn.execute("""
        SELECT status, COUNT(*) as cnt, SUM(companies_found) as total_co
        FROM scrape_log GROUP BY status ORDER BY total_co DESC
    """).fetchall()

    if rows:
        print(f"\n  Status Breakdown:")
        for r in rows:
            icon = STATUS_ICONS.get(r['status'], "❓")
            print(f"    {icon} {r['status']:20s}: {r['cnt']:>3d} fuar | {r['total_co'] or 0:>5d} firma")

    # TOP fairs by leads
    top = conn.execute("""
        SELECT fair_name, COUNT(*) as cnt FROM exhibitor_leads
        GROUP BY fair_slug ORDER BY cnt DESC LIMIT 5
    """).fetchall()
    if top:
        print(f"\n  🏆 TOP Fuarlar:")
        for r in top:
            print(f"    {r[1]:>5d} firma | {r[0]}")

    # Recent
    recent = conn.execute("""
        SELECT fair_name, status, sub_status, companies_found, layer
        FROM scrape_log ORDER BY scrape_date DESC LIMIT 10
    """).fetchall()
    if recent:
        print(f"\n  Son 10:")
        for r in recent:
            icon = STATUS_ICONS.get(r['status'], "❓")
            sub = r['sub_status'] or ''
            print(f"    {icon} {r['fair_name'][:30]:30s} | {r['companies_found']:>4d} | "
                  f"{r['status']:15s} | {sub}")

    # Zone coverage
    for zn, zr in [("YELLOW", "60-120g"), ("GOLD", "120-180g")]:
        zf = get_zone_fairs(zn.lower(), True)
        done = get_scraped_slugs()
        d = len([f for f in zf if _slug(f['name']) in done])
        t = len(zf)
        p = d * 100 // max(t, 1)
        print(f"\n  {'🟡' if zn=='YELLOW' else '🔥'} {zn} ({zr}): {d}/{t} = {p}%")

    # Recheck candidates
    rc = get_recheck_candidates()
    if rc:
        print(f"\n  🔄 Recheck bekleyen: {len(rc)} fuar")

    conn.close()


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    args = sys.argv[1:]

    if "--status" in args:
        show_status()
    elif "--recheck" in args:
        run_recheck()
    elif "--diagnose" in args:
        run_diagnose()
    else:
        zone = "yellow"
        max_fairs = 5
        fair_filter = None
        use_browser = "--no-browser" not in args

        for i, arg in enumerate(args):
            if arg == "--zone" and i+1 < len(args): zone = args[i+1]
            elif arg == "--max" and i+1 < len(args): max_fairs = int(args[i+1])
            elif arg == "--fair" and i+1 < len(args): fair_filter = args[i+1]

        run_pipeline(zone, max_fairs, fair_filter, use_browser)
