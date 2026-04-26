"""
Smart Fair Discoverer
Given a fair name, automatically finds the exhibitor list URL
and scrapes companies using web search + known patterns.
"""

import re
import time
import string
import requests
from typing import Optional
from urllib.parse import urljoin, urlparse, quote_plus
from bs4 import BeautifulSoup
from rich.console import Console

import config
from scrapers.base_scraper import BaseScraper, CompanyData

console = Console()

# Turkish alphabet for letter filtering
TR_ALPHABET = list(string.ascii_uppercase) + ["Ç", "Ğ", "İ", "Ö", "Ş", "Ü"]

# Common exhibitor page paths
EXHIBITOR_PATHS = [
    "/exhibitors", "/exhibitor-list", "/exhibitor",
    "/katilimcilar", "/katilimci-listesi", "/katilimci-listesi-app",
    "/participants", "/participant-list",
    "/en/exhibitors", "/en/exhibitor-list",
    "/tr/katilimcilar", "/tr/katilimci-listesi",
    "/companies", "/firmalar",
]

# Common pagination params
PAGINATION_PARAMS = ["page", "p", "sayfa"]
# Common letter filter params
LETTER_PARAMS = ["letter", "a", "harf", "l"]


class SmartFairDiscoverer:
    """
    Smart system that takes a fair name, finds its exhibitor list,
    and scrapes all company data automatically.
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": config.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        })

    def discover_and_scrape(self, fair_name: str, enrich_details: bool = True) -> dict:
        """
        Main entry point. Given a fair name:
        1. Find the fair's official website
        2. Find the exhibitor list page
        3. Scrape all companies
        4. Return structured data

        Returns dict with:
            fair_url: str
            exhibitor_url: str
            companies: list[CompanyData]
            method: str (how the data was found)
        """
        console.print(f"\n[bold blue]🔍 Smart Discovery: '{fair_name}'[/bold blue]")

        result = {
            "fair_name": fair_name,
            "fair_url": None,
            "exhibitor_url": None,
            "companies": [],
            "method": None,
        }

        # Step 1: Find the fair's official website
        console.print(f"\n  [bold]Step 1: Finding fair website...[/bold]")
        fair_url = self._find_fair_website(fair_name)
        if not fair_url:
            console.print(f"  [red]Could not find website for '{fair_name}'[/red]")
            return result
        result["fair_url"] = fair_url
        console.print(f"  [green]✓ Found: {fair_url}[/green]")

        # Step 2: Find the exhibitor list page
        console.print(f"\n  [bold]Step 2: Finding exhibitor list...[/bold]")
        exhibitor_url = self._find_exhibitor_page(fair_url)
        if not exhibitor_url:
            console.print(f"  [yellow]⚠ No exhibitor page found via URL probing[/yellow]")
            console.print(f"  [dim]Trying homepage link discovery...[/dim]")
            exhibitor_url = self._discover_from_homepage(fair_url)

        if exhibitor_url:
            result["exhibitor_url"] = exhibitor_url
            console.print(f"  [green]✓ Found exhibitor page: {exhibitor_url}[/green]")
        else:
            console.print(f"  [yellow]⚠ Could not find exhibitor list page[/yellow]")
            return result

        # Step 3: Scrape companies
        console.print(f"\n  [bold]Step 3: Scraping companies...[/bold]")
        companies, method = self._smart_scrape(exhibitor_url, fair_url)

        # Step 4: Enrich from detail pages (get actual website, email, phone)
        if companies and enrich_details:
            console.print(f"\n  [bold]Step 4: Fetching company details...[/bold]")
            self._enrich_from_detail_pages(companies, fair_url)
        elif companies:
            console.print(f"\n  [dim]  Step 4 atlandı (--no-detail)[/dim]")

        result["companies"] = companies
        result["method"] = method

        console.print(f"\n  [bold green]✓ Found {len(companies)} companies via {method}[/bold green]")
        return result

    # ────────────────────────────────────────────────────────────
    # Step 1: Find the fair website
    # ────────────────────────────────────────────────────────────

    def _find_fair_website(self, fair_name: str) -> Optional[str]:
        """Find the official website of a fair by searching."""

        # Known fairs database
        known_fairs = {
            # Türkiye
            "idef": "https://idef.com.tr",
            "saha expo": "https://sahaexpo.com",
            "saha": "https://sahaexpo.com",
            "sahaexpo": "https://sahaexpo.com",
            "win eurasia": "https://www.win-eurasia.com",
            "win": "https://www.win-eurasia.com",
            "eurasia": "https://www.win-eurasia.com",
            "maktek": "https://www.maktekfuari.com",
            "modef": "https://www.modefmobilyafuari.com",
            "automechanika": "https://automechanika.messefrankfurt.com",
            "ifm": "https://www.ifm.com.tr",
            "musiad expo": "https://www.musiadexpo.com",
            "annofer": "https://www.annofer.com",
            "ankiros": "https://www.ankiros.com",
            "turkcast": "https://www.turkcast.com",
            "intermob": "https://www.intermob.com.tr",
            "beautyeurasia": "https://www.beautyeurasia.com",
            "beauty eurasia": "https://www.beautyeurasia.com",
            "icci": "https://www.icci.com.tr",
            "itm": "https://www.itm2026.com",
            
            # Fransa
            "maison & objet": "https://www.maison-objet.com",
            "maison objet": "https://www.maison-objet.com",
            "maison et objet": "https://www.maison-objet.com",
            "première vision": "https://www.premierevision.com",
            "premiere vision": "https://www.premierevision.com",
            "eurosatory": "https://www.eurosatory.com",
            "le bourget": "https://www.siae.fr",
            
            # İtalya
            "marmo+mac": "https://www.marmomac.com",
            "marmomac": "https://www.marmomac.com",
            "micam": "https://www.themicam.com",
            "micam milano": "https://www.themicam.com",
            "cersaie": "https://www.cersaie.it",
            "plast": "https://www.plastonline.org",
            
            # Endonezya
            "electric & power indonesia": "https://www.electricindonesia.com",
            "mining indonesia": "https://www.miningindonesia.com",
            "fhi food": "https://www.fhiindonesia.com",
            "fhi food & hotel indonesia": "https://www.fhiindonesia.com",
            "manufacturing indonesia": "https://www.manufacturingindonesia.com",
            "indobuildtech": "https://www.indobuildtech.com",
            "indolivestock": "https://www.indolivestock.com",
            
            # Polonya
            "energetab": "https://www.energetab.com",
            "mspo": "https://www.targikielce.pl/en/mspo",
            "sacroexpo": "https://www.targikielce.pl/en/sacroexpo",
            "necroexpo": "https://www.targikielce.pl/en/necroexpo",
            
            # Güney Kore
            "korea build": "https://www.koreabuildweek.com",
            "seoul food": "https://www.seoulfoodnhotel.com",
            "seoul food & hotel": "https://www.seoulfoodnhotel.com",
            "intercharm korea": "https://www.intercharm-korea.com",
            "smart tech korea": "https://www.smarttechkorea.com",
            
            # Singapur
            "medical fair asia": "https://www.medicalfair-asia.com",
            "siww": "https://www.siww.com.sg",
            "siww singapore international water week": "https://www.siww.com.sg",
            "sije": "https://www.sije.com.sg",
            
            # Japonya
            "japan's food export fair": "https://www.jfex.jp",
            "jfex": "https://www.jfex.jp",
            "interior lifestyle tokyo": "https://www.interior-lifestyle.com",
            "interop tokyo": "https://www.interop.jp",
            "techno-frontier": "https://www.jma.or.jp/tf",
            
            # ABD
            "neocon": "https://www.neocon.com",
            
            # Brezilya
            "tecnocarne": "https://www.tecnocarne.com.br",
            "fispal tecnologia": "https://www.fispaltecnologia.com.br",
            
            # Hindistan
            "automation expo": "https://www.automationexpo.com",
            "intec": "https://www.intec.codissia.com",
            "agri intex": "https://www.agriintex.codissia.com",
            "famdent": "https://www.famdent.com",
            
            # Mısır
            "big 5 construct egypt": "https://www.thebig5constructegypt.com",
            "paper middle east": "https://www.papermiddleeast.com",
            
            # İngiltere
            "farnborough": "https://www.farnboroughairshow.com",
            "dsei": "https://www.dsei.co.uk",
            "the london textile fair": "https://www.thelondontextilefair.co.uk",
            "london textile fair": "https://www.thelondontextilefair.co.uk",
            "rolling stock networking": "https://www.rollingstocknetworking.com",
            "solar & storage live": "https://www.terrapinn.com/exhibition/solar-storage-live",
            "solar & storage live uk": "https://www.terrapinn.com/exhibition/solar-storage-live",
            "techspo london": "https://techspoconference.com/london",
            "nfe national funeral": "https://www.nationalfuneralexhibition.co.uk",
            "nfe": "https://www.nationalfuneralexhibition.co.uk",
            "london packaging week": "https://www.londonpackagingweek.com",
            "the flooring show": "https://www.theflooringshow.com",
            
            # İspanya
            "bisutex": "https://www.ifema.es/en/bisutex",
            "madridjoya": "https://www.ifema.es/en/madridjoya",
            
            # Fransa (ek)
            "salon vivre côté sud": "https://www.vivrecotesud.com",
            "salon vivre cote sud": "https://www.vivrecotesud.com",
            "le printemps des etudes": "https://www.printemps-etudes.com",
            "cheese and dairy": "https://www.salondufrommage.com",
            "bijorhca": "https://www.bijorhca.net",
            
            # İtalya (ek)
            "xylexpo": "https://www.xylexpo.com",
            "xylexpo milano": "https://www.xylexpo.com",
            
            # Brezilya (ek)
            "biofach america latina": "https://www.biofach-americalatina.com.br",
            "pet south america": "https://www.petsa.com.br",
            "transpoquip": "https://www.transpoquip.com.br",
            "transpoquip latin america": "https://www.transpoquip.com.br",
            
            # Endonezya (ek)
            "indo water": "https://www.indowaterexpo.com",
            "indo water expo": "https://www.indowaterexpo.com",
            "refrigeration & hvac indonesia": "https://www.rhvacindonesia.com",
            "construction indonesia": "https://www.constructionindonesia.com",
            "oil & gas indonesia": "https://www.oilgasindonesia.com",
            "growtech jakarta": "https://www.growtechjakarta.com",
            "enlit asia": "https://www.enlit-asia.com",
            
            # Singapur (ek)
            "os+h asia": "https://www.osha-singapore.com",
            "medical manufacturing asia": "https://www.medmanufacturing-asia.com",
            
            # Güney Kore (ek)
            "cphi korea": "https://www.cphi.com/korea",
            "khf": "https://www.khf.com",
            "korea build week": "https://www.koreabuildweek.com",
            
            # Hindistan (ek)
            "packplus": "https://www.packplus.in",
            "natural expo india": "https://www.naturalproductsexpo.in",
            "biofach india": "https://www.biofach-india.com",
            
            # Polonya (ek)
            "glass-tech poland": "https://www.glasstechpoland.com",
            "warsaw sweet tech": "https://www.warsawsweettech.com",
            "warsaw floor expo": "https://www.warsawfloorexpo.com",
            "warsaw dental medica": "https://www.warsawdentalmedica.com",
            "warsaw print-tech expo": "https://www.warsawprinttech.com",
            "metal": "https://www.targikielce.pl/en/metal",
            "polfish": "https://www.polfish.pl",
            "heating tech": "https://www.heatingtech.pl",
            "trends expo": "https://www.trendsexpo.pl",
            "wodkan tech": "https://www.wodkantech.com",
            "recycling tech": "https://www.recyclingtech.org",
            
            # Türkiye (ek)
            "busworld turkey": "https://www.busworldturkey.org",
            "elevate": "https://www.elevate.com.tr",
            "zuchex": "https://www.zuchex.com",
            "aymod": "https://www.aymod.com",
            
            # Savunma/Havacılık
            "idex": "https://www.idexuae.ae",
            "aero india": "https://aeroindia.gov.in",
        }

        # Check known fairs
        fair_lower = fair_name.lower().strip()
        for key, url in known_fairs.items():
            if key in fair_lower or fair_lower in key:
                return url

        # Try to construct URL from name — with many TLD patterns
        slug = fair_lower.replace(" ", "").replace("-", "").replace("&", "and")
        slug_dash = fair_lower.replace(" ", "-").replace("&", "and")
        possible_urls = [
            f"https://www.{slug}.com",
            f"https://{slug}.com",
            f"https://www.{slug}.com.tr",
            f"https://www.{slug}.co.uk",
            f"https://www.{slug}.org",
            f"https://www.{slug}.eu",
            f"https://www.{slug}.pl",
            f"https://www.{slug}.de",
            f"https://www.{slug}.it",
            f"https://www.{slug}.fr",
            f"https://www.{slug}.com.br",
            f"https://www.{slug}.in",
            f"https://www.{slug_dash}.com",
            f"https://www.{slug_dash}.co.uk",
            f"https://www.{slug_dash}.org",
        ]

        for url in possible_urls:
            try:
                r = self.session.head(url, timeout=10, allow_redirects=True)
                if r.status_code == 200:
                    return url
            except requests.RequestException:
                continue

        # If nothing found directly, try Google search approach
        # by looking at common fair site patterns
        search_slugs = [
            fair_lower.replace(" ", ""),
            fair_lower.replace(" ", "-"),
            fair_lower.replace(" ", "_"),
        ]

        for slug in search_slugs:
            for tld in [".com", ".com.tr", ".org", ".net"]:
                url = f"https://www.{slug}{tld}"
                try:
                    r = self.session.head(url, timeout=8, allow_redirects=True)
                    if r.status_code == 200:
                        return url
                except requests.RequestException:
                    continue

        return None

    # ────────────────────────────────────────────────────────────
    # Step 2: Find the exhibitor list page
    # ────────────────────────────────────────────────────────────

    def _find_exhibitor_page(self, fair_url: str) -> Optional[str]:
        """Try common exhibitor page URL patterns."""
        for path in EXHIBITOR_PATHS:
            url = f"{fair_url.rstrip('/')}{path}"
            try:
                r = self.session.get(url, timeout=15, allow_redirects=True)
                if r.status_code == 200 and len(r.text) > 1000:
                    # Verify this is actually an exhibitor page
                    soup = BeautifulSoup(r.text, "lxml")
                    text = soup.get_text().lower()
                    if any(kw in text for kw in [
                        "exhibitor", "katılımcı", "katilimci", "participant",
                        "company", "firma", "stand", "stant", "salon", "hall"
                    ]):
                        return url
                time.sleep(0.5)
            except requests.RequestException:
                continue
        return None

    def _discover_from_homepage(self, fair_url: str) -> Optional[str]:
        """Crawl homepage to find exhibitor-related links."""
        try:
            r = self.session.get(fair_url, timeout=15)
            soup = BeautifulSoup(r.text, "lxml")
        except requests.RequestException:
            return None

        keywords = [
            "exhibitor", "katılımcı", "katilimci", "participant",
            "firma listesi", "company list", "exhibitor list",
            "katılımcı listesi", "sergileyen",
        ]

        best_link = None
        best_score = 0

        for link in soup.find_all("a", href=True):
            href = link["href"]
            text = (link.get_text(strip=True) + " " + href).lower()

            score = sum(1 for kw in keywords if kw in text)
            if score > best_score:
                best_score = score
                best_link = urljoin(fair_url, href)

        return best_link if best_score > 0 else None

    # ────────────────────────────────────────────────────────────
    # Step 4: Enrich from detail pages
    # ────────────────────────────────────────────────────────────

    def _enrich_from_detail_pages(self, companies: list, fair_url: str):
        """Visit each company's detail page to extract real website, email, phone, address.
        Uses ThreadPoolExecutor for parallel requests (~10x faster).
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        fair_domain = urlparse(fair_url).netloc.replace("www.", "")
        total = len(companies)

        # Filter companies that have a fair profile URL
        to_enrich = [(i, c) for i, c in enumerate(companies)
                     if c.website and fair_domain in c.website]

        if not to_enrich:
            console.print(f"  [yellow]  No detail pages to visit[/yellow]")
            return

        console.print(f"  [dim]  {len(to_enrich)} detail pages to visit (parallel)...[/dim]")

        def _fetch_detail(idx_company):
            idx, company = idx_company
            profile_url = company.website
            try:
                s = requests.Session()
                s.headers.update(self.session.headers)
                r = s.get(profile_url, timeout=config.REQUEST_TIMEOUT)
                if r.status_code != 200:
                    return idx, None
                return idx, r.text
            except Exception:
                return idx, None

        # Fetch all pages in parallel (10 workers)
        results = {}
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(_fetch_detail, item): item for item in to_enrich}
            done_count = 0
            for future in as_completed(futures):
                done_count += 1
                idx, html = future.result()
                if html:
                    results[idx] = html
                if done_count % 50 == 0 or done_count == len(to_enrich):
                    console.print(f"  [dim]  {done_count}/{len(to_enrich)} pages fetched...[/dim]")

        # Parse results
        enriched = 0
        for idx, html in results.items():
            company = companies[idx]
            soup = BeautifulSoup(html, "lxml")
            page_text = soup.get_text()

            real_website = None
            email = None
            phone = None
            address = None
            sectors = []

            # --- Parse all links ---
            for link in soup.find_all("a", href=True):
                href = link.get("href", "").strip()
                text = link.get_text(strip=True)

                # Email: mailto links
                if href.startswith("mailto:"):
                    email = href.replace("mailto:", "").strip()
                    continue

                # Phone: tel links
                if href.startswith("tel:"):
                    phone = href.replace("tel:", "").strip()
                    continue

                # Cloudflare email protection
                if "email-protection" in href and "#" in href:
                    try:
                        encoded = href.split("#")[-1]
                        r_val = int(encoded[:2], 16)
                        decoded = ""
                        for j in range(2, len(encoded), 2):
                            decoded += chr(int(encoded[j:j+2], 16) ^ r_val)
                        if "@" in decoded:
                            email = decoded
                    except Exception:
                        pass
                    continue

                # Skip fair/internal/social links
                SKIP_DOMAINS = [
                    fair_domain, "sahaexpo.com", "idef.com",
                    "google.com", "facebook.com", "twitter.com", "x.com",
                    "linkedin.com", "instagram.com", "youtube.com",
                    "calendar.google", "outlook.live", "apple.com",
                    "whatsapp.com", "t.me", "tiktok.com", "pinterest.com",
                    "kayit.sahaexpo.com", "portal.sahaexpo.com",
                    "sahaistanbul.org.tr", "sahaistanbul.org",
                    "kp.idef.com.tr", "dot.idef.com.tr",
                    "nsosyal.com", "addthis.com", "sharethis.com",
                    "bit.ly", "goo.gl", "mailto:", "javascript:",
                    "play.google.com", "apps.apple.com",
                ]
                if any(d in href for d in SKIP_DOMAINS):
                    continue

                # External website link
                if href.startswith("http"):
                    if not real_website:
                        real_website = href

                # Plain domain text like "aaes.com.tr" — always prefer this over href
                if "." in text and len(text) < 60 and " " not in text and "@" not in text:
                    if any(tld in text.lower() for tld in [".com", ".tr", ".net", ".org", ".io", ".de", ".uk", ".fr", ".us", ".ch", ".sk", ".tech", ".ae", ".sa", ".bd"]):
                        real_website = f"https://{text}" if not text.startswith("http") else text

            # --- Parse email from text (if not found in links) ---
            if not email:
                email_match = re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', page_text)
                if email_match:
                    candidate = email_match.group(0)
                    if fair_domain not in candidate:
                        email = candidate

            # --- Parse address text ---
            for text_node in soup.stripped_strings:
                txt = text_node.strip()
                if any(kw in txt for kw in ["OSB", "Cadde", "Sokak", "Mah.", "No:", "Blv.",
                                             "Street", "Ave", "Road", "Suite"]):
                    if len(txt) > 10 and len(txt) < 300:
                        address = txt
                        break

            # --- Parse sectors/business areas ---
            for heading in soup.find_all(["h2", "h3", "h4", "h5", "h6", "div"]):
                heading_text = heading.get_text(strip=True).upper()
                if any(kw in heading_text for kw in ["BUSINESS AREA", "FAALİYET ALAN", "SEKTÖR"]):
                    parent = heading.parent
                    if parent:
                        for item in parent.find_all(["li", "span", "a", "div"]):
                            t = item.get_text(strip=True)
                            if t and len(t) > 3 and len(t) < 100 and t != heading_text:
                                sectors.append(t)

            # --- Update company data ---
            if real_website:
                company.website = real_website
                enriched += 1
            if email:
                company.email = email
            if phone:
                company.phone = phone
            if address:
                company.address = address
            if sectors and not company.sector:
                company.sector = ", ".join(sectors[:3])

        console.print(f"  [green]  ✓ {enriched}/{total} firmanın gerçek web sitesi bulundu[/green]")

    # ────────────────────────────────────────────────────────────
    # Step 3: Smart scraping
    # ────────────────────────────────────────────────────────────

    def _smart_scrape(self, exhibitor_url: str, fair_url: str) -> tuple:
        """
        Intelligently scrape the exhibitor page.
        Tries multiple strategies and picks the best one.
        Returns (companies, method_name)
        """
        all_companies = []
        seen_names = set()
        initial_count = 0

        # Strategy A: Single page parse
        console.print(f"  [dim]Strategy A: Direct page parse...[/dim]")
        page_companies = self._parse_exhibitor_page(exhibitor_url, fair_url)

        if page_companies:
            for c in page_companies:
                if c.name not in seen_names:
                    seen_names.add(c.name)
                    all_companies.append(c)
            initial_count = len(all_companies)
            console.print(f"  [green]  → Found {initial_count} companies on first page[/green]")

        # Strategy B: Letter filter FIRST (most fairs cap results per page)
        # Always try this — most Turkish fairs support ?letter=X
        console.print(f"  [dim]Strategy B: Letter-based filtering (A-Z)...[/dim]")
        letter_companies = self._scrape_with_letter_filter(exhibitor_url, fair_url, seen_names)
        if letter_companies:
            # If letter filter found significantly more, use ONLY letter results
            # (initial page may have different language/format causing duplicates)
            if len(letter_companies) > initial_count * 2:
                all_companies = letter_companies
                seen_names = set(c.name for c in all_companies)
                console.print(f"  [green]  → {len(all_companies)} companies via letters (replaced initial)[/green]")
            else:
                all_companies.extend(letter_companies)
                for c in letter_companies:
                    seen_names.add(c.name)
                console.print(f"  [green]  → +{len(letter_companies)} new via letters (total: {len(all_companies)})[/green]")

        # Strategy C: Pagination (if letter filter didn't help much)
        if len(all_companies) <= initial_count + 5:
            console.print(f"  [dim]Strategy C: Paginated scraping...[/dim]")
            paginated = self._scrape_with_pagination(exhibitor_url, fair_url, seen_names)
            if paginated:
                all_companies.extend(paginated)
                for c in paginated:
                    seen_names.add(c.name)
                console.print(f"  [green]  → +{len(paginated)} via pagination (total: {len(all_companies)})[/green]")

        method = "letter_filter" if len(all_companies) > initial_count else "direct"

        return all_companies, method

    def _scrape_with_pagination(self, base_url: str, fair_url: str,
                                 seen_names: set) -> list[CompanyData]:
        """Try paginated scraping."""
        new_companies = []

        for param in PAGINATION_PARAMS:
            found_any = False
            consecutive_empty = 0
            for page_num in range(2, 30):  # max 30 pages
                sep = "&" if "?" in base_url else "?"
                url = f"{base_url}{sep}{param}={page_num}"

                companies = self._parse_exhibitor_page(url, fair_url)
                if not companies:
                    consecutive_empty += 1
                    if consecutive_empty >= 2:
                        break  # Two empty pages in a row = stop
                    continue

                consecutive_empty = 0
                new_on_page = 0
                for c in companies:
                    if c.name not in seen_names:
                        seen_names.add(c.name)
                        new_companies.append(c)
                        new_on_page += 1
                        found_any = True

                if new_on_page == 0:
                    break

                console.print(f"  [dim]    Page {page_num}: +{new_on_page} new[/dim]")
                time.sleep(config.REQUEST_DELAY)

            if found_any:
                break  # Found the right pagination param

        return new_companies

    def _scrape_with_letter_filter(self, base_url: str, fair_url: str,
                                    seen_names: set) -> list[CompanyData]:
        """Try letter-based filtering. First detect which param works, then scan all letters."""
        new_companies = []

        # Build list of URLs to try (base + locale variants)
        urls_to_try = [base_url]
        parsed = urlparse(base_url)
        path = parsed.path

        # Add locale-prefixed variants: /en/exhibitors, /tr/katilimcilar etc.
        if not path.startswith("/en/") and not path.startswith("/tr/"):
            en_url = base_url.replace(path, f"/en{path}")
            tr_url = base_url.replace(path, f"/tr{path}")
            urls_to_try.extend([en_url, tr_url])
        elif path.startswith("/en/"):
            tr_url = base_url.replace("/en/", "/tr/")
            urls_to_try.append(tr_url)
        elif path.startswith("/tr/"):
            en_url = base_url.replace("/tr/", "/en/")
            urls_to_try.insert(0, en_url)  # Try English first

        # Step 1: Detect which URL + param combo works
        working_url = None
        working_param = None

        for try_url in urls_to_try:
            for param in LETTER_PARAMS:
                sep = "&" if "?" in try_url else "?"
                test_url = f"{try_url}{sep}{param}=A"
                console.print(f"  [dim]    Testing {test_url}[/dim]")

                companies = self._parse_exhibitor_page(test_url, fair_url)
                if companies:
                    new_count = sum(1 for c in companies if c.name not in seen_names)
                    if new_count > 0:
                        working_url = try_url
                        working_param = param
                        console.print(f"  [green]    ✓ Works! {new_count} new companies[/green]")
                        # Add these companies
                        for c in companies:
                            if c.name not in seen_names:
                                seen_names.add(c.name)
                                new_companies.append(c)

                        # Also paginate for letter A
                        self._paginate_letter(working_url, working_param, "A",
                                              fair_url, seen_names, new_companies)
                        break
                    else:
                        console.print(f"  [dim]    Same data, next...[/dim]")
                else:
                    pass  # Silently skip failed URLs

            if working_url:
                break

        if not working_url:
            console.print(f"  [dim]    No working letter filter found[/dim]")
            return new_companies

        # Step 2: Scan remaining letters with the working combo
        for letter in TR_ALPHABET[1:]:  # Skip 'A'
            sep = "&" if "?" in working_url else "?"
            url = f"{working_url}{sep}{working_param}={letter}"
            companies = self._parse_exhibitor_page(url, fair_url)

            if companies:
                new_count = 0
                for c in companies:
                    if c.name not in seen_names:
                        seen_names.add(c.name)
                        new_companies.append(c)
                        new_count += 1

                if new_count > 0:
                    console.print(f"  [dim]    '{letter}': +{new_count} (total: {len(new_companies)})[/dim]")

                # Paginate within this letter
                self._paginate_letter(working_url, working_param, letter,
                                      fair_url, seen_names, new_companies)

        # Also try digits 0-9
        for digit in "0123456789":
            sep = "&" if "?" in working_url else "?"
            url = f"{working_url}{sep}{working_param}={digit}"
            companies = self._parse_exhibitor_page(url, fair_url)
            if companies:
                for c in companies:
                    if c.name not in seen_names:
                        seen_names.add(c.name)
                        new_companies.append(c)

        return new_companies

    def _paginate_letter(self, base_url: str, letter_param: str,
                          letter: str, fair_url: str,
                          seen_names: set, new_companies: list):
        """Handle pagination within a single letter filter."""
        sep = "&" if "?" in base_url else "?"
        for page_num in range(2, 30):
            url = f"{base_url}{sep}{letter_param}={letter}&page={page_num}"
            companies = self._parse_exhibitor_page(url, fair_url)
            if not companies:
                break

            new_on_page = 0
            for c in companies:
                if c.name not in seen_names:
                    seen_names.add(c.name)
                    new_companies.append(c)
                    new_on_page += 1

            if new_on_page == 0:
                break

            console.print(f"  [dim]      '{letter}' p{page_num}: +{new_on_page}[/dim]")

    def _parse_exhibitor_page(self, url: str, fair_url: str) -> list[CompanyData]:
        """Parse a single exhibitor list page. Returns list of companies found."""
        try:
            r = self.session.get(url, timeout=config.REQUEST_TIMEOUT)
            if r.status_code != 200:
                return []
        except requests.RequestException:
            return []

        soup = BeautifulSoup(r.text, "lxml")

        # Remove navigation, footer, header
        for el in soup.find_all(["nav", "header", "footer", "script", "style", "noscript"]):
            el.decompose()

        companies = []

        # Try multiple parsing strategies in order of reliability
        strategies = [
            ("detail_links", lambda: self._parse_detail_links(soup, fair_url)),
            ("subdomain_links", lambda: self._parse_subdomain_links(soup, fair_url)),
            ("table", lambda: self._parse_tables(soup, fair_url)),
            ("cards", lambda: self._parse_cards(soup, fair_url)),
            ("structured_list", lambda: self._parse_structured_list(soup, fair_url)),
            ("external_links", lambda: self._parse_external_links(soup, fair_url)),
        ]

        for name, strategy in strategies:
            result = strategy()
            if result and len(result) >= 3:
                companies = result
                break

        return companies

    def _parse_detail_links(self, soup, fair_url: str) -> list[CompanyData]:
        """Parse companies from detail page links (e.g., /katilimci/slug or /exhibitor/slug).
        This is the most reliable method for Turkish fair sites like SAHA EXPO."""
        companies = []
        seen = set()

        # Known countries for classification
        KNOWN_COUNTRIES = {
            "Türkiye", "Turkey", "Almanya", "Germany", "ABD", "United States",
            "Amerika Birleşik Devletleri", "Fransa", "France", "İngiltere",
            "United Kingdom", "İtalya", "Italy", "Japonya", "Japan", "Çin",
            "China", "Rusya", "Russia", "İsrail", "Israel", "Güney Kore",
            "South Korea", "Hindistan", "India", "Azerbaycan", "Azerbaijan",
            "Birleşik Arap Emirlikleri", "United Arab Emirates", "Katar", "Qatar",
            "İspanya", "Spain", "Hollanda", "Netherlands", "Belçika", "Belgium",
            "İsviçre", "Switzerland", "Norveç", "Norway", "İsveç", "Sweden",
            "Finlandiya", "Finland", "Polonya", "Poland", "Çekya", "Czech Republic",
            "Romanya", "Romania", "Ukrayna", "Ukraine", "Gürcistan", "Georgia",
            "Suudi Arabistan", "Saudi Arabia", "Ürdün", "Jordan", "Malezya",
            "Malaysia", "Singapur", "Singapore", "Endonezya", "Indonesia",
            "Slovakya", "Slovakia", "Macaristan", "Hungary", "Pakistan",
            "Kanada", "Canada", "Avustralya", "Australia", "Brezilya", "Brazil",
            "Portekiz", "Portugal", "Danimarka", "Denmark", "Avusturya", "Austria",
            "Yunanistan", "Greece", "Bulgaristan", "Bulgaria", "Tayland", "Thailand",
            "Çin Tayvanı", "Chinese Taipei", "Taiwan", "Güney Afrika", "South Africa",
            "Mısır", "Egypt", "Fas", "Morocco", "Tunus", "Tunisia", "Irak", "Iraq",
            "İran", "Iran", "Lübnan", "Lebanon", "Litvanya", "Lithuania",
            "Letonya", "Latvia", "Estonya", "Estonia", "Hırvatistan", "Croatia",
            "Sırbistan", "Serbia", "Bosna Hersek", "Bosnia and Herzegovina",
            "Arnavutluk", "Albania", "Kosova", "Kosovo", "Karadağ", "Montenegro",
        }

        # Skip words - not company names
        SKIP_WORDS = {
            "Tüm Firmalar", "All Companies", "Next", "Previous", "Next »", "« Previous",
            "Sonraki", "Önceki", "Platinum Area", "Silver Area", "Platin Alan",
            "Gümüş Alan", "Altın Alan", "Gold Area", "Bronze Area", "Bronz Alan",
            "Clear All", "Temizle",
        }

        # Find links to exhibitor detail pages
        detail_patterns = [
            re.compile(r'/katilimci/[\w-]+$'),
            re.compile(r'/exhibitor/[\w-]+$'),
            re.compile(r'/participant/[\w-]+$'),
            re.compile(r'/firma/[\w-]+$'),
        ]

        for pattern in detail_patterns:
            links = soup.find_all("a", href=pattern)
            if len(links) < 3:
                continue

            for link in links:
                href = link.get("href", "")
                full_url = urljoin(fair_url, href)

                name = None
                country = None
                sector = None
                booth = None

                # Strategy 1: h3 heading right after this link (SAHA EXPO pattern)
                next_sib = link.find_next_sibling(["h2", "h3", "h4", "h5"])
                if next_sib:
                    candidate = next_sib.get_text(strip=True)
                    if candidate and len(candidate) > 2 and candidate not in SKIP_WORDS:
                        name = candidate

                # Strategy 2: Parse structured text from within the link
                if not name or len(name) < 2:
                    texts = [t.strip() for t in link.stripped_strings
                             if len(t.strip()) > 1 and len(t.strip()) < 200]
                    if texts:
                        name = texts[0]

                if not name or len(name) < 2 or name in seen or name in SKIP_WORDS:
                    continue

                # Extract country, sector, booth from link text
                texts = [t.strip() for t in link.stripped_strings
                         if len(t.strip()) > 1 and len(t.strip()) < 200 and t.strip() != name]

                for t in texts:
                    if "Hall" in t or "Salon" in t or "Stand" in t or "|" in t:
                        booth = t.replace("|", "-").strip()
                    elif t in KNOWN_COUNTRIES:
                        country = t
                    elif not sector and len(t) > 3 and t not in SKIP_WORDS:
                        sector = t

                seen.add(name)
                companies.append(CompanyData(
                    name=name,
                    website=full_url,
                    country=country,
                    booth_number=booth,
                    sector=sector,
                ))

            if companies:
                break  # Found working pattern

        return companies

    def _parse_subdomain_links(self, soup, fair_url: str) -> list[CompanyData]:
        """Parse companies from subdomain links (e.g., company.idef.com.tr)."""
        domain = urlparse(fair_url).netloc.replace("www.", "")
        companies = []
        seen = set()

        pattern = re.compile(rf'https?://[\w-]+\.{re.escape(domain)}')
        links = soup.find_all("a", href=pattern)

        for link in links:
            href = link.get("href", "")
            subdomain = urlparse(href).netloc

            # Skip main domain and known utility subdomains
            skip_subdomains = {f"www.{domain}", domain, f"kp.{domain}",
                               f"dot.{domain}", f"cdn.{domain}", f"api.{domain}"}
            if subdomain in skip_subdomains:
                continue

            # Find parent card
            card = self._find_card_parent(link)
            name, country = self._extract_name_country_from_card(card)

            if name and name not in seen and len(name) > 2:
                seen.add(name)
                logo = self._extract_logo(card, fair_url)
                companies.append(CompanyData(
                    name=name, website=href, country=country, logo_url=logo
                ))

        return companies

    def _parse_tables(self, soup, fair_url: str) -> list[CompanyData]:
        """Parse from HTML tables."""
        companies = []
        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            if len(rows) < 3:
                continue
            for row in rows[1:]:
                cells = row.find_all(["td", "th"])
                if cells:
                    name = cells[0].get_text(strip=True)
                    if name and 2 < len(name) < 200:
                        company = CompanyData(name=name)
                        link = cells[0].find("a", href=True)
                        if link:
                            href = link["href"]
                            if "http" in href and fair_url not in href:
                                company.website = href
                        if len(cells) > 1:
                            text = cells[1].get_text(strip=True)
                            company.country = text if len(text) < 50 else None
                        if len(cells) > 2:
                            company.booth_number = cells[2].get_text(strip=True)
                        companies.append(company)
        return companies

    def _parse_cards(self, soup, fair_url: str) -> list[CompanyData]:
        """Parse from card/div layouts."""
        companies = []
        seen = set()

        card_patterns = [
            re.compile(r"exhibitor|participant|company|firma|katilimci", re.I),
            re.compile(r"card|grid-item|list-item|item", re.I),
        ]

        for pattern in card_patterns:
            cards = soup.find_all(["div", "li", "article"], class_=pattern)
            if len(cards) >= 3:
                for card in cards:
                    name_el = card.find(["h2", "h3", "h4", "h5", "a", "strong", "b"])
                    if name_el:
                        name = name_el.get_text(strip=True)
                        if name and 2 < len(name) < 200 and name not in seen:
                            seen.add(name)
                            company = CompanyData(name=name)

                            # Website
                            for link in card.find_all("a", href=True):
                                href = link["href"]
                                if "http" in href and fair_url not in href:
                                    company.website = href
                                    break

                            # Logo
                            company.logo_url = self._extract_logo(card, fair_url)

                            # Country
                            for span in card.find_all(["span", "small", "p"]):
                                text = span.get_text(strip=True)
                                if text and text != name and len(text) < 60:
                                    if not company.country:
                                        company.country = text

                            companies.append(company)
                if companies:
                    break

        return companies

    def _parse_structured_list(self, soup, fair_url: str) -> list[CompanyData]:
        """Parse from ul/ol lists."""
        companies = []
        for lst in soup.find_all(["ul", "ol"]):
            items = lst.find_all("li")
            if len(items) >= 5:
                for item in items:
                    text_el = item.find(["a", "strong", "b", "span"])
                    if text_el:
                        name = text_el.get_text(strip=True)
                    else:
                        name = item.get_text(strip=True)

                    if name and 2 < len(name) < 200:
                        company = CompanyData(name=name)
                        link = item.find("a", href=True)
                        if link and "http" in link["href"]:
                            company.website = link["href"]
                        companies.append(company)

                if len(companies) >= 5:
                    break

        return companies

    def _parse_external_links(self, soup, fair_url: str) -> list[CompanyData]:
        """Last resort: external links as company websites."""
        companies = []
        seen = set()
        domain = urlparse(fair_url).netloc

        for link in soup.find_all("a", href=True):
            href = link["href"]
            text = link.get_text(strip=True)

            if (text and 3 < len(text) < 100 and text not in seen and
                "http" in href and domain not in href and
                not any(x in href.lower() for x in
                        ["facebook", "twitter", "instagram", "youtube",
                         "linkedin", "google", "mailto:", "tel:", "javascript:"])):
                seen.add(text)
                companies.append(CompanyData(name=text, website=href))

        return companies

    # ────────────────────────────────────────────────────────────
    # Helper methods
    # ────────────────────────────────────────────────────────────

    def _find_card_parent(self, element) -> object:
        """Navigate up the DOM to find the card container."""
        card = element
        for _ in range(8):
            parent = card.parent
            if parent and parent.name in ["div", "article", "li", "section"]:
                text = parent.get_text(strip=True)
                if len(text) > 5:
                    card = parent
                    # Stop if we found a large enough container
                    children = parent.find_all(["div", "a"], recursive=False)
                    if len(children) >= 2:
                        break
            else:
                break
        return card

    def _extract_name_country_from_card(self, card) -> tuple:
        """Extract company name and country from a card element."""
        COUNTRIES = {
            "Türkiye", "Almanya", "ABD", "Fransa", "İngiltere", "İtalya",
            "Güney Kore", "Japonya", "Çin", "Rusya", "İsrail", "Pakistan",
            "Azerbaycan", "Birleşik Arap Emirlikleri", "Katar", "Hindistan",
            "Turkey", "Germany", "USA", "France", "United Kingdom", "Italy",
            "Japan", "China", "Russia", "Israel", "South Korea", "India",
            "United Arab Emirates", "Qatar", "Brazil", "Australia", "Canada",
            "İspanya", "Hollanda", "Belçika", "İsviçre", "Norveç", "İsveç",
            "Finlandiya", "Polonya", "Çekya", "Romanya", "Ukrayna", "Gürcistan",
            "Suudi Arabistan", "Ürdün", "Malezya", "Singapur", "Endonezya",
        }

        name = None
        country = None

        texts = []
        for el in card.find_all(["h2", "h3", "h4", "h5", "p", "span", "strong"]):
            t = el.get_text(strip=True)
            if t and 2 < len(t) < 200:
                texts.append(t)

        if not texts:
            texts = [t.strip() for t in card.stripped_strings if 2 < len(t.strip()) < 200]

        for text in texts:
            if text in COUNTRIES:
                country = text
            elif not name:
                name = text

        return name, country

    def _extract_logo(self, card, fair_url: str) -> Optional[str]:
        """Extract logo URL from a card."""
        img = card.find("img")
        if img:
            src = img.get("src") or img.get("data-src")
            if src:
                return urljoin(fair_url, src)
        return None
