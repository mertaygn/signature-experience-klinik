"""
SAHA EXPO Fair Scraper
Scrapes exhibitor list from sahaexpo.com
"""

import re
from typing import Optional
from rich.console import Console

from scrapers.base_scraper import BaseScraper, CompanyData

console = Console()


class SahaExpoScraper(BaseScraper):
    """Scraper for SAHA EXPO — Defence, Aviation & Space Industry Fair."""

    @property
    def fair_name(self) -> str:
        return "SAHA EXPO — Savunma, Havacılık ve Uzay Sanayi Fuarı"

    @property
    def fair_slug(self) -> str:
        return "saha_expo"

    @property
    def fair_url(self) -> str:
        return "https://sahaexpo.com"

    def scrape(self) -> list[CompanyData]:
        """Scrape SAHA EXPO exhibitor list."""
        console.print(f"\n[bold blue]🔍 Scraping {self.fair_name}...[/bold blue]")

        # Try multiple possible URL patterns
        urls_to_try = [
            f"{self.fair_url}/katilimcilar",
            f"{self.fair_url}/katilimci-listesi",
            f"{self.fair_url}/exhibitors",
            f"{self.fair_url}/exhibitor-list",
            f"{self.fair_url}/en/exhibitors",
            f"{self.fair_url}/tr/katilimcilar",
            f"{self.fair_url}/participants",
        ]

        soup = None
        for url in urls_to_try:
            soup = self._get_page(url)
            if soup:
                body_text = soup.get_text(strip=True)
                if len(body_text) > 500:
                    console.print(f"  [green]Found exhibitor page: {url}[/green]")
                    break
                soup = None

        if not soup:
            console.print("[yellow]⚠ Could not find exhibitor page directly.[/yellow]")
            console.print("[yellow]  Trying homepage and API discovery...[/yellow]")
            return self._discover_and_scrape()

        return self._parse_exhibitor_page(soup)

    def _discover_and_scrape(self) -> list[CompanyData]:
        """Try to discover exhibitor data from the homepage."""
        homepage = self._get_page(self.fair_url)
        if not homepage:
            return []

        # Look for links containing exhibitor-related keywords
        exhibitor_links = []
        for link in homepage.find_all("a", href=True):
            href = link["href"]
            text = link.get_text(strip=True).lower()
            if any(kw in href.lower() or kw in text for kw in
                   ["exhibitor", "katılımcı", "katilimci", "participant", "firma"]):
                full_url = href if href.startswith("http") else f"{self.fair_url}{href}"
                exhibitor_links.append(full_url)
                console.print(f"  [dim]Found potential link: {full_url}[/dim]")

        for link in exhibitor_links:
            soup = self._get_page(link)
            if soup:
                companies = self._parse_exhibitor_page(soup)
                if companies:
                    return companies

        # Try API-based approach
        return self._try_api_scrape()

    def _parse_exhibitor_page(self, soup) -> list[CompanyData]:
        """Parse exhibitor list from HTML."""
        companies = []

        # SAHA EXPO often uses card-based layout
        # Try common patterns
        card_patterns = [
            soup.find_all("div", class_=re.compile(r"exhibitor|participant|company|firma", re.I)),
            soup.find_all("div", class_=re.compile(r"card|item", re.I)),
            soup.find_all("li", class_=re.compile(r"exhibitor|participant|company", re.I)),
            soup.find_all("article"),
        ]

        for cards in card_patterns:
            if cards and len(cards) >= 3:  # at least 3 items to be a list
                for card in cards:
                    name_el = card.find(["h2", "h3", "h4", "h5", "a", "strong"])
                    if name_el:
                        name = name_el.get_text(strip=True)
                        if name and len(name) > 2:
                            company = CompanyData(name=name)

                            # Find website
                            links = card.find_all("a", href=True)
                            for link in links:
                                href = link["href"]
                                if "http" in href and self.fair_url not in href:
                                    company.website = href
                                    break

                            # Find sector/country info
                            for el in card.find_all(["span", "p", "small", "div"]):
                                text = el.get_text(strip=True)
                                if text and text != name and len(text) < 100:
                                    if not company.sector:
                                        company.sector = text

                            # Find logo
                            img = card.find("img")
                            if img and img.get("src"):
                                company.logo_url = img["src"]

                            companies.append(company)
                break

        # Fallback: table-based
        if not companies:
            tables = soup.find_all("table")
            for table in tables:
                rows = table.find_all("tr")
                if len(rows) >= 3:
                    for row in rows[1:]:
                        cells = row.find_all(["td", "th"])
                        if cells:
                            name = cells[0].get_text(strip=True)
                            if name and len(name) > 2:
                                company = CompanyData(name=name)
                                link = cells[0].find("a", href=True)
                                if link:
                                    href = link["href"]
                                    if "http" in href and self.fair_url not in href:
                                        company.website = href
                                if len(cells) > 1:
                                    company.booth_number = cells[1].get_text(strip=True)
                                if len(cells) > 2:
                                    company.country = cells[2].get_text(strip=True)
                                companies.append(company)

        self.companies = companies
        console.print(f"  [green]Found {len(companies)} companies[/green]")
        return companies

    def _try_api_scrape(self) -> list[CompanyData]:
        """Try to find exhibitor data via API endpoints."""
        api_urls = [
            f"{self.fair_url}/api/exhibitors",
            f"{self.fair_url}/api/participants",
            f"{self.fair_url}/api/v1/companies",
        ]

        for url in api_urls:
            data = self._get_json(url)
            if data:
                console.print(f"  [green]Found API: {url}[/green]")
                return self._parse_api_data(data)

        console.print("  [yellow]No exhibitors found via any method.[/yellow]")
        return []

    def _parse_api_data(self, data) -> list[CompanyData]:
        """Parse JSON API data."""
        companies = []
        items = data if isinstance(data, list) else data.get("data", data.get("items", []))

        for item in (items if isinstance(items, list) else []):
            if isinstance(item, dict):
                name = item.get("name") or item.get("title") or item.get("company_name") or ""
                if name:
                    companies.append(CompanyData(
                        name=name,
                        website=item.get("website") or item.get("web"),
                        booth_number=item.get("booth") or item.get("stand"),
                        sector=item.get("sector") or item.get("category"),
                        country=item.get("country"),
                        raw_data=item,
                    ))

        self.companies = companies
        return companies
