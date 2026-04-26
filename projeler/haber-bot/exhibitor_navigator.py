"""
Exhibitor Navigator v1.0
━━━━━━━━━━━━━━━━━━━━━━━
Structure-aware crawler for exhibitor list pages.

Instead of blindly probing URL patterns, this module:
1. Analyzes the exhibitor page structure
2. Detects navigation elements (pagination, A-Z tabs, filters, load-more)
3. Chooses the optimal navigation strategy
4. Visits all relevant sub-pages
5. Deduplicates extracted companies

Usage:
    from exhibitor_navigator import ExhibitorNavigator
    nav = ExhibitorNavigator()
    result = nav.navigate("https://fair.com/exhibitors")
"""

import re
import time
import string
import requests
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse
from bs4 import BeautifulSoup, Tag
from typing import Optional
from dataclasses import dataclass, field

# ═══════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,tr;q=0.8",
}

# Skip: navigation, footer noise, etc.
SKIP_NAMES = {
    # Navigation
    "next", "previous", "sonraki", "önceki", "clear all", "temizle",
    "search", "ara", "filter", "filtre", "show all", "tümünü göster",
    "load more", "daha fazla", "back", "geri", "home", "ana sayfa",
    "contact", "iletişim", "about", "hakkında", "login", "register",
    "exhibitor", "exhibitors", "katılımcı", "katılımcılar",
    "participant", "participants", "all", "tümü", "menu",
    "privacy", "cookie", "terms", "close", "kapat", "submit",
    # Common site elements
    "expand", "collapse", "read more", "devamını oku", "details",
    "share", "paylaş", "download", "indir", "print", "yazdır",
    "subscribe", "abone ol", "sign up", "kayıt ol", "log in",
    "news", "haberler", "blog", "faq", "help", "yardım",
    "sitemap", "accessibility", "disclaimer", "legal",
    # Fair-specific noise
    "neden", "why", "visitor", "ziyaretçi", "professional",
    "profesyonel", "brand", "marka", "country", "ülke",
    "product", "ürün", "category", "kategori", "hall", "salon",
    "program", "schedule", "takvim", "conference", "konferans",
    "sponsor", "media", "medya", "press", "basın", "gallery",
    "sık sorulan sorular", "floor plan", "kat planı",
    "registration", "kayıt", "book", "reserve", "ticket", "bilet",
    "venue", "mekan", "location", "konum", "map", "harita",
    "social", "follow", "takip", "newsletter", "bülten",
    "apply", "başvuru", "exhibit", "stand",
    # Common footer elements  
    "informa plc", "all rights reserved", "tüm hakları saklıdır",
    "copyright", "powered by",
}

# Min company name length
MIN_NAME_LEN = 3
MAX_NAME_LEN = 100
MAX_WORD_COUNT = 12  # Company names rarely exceed 12 words
MIN_COMPANIES_FOR_STRATEGY = 3

TR_ALPHABET = list(string.ascii_uppercase) + ["Ç", "Ğ", "İ", "Ö", "Ş", "Ü"]


# ═══════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════

@dataclass
class PageStructure:
    """Analysis result of an exhibitor page."""
    list_type: str = "unknown"  # single_page, pagination, alphabetical, filtered, js_app, detail_directory
    has_pagination: bool = False
    has_alphabetical: bool = False
    has_filters: bool = False
    has_load_more: bool = False
    has_detail_links: bool = False
    is_js_rendered: bool = False

    pagination_info: dict = field(default_factory=dict)  # param, max_page, next_url
    alpha_info: dict = field(default_factory=dict)         # param, letters_found
    filter_info: dict = field(default_factory=dict)        # filter_params
    detail_link_pattern: str = ""

    initial_company_count: int = 0


@dataclass
class NavResult:
    """Result of a full navigation."""
    fair_url: str = ""
    exhibitor_url: str = ""
    list_type: str = "unknown"
    navigation_detected: dict = field(default_factory=dict)
    visited_urls: int = 0
    companies_found: int = 0
    deduplicated_companies: int = 0
    companies: list = field(default_factory=list)
    method: str = "navigator"


# ═══════════════════════════════════════════════════════════════════
# MAIN NAVIGATOR CLASS
# ═══════════════════════════════════════════════════════════════════

class ExhibitorNavigator:
    """
    Structure-aware exhibitor page navigator.
    Analyzes the page, detects navigation patterns, and extracts all companies.
    """

    def __init__(self, timeout: int = 12, delay: float = 0.5, max_pages: int = 50):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.timeout = timeout
        self.delay = delay
        self.max_pages = max_pages

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PUBLIC API
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def navigate(self, exhibitor_url: str, fair_url: str = "") -> NavResult:
        """
        Main entry point.
        1. Fetch page
        2. Analyze structure
        3. Execute navigation strategy
        4. Deduplicate
        5. Return result
        """
        result = NavResult(fair_url=fair_url, exhibitor_url=exhibitor_url)

        # Step 1: Fetch page
        html, status_code = self._fetch(exhibitor_url)
        if not html:
            print(f"    ❌ Navigator: sayfaya ulaşılamadı ({status_code})")
            return result

        soup = BeautifulSoup(html, "html.parser")
        self._clean_soup(soup)

        # Step 2: Analyze structure
        print(f"    📐 Navigator: yapı analizi...")
        structure = self._analyze_structure(soup, exhibitor_url)
        result.list_type = structure.list_type
        result.navigation_detected = {
            "pagination": structure.has_pagination,
            "alphabetical": structure.has_alphabetical,
            "filters": structure.has_filters,
            "load_more": structure.has_load_more,
            "detail_links": structure.has_detail_links,
            "js_rendered": structure.is_js_rendered,
        }
        print(f"    📊 Yapı: {structure.list_type} | "
              f"{'📄' if structure.has_pagination else ''}{'🔤' if structure.has_alphabetical else ''}"
              f"{'🔍' if structure.has_filters else ''}{'⚡' if structure.has_load_more else ''}"
              f"{'📋' if structure.has_detail_links else ''}{'🔄' if structure.is_js_rendered else ''}"
              f" | İlk sayfa: {structure.initial_company_count} firma")

        # Step 3: Execute navigation strategy
        all_companies, visited = self._execute_strategy(soup, structure, exhibitor_url, fair_url)
        result.visited_urls = visited

        # Step 4: Deduplicate
        seen = set()
        unique = []
        for name in all_companies:
            normalized = self._normalize_name(name)
            if normalized and normalized not in seen:
                seen.add(normalized)
                unique.append(name)

        result.companies_found = len(all_companies)
        result.deduplicated_companies = len(unique)
        result.companies = unique
        result.method = f"navigator_{structure.list_type}"

        print(f"    ✅ Navigator: {result.deduplicated_companies} firma "
              f"({result.visited_urls} sayfa ziyaret)")

        return result

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # STEP 2: STRUCTURE ANALYSIS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _analyze_structure(self, soup: BeautifulSoup, url: str) -> PageStructure:
        """Analyze the exhibitor page to detect its navigation structure."""
        s = PageStructure()

        # Extract initial companies
        initial = self._extract_company_names(soup, url)
        s.initial_company_count = len(initial)

        # Detect pagination
        s.has_pagination, s.pagination_info = self._detect_pagination(soup, url)

        # Detect alphabetical tabs
        s.has_alphabetical, s.alpha_info = self._detect_alphabetical(soup, url)

        # Detect filter/facets
        s.has_filters, s.filter_info = self._detect_filters(soup)

        # Detect load more / infinite scroll
        s.has_load_more = self._detect_load_more(soup)

        # Detect detail page pattern
        s.has_detail_links, s.detail_link_pattern = self._detect_detail_links(soup, url)

        # Detect JS rendering
        s.is_js_rendered = self._detect_js_rendered(soup)

        # Classify list type
        s.list_type = self._classify_list_type(s)

        return s

    def _detect_pagination(self, soup: BeautifulSoup, url: str) -> tuple:
        """Detect pagination elements on the page."""
        info = {"param": None, "max_page": 1, "next_url": None, "links": []}

        # 1. Look for pagination containers
        pag_containers = soup.find_all(["nav", "div", "ul"],
            class_=re.compile(r'pag(ination|er|ing)|page-nav|wp-pagenavi', re.I))

        # 2. Look for page number links
        page_links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True)

            # Numeric page links
            if text.isdigit() and 1 < int(text) <= 100:
                page_links.append((int(text), urljoin(url, href)))

            # "Next" / "Sonraki" / "»" links
            if text.lower() in ("next", "sonraki", "»", "›", "next page", "next »"):
                info["next_url"] = urljoin(url, href)

            # URL param detection: ?page=2, ?p=2
            for param in ["page", "p", "sayfa", "pg", "offset"]:
                if f"{param}=" in href:
                    import re as _re
                    m = _re.search(rf'{param}=(\d+)', href)
                    if m:
                        pn = int(m.group(1))
                        if pn > 1:
                            info["param"] = param
                            info["max_page"] = max(info["max_page"], pn)
                            page_links.append((pn, urljoin(url, href)))

        # 3. Check for rel="next" in link tags
        for link in soup.find_all("link", rel="next"):
            if link.get("href"):
                info["next_url"] = urljoin(url, link["href"])

        if page_links:
            page_links.sort(key=lambda x: x[0])
            info["max_page"] = max(p[0] for p in page_links)
            info["links"] = [(p, u) for p, u in page_links[:50]]

        has = bool(page_links or info["next_url"] or pag_containers)
        return has, info

    def _detect_alphabetical(self, soup: BeautifulSoup, url: str) -> tuple:
        """Detect alphabetical filter tabs (A-Z navigation)."""
        info = {"param": None, "letters_found": [], "letter_urls": {}}

        # Pattern 1: Links that look like letter tabs
        letter_links = []
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True).upper()
            if len(text) == 1 and text in string.ascii_uppercase:
                href = a["href"]
                letter_links.append((text, urljoin(url, href)))

        # Pattern 2: Links with letter=X or alpha=X parameters
        for a in soup.find_all("a", href=True):
            href = a["href"]
            for param in ["letter", "alpha", "starts_with", "initial", "harf", "l", "a"]:
                m = re.search(rf'{param}=([A-Za-z])', href)
                if m:
                    letter = m.group(1).upper()
                    if letter in string.ascii_uppercase:
                        info["param"] = param
                        letter_links.append((letter, urljoin(url, href)))

        # Pattern 3: Alphabetical tab containers
        alpha_containers = soup.find_all(["div", "ul", "nav"],
            class_=re.compile(r'alpha|letter|az-filter|abc|glossary', re.I))
        for container in alpha_containers:
            for a in container.find_all("a", href=True):
                text = a.get_text(strip=True).upper()
                if len(text) == 1 and text in string.ascii_uppercase:
                    letter_links.append((text, urljoin(url, a["href"])))

        # Pattern 4: data-letter attributes
        for el in soup.find_all(attrs={"data-letter": True}):
            letter = el.get("data-letter", "").upper()
            if letter in string.ascii_uppercase:
                href = el.get("href") or ""
                letter_links.append((letter, urljoin(url, href) if href else ""))

        # Deduplicate and validate
        letters = {}
        for letter, href in letter_links:
            if letter not in letters:
                letters[letter] = href

        if len(letters) >= 5:  # At least 5 letters = real alphabetical nav
            info["letters_found"] = sorted(letters.keys())
            info["letter_urls"] = letters

            # Try to detect the URL parameter if not found yet
            if not info["param"] and letters:
                first_url = list(letters.values())[0]
                for param in ["letter", "alpha", "starts_with", "initial", "harf"]:
                    if f"{param}=" in first_url:
                        info["param"] = param
                        break

        has = len(letters) >= 5
        return has, info

    def _detect_filters(self, soup: BeautifulSoup) -> tuple:
        """Detect filter/facet elements (industry, country, product group, hall)."""
        info = {"filter_elements": [], "select_elements": []}

        # 1. Select/dropdown menus
        for select in soup.find_all("select"):
            name = (select.get("name") or select.get("id") or "").lower()
            filter_keywords = ["industry", "category", "country", "hall", "sector",
                             "product", "group", "type", "sektör", "ülke", "salon"]
            if any(kw in name for kw in filter_keywords):
                options = [opt.get_text(strip=True) for opt in select.find_all("option")]
                info["select_elements"].append({"name": name, "options": options[:20]})

        # 2. Filter containers with checkboxes or links
        filter_containers = soup.find_all(["div", "aside", "form"],
            class_=re.compile(r'filter|facet|sidebar|refine|search-form', re.I))
        for container in filter_containers:
            inputs = container.find_all("input", type=re.compile(r'checkbox|radio'))
            if inputs:
                info["filter_elements"].append({
                    "type": "checkbox_group",
                    "count": len(inputs),
                })

        has = bool(info["select_elements"] or info["filter_elements"])
        return has, info

    def _detect_load_more(self, soup: BeautifulSoup) -> bool:
        """Detect 'Load More' or infinite scroll patterns."""
        # Button patterns
        for btn in soup.find_all(["button", "a", "div"]):
            text = btn.get_text(strip=True).lower()
            if text in ("load more", "daha fazla", "show more", "daha fazla göster",
                        "load all", "tümünü yükle", "more results"):
                return True
            cls = " ".join(btn.get("class", []))
            if "load-more" in cls or "loadmore" in cls:
                return True

        # Infinite scroll JS indicators
        page_text = str(soup)
        if any(pattern in page_text for pattern in [
            "infinite-scroll", "infinitescroll", "InfiniteScroll",
            "data-infinite", "scroll-loader", "lazy-load-list",
        ]):
            return True

        return False

    def _detect_detail_links(self, soup: BeautifulSoup, url: str) -> tuple:
        """Detect if companies link to individual detail pages."""
        patterns = [
            re.compile(r'/exhibitor(s)?/[a-z0-9][\w-]+/?$', re.I),
            re.compile(r'/katilimci/[\w-]+/?$', re.I),
            re.compile(r'/participant/[\w-]+/?$', re.I),
            re.compile(r'/company/[\w-]+/?$', re.I),
            re.compile(r'/firma/[\w-]+/?$', re.I),
            re.compile(r'/aussteller/[\w-]+/?$', re.I),
        ]

        for pattern in patterns:
            matches = soup.find_all("a", href=pattern)
            if len(matches) >= 3:
                return True, pattern.pattern

        return False, ""

    def _detect_js_rendered(self, soup: BeautifulSoup) -> bool:
        """Detect if the page content is JavaScript-rendered."""
        text = soup.get_text(strip=True)
        html_str = str(soup)

        signals = 0

        # Very little text content
        if len(text) < 500:
            signals += 2

        # React/Vue/Angular markers
        js_frameworks = ["__NEXT_DATA__", "__NUXT__", "ng-app", "data-reactroot",
                         "data-v-", "id=\"app\"", "id=\"root\"", "id=\"__next\""]
        signals += sum(1 for f in js_frameworks if f in html_str)

        # Empty content containers
        for div in soup.find_all("div", id=re.compile(r'^(app|root|__next|content)$')):
            if len(div.get_text(strip=True)) < 100:
                signals += 2

        return signals >= 3

    def _classify_list_type(self, s: PageStructure) -> str:
        """Classify the overall list type based on detected features."""
        if s.is_js_rendered and s.initial_company_count < 3:
            return "js_app"

        if s.has_alphabetical and s.has_pagination:
            return "alphabetical_paginated"
        if s.has_alphabetical:
            return "alphabetical_list"
        if s.has_pagination:
            return "pagination_list"
        if s.has_filters and s.initial_company_count > 0:
            return "filtered_list"
        if s.has_load_more:
            return "load_more_list"
        if s.has_detail_links and s.initial_company_count > 0:
            return "detail_page_directory"
        if s.initial_company_count > 0:
            return "single_page_list"

        return "empty_or_unknown"

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # STEP 3: NAVIGATION STRATEGY EXECUTION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _execute_strategy(self, soup: BeautifulSoup, structure: PageStructure,
                          exhibitor_url: str, fair_url: str) -> tuple:
        """Execute the appropriate navigation strategy based on structure analysis."""
        all_companies = []
        visited = 1  # already fetched the first page

        # Always extract from initial page
        initial = self._extract_company_names(soup, exhibitor_url)
        all_companies.extend(initial)

        strategy = structure.list_type
        print(f"    🧭 Strateji: {strategy}")

        if strategy == "alphabetical_paginated":
            companies, v = self._navigate_alphabetical(structure, exhibitor_url, fair_url, paginate=True)
            all_companies.extend(companies)
            visited += v

        elif strategy == "alphabetical_list":
            companies, v = self._navigate_alphabetical(structure, exhibitor_url, fair_url, paginate=False)
            all_companies.extend(companies)
            visited += v

        elif strategy == "pagination_list":
            companies, v = self._navigate_pagination(structure, exhibitor_url, fair_url)
            all_companies.extend(companies)
            visited += v

        elif strategy == "filtered_list":
            companies, v = self._navigate_filters(structure, exhibitor_url, fair_url)
            all_companies.extend(companies)
            visited += v

        elif strategy in ("single_page_list", "detail_page_directory"):
            # Try pagination fallback — some pages don't show pagination links but support it
            companies, v = self._try_pagination_fallback(exhibitor_url, fair_url)
            all_companies.extend(companies)
            visited += v

        elif strategy == "js_app":
            # Can't navigate without browser, but try API discovery
            pass

        elif strategy == "load_more_list":
            # Static fetch can't handle load-more, try pagination fallback
            companies, v = self._try_pagination_fallback(exhibitor_url, fair_url)
            all_companies.extend(companies)
            visited += v

        return all_companies, visited

    def _navigate_alphabetical(self, structure: PageStructure,
                                exhibitor_url: str, fair_url: str,
                                paginate: bool = False) -> tuple:
        """Navigate through alphabetical letter tabs."""
        companies = []
        visited = 0
        alpha = structure.alpha_info
        param = alpha.get("param")
        letter_urls = alpha.get("letter_urls", {})

        # If we have direct URLs for each letter
        if letter_urls:
            for letter, letter_url in sorted(letter_urls.items()):
                if not letter_url:
                    # Construct URL from param
                    if param:
                        sep = "&" if "?" in exhibitor_url else "?"
                        letter_url = f"{exhibitor_url}{sep}{param}={letter}"
                    else:
                        continue

                html, _ = self._fetch(letter_url)
                visited += 1
                if html:
                    soup = BeautifulSoup(html, "html.parser")
                    self._clean_soup(soup)
                    names = self._extract_company_names(soup, letter_url)
                    companies.extend(names)

                    # Paginate within this letter
                    if paginate and names:
                        pg_companies, pg_visited = self._paginate_within(letter_url, fair_url)
                        companies.extend(pg_companies)
                        visited += pg_visited

                    if names:
                        print(f"      🔤 {letter}: {len(names)} firma")

                time.sleep(self.delay)

        elif param:
            # Use detected parameter
            for letter in TR_ALPHABET:
                sep = "&" if "?" in exhibitor_url else "?"
                url = f"{exhibitor_url}{sep}{param}={letter}"
                html, _ = self._fetch(url)
                visited += 1
                if html:
                    soup = BeautifulSoup(html, "html.parser")
                    self._clean_soup(soup)
                    names = self._extract_company_names(soup, url)
                    companies.extend(names)

                    if paginate and names:
                        pg_companies, pg_visited = self._paginate_within(url, fair_url)
                        companies.extend(pg_companies)
                        visited += pg_visited

                time.sleep(self.delay)

            # Also try digits
            for digit in "0123456789":
                sep = "&" if "?" in exhibitor_url else "?"
                url = f"{exhibitor_url}{sep}{param}={digit}"
                html, _ = self._fetch(url)
                visited += 1
                if html:
                    soup = BeautifulSoup(html, "html.parser")
                    self._clean_soup(soup)
                    names = self._extract_company_names(soup, url)
                    companies.extend(names)
                time.sleep(self.delay)

        return companies, visited

    def _navigate_pagination(self, structure: PageStructure,
                              exhibitor_url: str, fair_url: str) -> tuple:
        """Navigate through paginated pages."""
        companies = []
        visited = 0
        pag = structure.pagination_info

        if pag.get("param"):
            param = pag["param"]
            max_page = min(pag.get("max_page", 10) + 2, self.max_pages)

            consecutive_empty = 0
            for page in range(2, max_page + 1):
                sep = "&" if "?" in exhibitor_url else "?"
                url = f"{exhibitor_url}{sep}{param}={page}"
                html, _ = self._fetch(url)
                visited += 1

                if html:
                    soup = BeautifulSoup(html, "html.parser")
                    self._clean_soup(soup)
                    names = self._extract_company_names(soup, url)

                    if names:
                        companies.extend(names)
                        consecutive_empty = 0
                        print(f"      📄 Sayfa {page}: +{len(names)} firma")
                    else:
                        consecutive_empty += 1
                        if consecutive_empty >= 2:
                            break
                else:
                    consecutive_empty += 1
                    if consecutive_empty >= 2:
                        break

                time.sleep(self.delay)

        elif pag.get("next_url"):
            next_url = pag["next_url"]
            for _ in range(self.max_pages):
                if not next_url:
                    break
                html, _ = self._fetch(next_url)
                visited += 1
                if not html:
                    break

                soup = BeautifulSoup(html, "html.parser")
                self._clean_soup(soup)
                names = self._extract_company_names(soup, next_url)
                companies.extend(names)

                # Find next link
                next_url = None
                for a in soup.find_all("a", href=True):
                    text = a.get_text(strip=True).lower()
                    if text in ("next", "sonraki", "»", "›", "next page"):
                        next_url = urljoin(exhibitor_url, a["href"])
                        break

                time.sleep(self.delay)

        return companies, visited

    def _navigate_filters(self, structure: PageStructure,
                           exhibitor_url: str, fair_url: str) -> tuple:
        """Navigate through filter options to collect all companies."""
        companies = []
        visited = 0

        for sel in structure.filter_info.get("select_elements", []):
            name = sel["name"]
            for option in sel["options"][:50]:  # limit
                if not option or option.lower() in ("all", "select", "choose"):
                    continue
                sep = "&" if "?" in exhibitor_url else "?"
                url = f"{exhibitor_url}{sep}{name}={requests.utils.quote(option)}"
                html, _ = self._fetch(url)
                visited += 1
                if html:
                    soup = BeautifulSoup(html, "html.parser")
                    self._clean_soup(soup)
                    names = self._extract_company_names(soup, url)
                    companies.extend(names)
                time.sleep(self.delay)

        return companies, visited

    def _paginate_within(self, base_url: str, fair_url: str) -> tuple:
        """Paginate within a single filter (e.g., letter A, page 2, 3...)."""
        companies = []
        visited = 0

        for page in range(2, 20):
            sep = "&" if "?" in base_url else "?"
            url = f"{base_url}{sep}page={page}"
            html, _ = self._fetch(url)
            visited += 1

            if not html:
                break

            soup = BeautifulSoup(html, "html.parser")
            self._clean_soup(soup)
            names = self._extract_company_names(soup, url)

            if not names:
                break

            companies.extend(names)
            time.sleep(self.delay)

        return companies, visited

    def _try_pagination_fallback(self, exhibitor_url: str, fair_url: str) -> tuple:
        """Try common pagination parameters even if not detected on page."""
        companies = []
        visited = 0

        for param in ["page", "p", "sayfa", "pg"]:
            sep = "&" if "?" in exhibitor_url else "?"
            url = f"{exhibitor_url}{sep}{param}=2"
            html, _ = self._fetch(url)
            visited += 1

            if html:
                soup = BeautifulSoup(html, "html.parser")
                self._clean_soup(soup)
                names = self._extract_company_names(soup, url)

                if names:
                    companies.extend(names)
                    print(f"      📄 Gizli pagination bulundu ({param}=2): +{len(names)}")

                    # Continue paginating
                    for page in range(3, self.max_pages):
                        url2 = f"{exhibitor_url}{sep}{param}={page}"
                        html2, _ = self._fetch(url2)
                        visited += 1
                        if not html2:
                            break
                        soup2 = BeautifulSoup(html2, "html.parser")
                        self._clean_soup(soup2)
                        names2 = self._extract_company_names(soup2, url2)
                        if not names2:
                            break
                        companies.extend(names2)
                        print(f"      📄 p{page}: +{len(names2)}")
                        time.sleep(self.delay)

                    break  # Found working param

            time.sleep(self.delay)

        return companies, visited

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # STEP 4: COMPANY EXTRACTION (Multi-strategy)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _extract_company_names(self, soup: BeautifulSoup, url: str) -> list:
        """Extract company names from a parsed page. Tries multiple strategies.
        Order matters: most reliable (detail_links) first, noisiest (headings) last."""
        strategies = [
            self._extract_from_detail_links,  # Most reliable: links to /exhibitor/slug
            self._extract_from_cards,          # Exhibitor cards with class hints
            self._extract_from_table,          # HTML tables
            self._extract_from_structured_list, # ul/ol lists
            self._extract_from_headings,        # h2/h3/h4 sequences (last resort)
        ]

        for strategy in strategies:
            names = strategy(soup, url)
            if names and len(names) >= MIN_COMPANIES_FOR_STRATEGY:
                return names

        return []

    def _extract_from_cards(self, soup: BeautifulSoup, url: str) -> list:
        """Extract from exhibitor cards (div/article with exhibitor-specific classes).
        Uses STRICT class matching to avoid picking up generic site cards."""
        names = []
        # Only match classes that specifically indicate exhibitor/company content
        card_classes = re.compile(
            r'exhibitor(?!-nav|-filter|-search)|'
            r'company(?!-info-page)|firma|participant|aussteller|'
            r'vendor-(?:card|item|list)|sponsor-(?:card|item)',
            re.I
        )

        cards = soup.find_all(["div", "article", "li"], class_=card_classes)

        for card in cards:
            # Only look for company name in headings — not random text
            heading = card.find(["h2", "h3", "h4", "h5"])
            if heading:
                name = heading.get_text(strip=True)
                if self._valid_name(name):
                    names.append(name)
                    continue

            # Fallback: <strong> or <b> inside the card
            strong = card.find(["strong", "b"])
            if strong:
                name = strong.get_text(strip=True)
                if self._valid_name(name):
                    names.append(name)

        return names

    def _extract_from_detail_links(self, soup: BeautifulSoup, url: str) -> list:
        """Extract from links to exhibitor detail pages."""
        names = []
        patterns = [
            re.compile(r'/exhibitor(s)?/[a-z0-9][\w-]+', re.I),
            re.compile(r'/katilimci/[\w-]+', re.I),
            re.compile(r'/participant/[\w-]+', re.I),
            re.compile(r'/company/[\w-]+', re.I),
            re.compile(r'/firma/[\w-]+', re.I),
            re.compile(r'/aussteller/[\w-]+', re.I),
        ]

        for pattern in patterns:
            links = soup.find_all("a", href=pattern)
            if len(links) >= 3:
                for link in links:
                    name = link.get_text(strip=True)
                    if self._valid_name(name):
                        names.append(name)

                if len(names) >= 3:
                    return names

        return names

    def _extract_from_table(self, soup: BeautifulSoup, url: str) -> list:
        """Extract company names from HTML tables."""
        names = []

        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            if len(rows) < 3:
                continue

            for row in rows[1:]:  # Skip header
                cells = row.find_all(["td", "th"])
                if cells:
                    # First cell is usually company name
                    name = cells[0].get_text(strip=True)
                    if self._valid_name(name):
                        names.append(name)

            if len(names) >= 3:
                return names

        return names

    def _extract_from_structured_list(self, soup: BeautifulSoup, url: str) -> list:
        """Extract from structured lists (ul/ol with exhibitor items)."""
        names = []

        for ul in soup.find_all(["ul", "ol"]):
            items = ul.find_all("li", recursive=False)
            if len(items) < 5:
                continue

            item_names = []
            for li in items:
                # Skip if item has sub-lists (navigation menu)
                if li.find(["ul", "ol"]):
                    continue
                text = li.get_text(strip=True)
                if self._valid_name(text):
                    item_names.append(text)

            if len(item_names) >= 5:
                names.extend(item_names)
                return names

        return names

    def _extract_from_headings(self, soup: BeautifulSoup, url: str) -> list:
        """Extract from heading elements that might be company names."""
        names = []

        for tag in ["h3", "h4", "h2"]:
            headings = soup.find_all(tag)
            if len(headings) >= 5:
                for h in headings:
                    name = h.get_text(strip=True)
                    if self._valid_name(name):
                        names.append(name)

                if len(names) >= 5:
                    return names

        return names

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # UTILITIES
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _fetch(self, url: str) -> tuple:
        """Fetch a URL. Returns (html, status_code)."""
        try:
            r = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            if r.status_code == 200:
                return r.text, 200
            return None, r.status_code
        except requests.RequestException as e:
            return None, str(e)[:50]

    def _clean_soup(self, soup: BeautifulSoup):
        """Remove noise elements from soup."""
        for tag in soup.find_all(["nav", "header", "footer", "script", "style",
                                   "noscript", "iframe", "svg"]):
            tag.decompose()

    def _valid_name(self, text: str) -> bool:
        """Check if text looks like a company name."""
        if not text:
            return False
        text = text.strip()
        if len(text) < MIN_NAME_LEN or len(text) > MAX_NAME_LEN:
            return False

        lower = text.lower()

        # Skip navigation/UI elements (exact match)
        if lower in SKIP_NAMES:
            return False

        # Skip if any skip phrase is contained
        for skip in SKIP_NAMES:
            if len(skip) > 3 and skip in lower:
                return False

        # Skip pure numbers or dates
        cleaned = text.replace(" ", "").replace("-", "").replace(".", "").replace(",", "")
        if cleaned.isdigit():
            return False

        # Skip if too many words (not a company name)
        if len(text.split()) > MAX_WORD_COUNT:
            return False

        # Skip very common non-company patterns
        if re.match(r'^(page|sayfa|next|prev|back|show|view|see|göster|gör)\s', lower):
            return False

        # Skip if it looks like a URL or email
        if text.startswith("http") or text.startswith("www.") or "@" in text:
            return False

        # Skip if it's a single common word
        single_word_skip = {
            "the", "and", "or", "for", "with", "from", "by", "of", "in", "on",
            "at", "to", "is", "it", "this", "that", "an", "a", "bir", "ve",
            "ile", "için", "bu", "şu",
        }
        if lower in single_word_skip:
            return False

        # Must have at least one letter
        if not re.search(r'[a-zA-ZçğıöşüÇĞİÖŞÜ]', text):
            return False

        # Skip if it starts with a question word (FAQ items)
        if re.match(r'^(how|what|when|where|why|which|nasıl|ne|nerede|neden|hangi)\s', lower):
            return False

        return True

    def _normalize_name(self, name: str) -> str:
        """Normalize company name for deduplication."""
        if not name:
            return ""
        n = name.strip().lower()
        # Remove common suffixes
        for suffix in [" ltd", " ltd.", " co.", " inc.", " inc",
                       " a.ş.", " a.s.", " gmbh", " bv", " nv",
                       " srl", " spa", " sa", " ag"]:
            n = n.replace(suffix, "")
        # Remove extra whitespace
        n = re.sub(r'\s+', ' ', n).strip()
        return n


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python exhibitor_navigator.py <exhibitor_url> [fair_url]")
        sys.exit(1)

    url = sys.argv[1]
    fair_url = sys.argv[2] if len(sys.argv) > 2 else url

    nav = ExhibitorNavigator()
    result = nav.navigate(url, fair_url)

    print(f"\n{'='*60}")
    print(f"📊 NAVIGATOR SONUCU")
    print(f"{'='*60}")
    print(f"  URL: {result.exhibitor_url}")
    print(f"  List Type: {result.list_type}")
    print(f"  Navigation: {result.navigation_detected}")
    print(f"  Visited URLs: {result.visited_urls}")
    print(f"  Companies Found: {result.companies_found}")
    print(f"  Deduplicated: {result.deduplicated_companies}")
    print(f"  Method: {result.method}")
    if result.companies:
        print(f"\n  İlk 20 firma:")
        for i, c in enumerate(result.companies[:20], 1):
            print(f"    {i:2d}. {c}")
