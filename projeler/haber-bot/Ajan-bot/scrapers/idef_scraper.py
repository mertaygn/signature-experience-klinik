"""
IDEF Fair Scraper
Scrapes exhibitor list from idef.com.tr using alphabet filter URLs.

The IDEF site uses Laravel Livewire. The exhibitor list can be filtered
by appending ?a=A, ?a=B, etc. to the URL. Each filtered page contains
server-rendered company cards with names, countries, and subdomain links.

Total: ~1491 exhibitors across 71 pages (unfiltered).
"""

import re
import time
import string
from typing import Optional
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from rich.console import Console

from scrapers.base_scraper import BaseScraper, CompanyData

console = Console()

# Turkish alphabet for comprehensive coverage
TURKISH_ALPHABET = list(string.ascii_uppercase) + ["Ç", "Ğ", "İ", "Ö", "Ş", "Ü"]
# Also try digits for companies starting with numbers
DIGITS = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"]


class IDEFScraper(BaseScraper):
    """Scraper for IDEF - International Defence Exhibition.

    Uses alphabet-filtered URL parameters (?a=A, ?a=B, etc.)
    to fetch exhibitor cards from the Livewire-powered page.
    """

    BASE_EXHIBITOR_URL = "https://idef.com.tr/katilimci-listesi"

    @property
    def fair_name(self) -> str:
        return "IDEF 2025 - International Defence Exhibition"

    @property
    def fair_slug(self) -> str:
        return "idef"

    @property
    def fair_url(self) -> str:
        return "https://www.idef.com.tr"

    def scrape(self) -> list[CompanyData]:
        """Scrape IDEF exhibitor list using alphabet filter."""
        console.print(f"\n[bold blue]🔍 Scraping {self.fair_name}...[/bold blue]")
        console.print(f"  [dim]Strategy: Alphabet filter (?a=A..Z + digits)[/dim]")

        all_companies = []
        seen_names = set()

        # First try: unfiltered page to get total and first batch
        console.print(f"\n  [bold]Fetching unfiltered page...[/bold]")
        first_page_companies = self._scrape_page(self.BASE_EXHIBITOR_URL)

        # Check if unfiltered page has pagination
        if first_page_companies:
            for c in first_page_companies:
                if c.name not in seen_names:
                    seen_names.add(c.name)
                    all_companies.append(c)
            console.print(f"  [green]First page: {len(first_page_companies)} companies[/green]")

            # Try pagination on unfiltered page
            page = 2
            while True:
                url = f"{self.BASE_EXHIBITOR_URL}?page={page}"
                page_companies = self._scrape_page(url)
                if not page_companies:
                    break

                new_count = 0
                for c in page_companies:
                    if c.name not in seen_names:
                        seen_names.add(c.name)
                        all_companies.append(c)
                        new_count += 1

                if new_count == 0:
                    break  # No new companies found

                console.print(f"  [dim]Page {page}: +{new_count} new — total: {len(all_companies)}[/dim]")
                page += 1

                if page > 100:  # Safety limit
                    break

        # If pagination didn't work well, try alphabet filter
        if len(all_companies) < 100:
            console.print(f"\n  [bold]Trying alphabet filter...[/bold]")
            all_companies = []
            seen_names = set()

            for letter in TURKISH_ALPHABET + DIGITS:
                url = f"{self.BASE_EXHIBITOR_URL}?a={letter}"
                companies = self._scrape_page(url)

                if companies:
                    new_count = 0
                    for c in companies:
                        if c.name not in seen_names:
                            seen_names.add(c.name)
                            all_companies.append(c)
                            new_count += 1

                    if new_count > 0:
                        console.print(f"  [dim]Letter '{letter}': +{new_count} — total: {len(all_companies)}[/dim]")

                    # Check for pagination within this letter
                    page = 2
                    while True:
                        page_url = f"{self.BASE_EXHIBITOR_URL}?a={letter}&page={page}"
                        page_companies = self._scrape_page(page_url)
                        if not page_companies:
                            break

                        new_in_page = 0
                        for c in page_companies:
                            if c.name not in seen_names:
                                seen_names.add(c.name)
                                all_companies.append(c)
                                new_in_page += 1

                        if new_in_page == 0:
                            break

                        console.print(f"  [dim]  └─ Page {page}: +{new_in_page}[/dim]")
                        page += 1

                        if page > 50:  # Safety
                            break

        self.companies = all_companies
        console.print(f"\n  [bold green]✓ Total: {len(all_companies)} companies found![/bold green]")
        return all_companies

    def _scrape_page(self, url: str) -> list[CompanyData]:
        """Scrape a single page for company cards."""
        soup = self._get_page(url)
        if not soup:
            return []

        companies = []

        # Strategy 1: Find links to company subdomains (*.idef.com.tr)
        # Each company card has an overlay <a> link to their subdomain
        company_links = soup.find_all("a", href=re.compile(
            r'https?://[a-zA-Z0-9][\w-]*\.idef\.com\.tr'
        ))

        processed_cards = set()

        for link in company_links:
            href = link.get("href", "")

            # Skip main site links
            if href.rstrip("/") in [
                "https://idef.com.tr", "https://www.idef.com.tr",
                "https://kp.idef.com.tr", "https://dot.idef.com.tr",
            ]:
                continue

            # Skip non-company subdomains
            if any(x in href for x in ["kp.idef", "dot.idef", "cdn.idef"]):
                continue

            # Find parent card element (go up until we find a meaningful container)
            card = link
            for _ in range(8):
                parent = card.parent
                if parent and parent.name in ["div", "article", "li", "section"]:
                    card = parent
                    # Check if this card has some substance
                    card_text = card.get_text(strip=True)
                    if len(card_text) > 5:
                        break

            card_id = id(card)
            if card_id in processed_cards:
                continue
            processed_cards.add(card_id)

            # Extract company name and country from card text
            name, country = self._extract_name_country(card)

            if not name or len(name) < 2:
                continue

            # Extract logo
            logo = None
            img = card.find("img")
            if img:
                src = img.get("src") or img.get("data-src") or ""
                if src:
                    logo = urljoin("https://idef.com.tr", src)

            company = CompanyData(
                name=name,
                website=href,
                country=country,
                logo_url=logo,
            )
            companies.append(company)

        # Strategy 2: If no subdomain links found, try general card parsing
        if not companies:
            companies = self._parse_generic_cards(soup)

        return companies

    def _extract_name_country(self, card) -> tuple:
        """Extract company name and country from a card element."""
        name = None
        country = None

        # Known country names
        countries = {
            "Türkiye", "Almanya", "ABD", "Fransa", "İngiltere", "İtalya",
            "İspanya", "Kanada", "Japonya", "Güney Kore", "Kore",
            "Avustralya", "Brezilya", "Hindistan", "Çin", "Rusya",
            "İsrail", "Pakistan", "Azerbaycan", "Gürcistan",
            "Birleşik Arap Emirlikleri", "Suudi Arabistan", "Katar",
            "Ürdün", "Norveç", "İsveç", "Finlandiya", "Polonya",
            "Çekya", "Ukrayna", "Romanya", "Bulgaristan", "Sırbistan",
            "Hollanda", "Belçika", "Avusturya", "İsviçre", "Portekiz",
            "Danimarka", "Malezya", "Singapur", "Endonezya",
            "Tayvan", "Tayland", "Meksika", "Kolombiya", "Arjantin",
            # English names
            "Turkey", "Germany", "USA", "France", "United Kingdom",
            "Italy", "Spain", "Canada", "Japan", "South Korea",
            "Australia", "Brazil", "India", "China", "Russia",
            "Israel", "Pakistan", "Azerbaijan", "Georgia",
            "United Arab Emirates", "Saudi Arabia", "Qatar",
            "Jordan", "Norway", "Sweden", "Finland", "Poland",
            "Czech Republic", "Ukraine", "Romania", "Bulgaria", "Serbia",
            "Netherlands", "Belgium", "Austria", "Switzerland", "Portugal",
            "Denmark", "Malaysia", "Singapore", "Indonesia",
        }

        # Get all text segments from the card
        texts = []
        for el in card.find_all(["h2", "h3", "h4", "h5", "p", "span", "strong", "b", "div"]):
            text = el.get_text(strip=True)
            if text and 2 < len(text) < 200:
                texts.append(text)

        # If no structured text found, get all strings
        if not texts:
            texts = [t.strip() for t in card.stripped_strings if 2 < len(t.strip()) < 200]

        for text in texts:
            if text in countries:
                country = text
            elif not name and text not in ["IDEF", "idef", "Katılımcı"]:
                # First non-country text is likely the company name
                name = text

        return name, country

    def _parse_generic_cards(self, soup) -> list[CompanyData]:
        """Fallback: parse any card-like structures."""
        companies = []

        # Look for repeated div structures that might be company cards
        containers = soup.find_all("div", class_=re.compile(
            r"card|exhibitor|participant|company|item|grid", re.I
        ))

        seen = set()
        for container in containers:
            # Must have some text content
            text_el = container.find(["h2", "h3", "h4", "h5", "strong", "b", "p"])
            if text_el:
                name = text_el.get_text(strip=True)
                if name and len(name) > 2 and name not in seen:
                    seen.add(name)
                    companies.append(CompanyData(name=name))

        return companies
