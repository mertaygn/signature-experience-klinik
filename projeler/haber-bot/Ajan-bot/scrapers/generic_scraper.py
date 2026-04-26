"""
Generic Fair Scraper
Attempts to scrape exhibitor lists from any fair URL.
Uses heuristics to discover and parse exhibitor data.
"""

import re
from urllib.parse import urljoin, urlparse
from rich.console import Console

from scrapers.base_scraper import BaseScraper, CompanyData

console = Console()


class GenericScraper(BaseScraper):
    """Generic scraper that tries to extract exhibitor lists from any fair URL."""

    def __init__(self, url: str, name: str = None, slug: str = None):
        super().__init__()
        self._url = url.rstrip("/")
        self._name = name or self._extract_name_from_url(url)
        self._slug = slug or urlparse(url).netloc.replace(".", "_").replace("www_", "")

    @property
    def fair_name(self) -> str:
        return self._name

    @property
    def fair_slug(self) -> str:
        return self._slug

    @property
    def fair_url(self) -> str:
        return self._url

    def _extract_name_from_url(self, url: str) -> str:
        """Extract a readable name from URL."""
        domain = urlparse(url).netloc.replace("www.", "")
        name = domain.split(".")[0]
        return name.upper().replace("-", " ").replace("_", " ")

    def scrape(self) -> list[CompanyData]:
        """Smart scrape: discover exhibitor pages and parse them."""
        console.print(f"\n[bold blue]🔍 Generic Scraping: {self.fair_name}[/bold blue]")
        console.print(f"  [dim]URL: {self.fair_url}[/dim]")

        # Step 1: Try direct exhibitor page URLs
        companies = self._try_direct_urls()
        if companies:
            return companies

        # Step 2: Crawl homepage to find exhibitor links
        companies = self._discover_from_homepage()
        if companies:
            return companies

        # Step 3: Try API endpoints
        companies = self._try_api_endpoints()
        if companies:
            return companies

        console.print("[yellow]⚠ Could not find exhibitor data automatically.[/yellow]")
        console.print("[dim]Tip: Try providing the direct exhibitor list URL.[/dim]")
        return []

    def _try_direct_urls(self) -> list[CompanyData]:
        """Try common exhibitor page URL patterns."""
        suffixes = [
            "/exhibitors", "/exhibitor-list", "/exhibitor",
            "/katilimcilar", "/katilimci-listesi",
            "/participants", "/participant-list",
            "/companies", "/company-list",
            "/en/exhibitors", "/en/exhibitor-list",
            "/tr/katilimcilar", "/tr/katilimci-listesi",
            "/firsts", "/firmalar",
        ]

        for suffix in suffixes:
            url = f"{self.fair_url}{suffix}"
            soup = self._get_page(url)
            if soup:
                text = soup.get_text(strip=True)
                if len(text) > 500:
                    console.print(f"  [green]✓ Found page: {url}[/green]")
                    companies = self._smart_parse(soup, url)
                    if companies:
                        return companies

        return []

    def _discover_from_homepage(self) -> list[CompanyData]:
        """Crawl homepage to discover exhibitor-related links."""
        console.print("  [dim]Discovering from homepage...[/dim]")
        homepage = self._get_page(self.fair_url)
        if not homepage:
            return []

        # Keywords that suggest exhibitor pages
        keywords = [
            "exhibitor", "katılımcı", "katilimci", "participant",
            "company", "firma", "iştirakçi", "stand",
        ]

        discovered_links = set()
        for link in homepage.find_all("a", href=True):
            href = link["href"]
            text = (link.get_text(strip=True) + " " + href).lower()
            if any(kw in text for kw in keywords):
                full_url = urljoin(self.fair_url, href)
                if full_url.startswith(self.fair_url):
                    discovered_links.add(full_url)

        for link in discovered_links:
            console.print(f"  [dim]Trying discovered link: {link}[/dim]")
            soup = self._get_page(link)
            if soup:
                companies = self._smart_parse(soup, link)
                if companies:
                    return companies

        return []

    def _try_api_endpoints(self) -> list[CompanyData]:
        """Try common API endpoint patterns."""
        api_suffixes = [
            "/api/exhibitors", "/api/v1/exhibitors",
            "/api/participants", "/api/companies",
            "/wp-json/wp/v2/exhibitors",
            "/api/v2/exhibitors",
        ]

        for suffix in api_suffixes:
            url = f"{self.fair_url}{suffix}"
            data = self._get_json(url)
            if data:
                companies = self._parse_json_data(data)
                if companies:
                    console.print(f"  [green]✓ Found API: {url}[/green]")
                    return companies

        return []

    def _smart_parse(self, soup, url: str) -> list[CompanyData]:
        """Intelligently parse a page for exhibitor data."""
        companies = []

        # Strategy 1: Find the largest list structure
        strategies = [
            self._parse_table,
            self._parse_cards,
            self._parse_list,
            self._parse_links,
        ]

        for strategy in strategies:
            result = strategy(soup)
            if result and len(result) >= 3:
                companies = result
                console.print(f"  [green]Parsed {len(companies)} companies[/green]")
                break

        self.companies = companies
        return companies

    def _parse_table(self, soup) -> list[CompanyData]:
        """Parse company data from HTML tables."""
        companies = []
        tables = soup.find_all("table")

        for table in tables:
            rows = table.find_all("tr")
            if len(rows) < 3:
                continue

            for row in rows[1:]:
                cells = row.find_all(["td", "th"])
                if cells:
                    name = cells[0].get_text(strip=True)
                    if name and 2 < len(name) < 150:
                        company = CompanyData(name=name)
                        # Look for website link
                        link = cells[0].find("a", href=True)
                        if link and "http" in link["href"]:
                            company.website = link["href"]
                        if len(cells) > 1:
                            company.booth_number = cells[1].get_text(strip=True)
                        if len(cells) > 2:
                            company.country = cells[2].get_text(strip=True)
                        companies.append(company)

        return companies

    def _parse_cards(self, soup) -> list[CompanyData]:
        """Parse company data from card/div layouts."""
        companies = []
        patterns = [
            re.compile(r"exhibitor|participant|company|firma|katilimci", re.I),
            re.compile(r"card|grid-item|list-item", re.I),
        ]

        for pattern in patterns:
            cards = soup.find_all(["div", "li", "article"], class_=pattern)
            if len(cards) >= 3:
                for card in cards:
                    name_el = card.find(["h2", "h3", "h4", "h5", "a", "strong", "b"])
                    if name_el:
                        name = name_el.get_text(strip=True)
                        if name and 2 < len(name) < 150:
                            company = CompanyData(name=name)
                            # Website
                            for link in card.find_all("a", href=True):
                                href = link["href"]
                                if "http" in href and self.fair_url not in href:
                                    company.website = href
                                    break
                            # Logo
                            img = card.find("img")
                            if img and img.get("src"):
                                company.logo_url = urljoin(self.fair_url, img["src"])
                            companies.append(company)
                break

        return companies

    def _parse_list(self, soup) -> list[CompanyData]:
        """Parse from ul/ol list elements."""
        companies = []
        lists = soup.find_all(["ul", "ol"])

        for lst in lists:
            items = lst.find_all("li")
            if len(items) >= 5:
                for item in items:
                    text = item.get_text(strip=True)
                    if text and 2 < len(text) < 150:
                        company = CompanyData(name=text)
                        link = item.find("a", href=True)
                        if link and "http" in link["href"]:
                            company.website = link["href"]
                        companies.append(company)
                if len(companies) >= 5:
                    break

        return companies

    def _parse_links(self, soup) -> list[CompanyData]:
        """Last resort: parse company names from anchor links."""
        companies = []
        seen_names = set()

        for link in soup.find_all("a", href=True):
            text = link.get_text(strip=True)
            href = link["href"]

            if (text and 3 < len(text) < 100 and text not in seen_names and
                not any(x in text.lower() for x in
                        ["home", "about", "contact", "menu", "login", "register",
                         "anasayfa", "hakkımızda", "iletişim"]) and
                not any(x in href.lower() for x in
                        ["facebook", "twitter", "instagram", "youtube", "linkedin",
                         "mailto:", "tel:", "javascript:"])):

                # Only external links suggest company websites
                if "http" in href and self.fair_url not in href:
                    companies.append(CompanyData(name=text, website=href))
                    seen_names.add(text)

        return companies

    def _parse_json_data(self, data) -> list[CompanyData]:
        """Parse JSON API response."""
        companies = []
        items = data if isinstance(data, list) else data.get("data", data.get("items", data.get("results", [])))

        for item in (items if isinstance(items, list) else []):
            if isinstance(item, dict):
                name = (item.get("name") or item.get("title") or
                        item.get("company_name") or item.get("firma_adi") or "")
                if name:
                    companies.append(CompanyData(
                        name=name,
                        website=item.get("website") or item.get("web") or item.get("url"),
                        booth_number=item.get("booth") or item.get("stand"),
                        sector=item.get("sector") or item.get("category"),
                        country=item.get("country") or item.get("ulke"),
                        raw_data=item,
                    ))

        self.companies = companies
        return companies
