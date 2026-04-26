"""
Base Scraper — Abstract foundation for all fair scrapers.
"""

import time
import re
import requests
from abc import ABC, abstractmethod
from typing import Optional
from bs4 import BeautifulSoup
from rich.console import Console

import config

console = Console()


class CompanyData:
    """Data class for a scraped company."""

    def __init__(self, name: str, website: str = None, booth_number: str = None,
                 sector: str = None, country: str = None, city: str = None,
                 description: str = None, logo_url: str = None, raw_data: dict = None,
                 email: str = None, phone: str = None, address: str = None):
        self.name = name.strip() if name else ""
        self.website = self._clean_url(website)
        self.booth_number = booth_number
        self.sector = sector
        self.country = country
        self.city = city
        self.description = description
        self.logo_url = logo_url
        self.raw_data = raw_data or {}
        self.email = email
        self.phone = phone
        self.address = address

    def _clean_url(self, url: str) -> Optional[str]:
        """Clean and normalize a URL."""
        if not url:
            return None
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        # Remove trailing slash
        url = url.rstrip("/")
        return url

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "website": self.website,
            "booth_number": self.booth_number,
            "sector": self.sector,
            "country": self.country,
            "city": self.city,
            "description": self.description,
            "logo_url": self.logo_url,
            "raw_data": self.raw_data,
            "email": self.email,
            "phone": self.phone,
            "address": self.address,
        }

    def __repr__(self):
        return f"CompanyData(name='{self.name}', website='{self.website}')"


class BaseScraper(ABC):
    """Abstract base class for fair scrapers."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": config.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        })
        self.companies: list[CompanyData] = []

    @property
    @abstractmethod
    def fair_name(self) -> str:
        """Human-readable name of the fair."""
        pass

    @property
    @abstractmethod
    def fair_slug(self) -> str:
        """URL-safe slug for the fair."""
        pass

    @property
    @abstractmethod
    def fair_url(self) -> str:
        """Base URL of the fair website."""
        pass

    @abstractmethod
    def scrape(self) -> list[CompanyData]:
        """Scrape exhibitor list. Returns list of CompanyData."""
        pass

    def _get_page(self, url: str, retry: int = 0) -> Optional[BeautifulSoup]:
        """Fetch a page and return BeautifulSoup object."""
        try:
            console.print(f"  [dim]Fetching: {url}[/dim]")
            response = self.session.get(url, timeout=config.REQUEST_TIMEOUT)
            response.raise_for_status()
            time.sleep(config.REQUEST_DELAY)
            return BeautifulSoup(response.text, "lxml")
        except requests.RequestException as e:
            if retry < config.MAX_RETRIES:
                console.print(f"  [yellow]Retry {retry + 1}/{config.MAX_RETRIES}...[/yellow]")
                time.sleep(config.REQUEST_DELAY * (retry + 1))
                return self._get_page(url, retry + 1)
            console.print(f"  [red]Failed to fetch {url}: {e}[/red]")
            return None

    def _get_json(self, url: str, retry: int = 0) -> Optional[dict]:
        """Fetch JSON from a URL."""
        try:
            console.print(f"  [dim]Fetching JSON: {url}[/dim]")
            response = self.session.get(url, timeout=config.REQUEST_TIMEOUT)
            response.raise_for_status()
            time.sleep(config.REQUEST_DELAY)
            return response.json()
        except (requests.RequestException, ValueError) as e:
            if retry < config.MAX_RETRIES:
                console.print(f"  [yellow]Retry {retry + 1}/{config.MAX_RETRIES}...[/yellow]")
                time.sleep(config.REQUEST_DELAY * (retry + 1))
                return self._get_json(url, retry + 1)
            console.print(f"  [red]Failed to fetch JSON {url}: {e}[/red]")
            return None

    def _extract_domain(self, url: str) -> Optional[str]:
        """Extract domain from URL."""
        if not url:
            return None
        match = re.search(r'https?://(?:www\.)?([^/]+)', url)
        return match.group(1) if match else None

    def get_results(self) -> list[dict]:
        """Get scraped results as list of dicts."""
        return [c.to_dict() for c in self.companies]

    def print_summary(self):
        """Print scraping summary."""
        total = len(self.companies)
        with_website = sum(1 for c in self.companies if c.website)
        with_sector = sum(1 for c in self.companies if c.sector)
        with_country = sum(1 for c in self.companies if c.country)

        console.print(f"\n[bold green]{'═' * 50}[/bold green]")
        console.print(f"[bold]{self.fair_name} — Scraping Summary[/bold]")
        console.print(f"[bold green]{'═' * 50}[/bold green]")
        console.print(f"  Total companies: [bold cyan]{total}[/bold cyan]")
        console.print(f"  With website:    [bold cyan]{with_website}[/bold cyan] ({with_website/total*100:.0f}%)" if total else "")
        console.print(f"  With sector:     [bold cyan]{with_sector}[/bold cyan] ({with_sector/total*100:.0f}%)" if total else "")
        console.print(f"  With country:    [bold cyan]{with_country}[/bold cyan] ({with_country/total*100:.0f}%)" if total else "")
        console.print()
