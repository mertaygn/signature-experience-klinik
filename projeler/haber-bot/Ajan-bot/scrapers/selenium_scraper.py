"""
Selenium-based Scraper for JavaScript-rendered pages.
Used when sites load exhibitor data dynamically via JS.
Requires: pip install selenium
"""

import re
import time
import json
from typing import Optional
from rich.console import Console

from scrapers.base_scraper import BaseScraper, CompanyData

console = Console()


def get_selenium_driver():
    """Create a headless Chrome/Chromium Selenium driver."""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service

        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                             "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(30)
        return driver

    except ImportError:
        console.print("[red]Selenium not installed. Run: pip install selenium[/red]")
        return None
    except Exception as e:
        console.print(f"[red]Could not create Selenium driver: {e}[/red]")
        console.print("[dim]Make sure Chrome/Chromium is installed.[/dim]")
        return None


class SeleniumIDEFScraper(BaseScraper):
    """Selenium-based scraper for IDEF exhibitor list (JS-rendered pages)."""

    EXHIBITOR_URL = "https://idef.com.tr/katilimci-listesi"

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
        """Scrape IDEF using Selenium to handle JS rendering."""
        console.print(f"\n[bold blue]🔍 Scraping {self.fair_name} (Selenium)...[/bold blue]")
        console.print(f"  [dim]URL: {self.EXHIBITOR_URL}[/dim]")

        driver = get_selenium_driver()
        if not driver:
            return []

        try:
            return self._scrape_with_driver(driver)
        finally:
            driver.quit()

    def _scrape_with_driver(self, driver) -> list[CompanyData]:
        """Perform the actual scraping with Selenium."""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        all_companies = []
        seen_names = set()

        console.print("  [dim]Loading exhibitor page...[/dim]")
        driver.get(self.EXHIBITOR_URL)
        time.sleep(5)  # Wait for JS app to render

        # Try to find total page count
        total_pages = self._get_total_pages(driver)
        console.print(f"  [dim]Found {total_pages} pages[/dim]")

        for page_num in range(1, total_pages + 1):
            if page_num > 1:
                # Navigate to next page
                if not self._goto_page(driver, page_num):
                    console.print(f"  [yellow]Could not navigate to page {page_num}[/yellow]")
                    break
                time.sleep(3)  # Wait for content to load

            # Parse current page
            page_source = driver.page_source
            companies = self._parse_page(page_source)

            for company in companies:
                if company.name not in seen_names:
                    seen_names.add(company.name)
                    all_companies.append(company)

            console.print(f"  [dim]Page {page_num}/{total_pages} — "
                          f"found {len(companies)} — total: {len(all_companies)}[/dim]")

        self.companies = all_companies
        return all_companies

    def _get_total_pages(self, driver) -> int:
        """Get total number of pages from pagination."""
        try:
            from selenium.webdriver.common.by import By

            # Look for pagination elements
            page_source = driver.page_source
            # Find the highest page number in pagination links
            import re
            page_numbers = re.findall(r'>\s*(\d+)\s*</(?:a|button|li|span)', page_source)
            if page_numbers:
                return max(int(n) for n in page_numbers if n.isdigit())
        except Exception:
            pass
        return 71  # Known IDEF page count as fallback

    def _goto_page(self, driver, page_num: int) -> bool:
        """Navigate to a specific page."""
        from selenium.webdriver.common.by import By

        try:
            # Try clicking the page number button
            # Look for pagination buttons/links
            buttons = driver.find_elements(By.CSS_SELECTOR, "button, a")
            for btn in buttons:
                try:
                    text = btn.text.strip()
                    if text == str(page_num):
                        btn.click()
                        return True
                except Exception:
                    continue

            # Try URL-based pagination
            driver.get(f"{self.EXHIBITOR_URL}?page={page_num}")
            time.sleep(3)
            return True

        except Exception:
            return False

    def _parse_page(self, html: str) -> list[CompanyData]:
        """Parse company cards from page HTML."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        companies = []

        # IDEF cards have: logo, company name, country
        # Links point to *.idef.com.tr subdomains

        # Strategy 1: Find all cards containing company data
        # Each card has an overlay link with class containing 'absolute inset-0'
        links = soup.find_all("a", href=re.compile(r'https?://[a-zA-Z0-9-]+\.idef\.com\.tr'))
        processed_parents = set()

        for link in links:
            href = link.get("href", "")

            # Skip the main idef.com.tr links
            if href in ["https://idef.com.tr", "https://www.idef.com.tr",
                         "https://idef.com.tr/", "https://www.idef.com.tr/"]:
                continue

            # Find the parent card
            card = link
            for _ in range(5):
                parent = card.parent
                if parent and parent.name in ["div", "article", "li"]:
                    card = parent
                else:
                    break

            card_id = id(card)
            if card_id in processed_parents:
                continue
            processed_parents.add(card_id)

            # Extract company name - look for text content
            texts = []
            for el in card.find_all(["h2", "h3", "h4", "h5", "p", "span", "strong"]):
                text = el.get_text(strip=True)
                if text and len(text) > 2 and not text.startswith("http"):
                    texts.append(text)

            if not texts:
                # Get all text from card
                all_text = [t.strip() for t in card.stripped_strings if len(t.strip()) > 2]
                texts = all_text

            # First substantial text is usually the company name
            name = None
            country = None

            for text in texts:
                # Skip known non-company text
                if text.lower() in ["idef", "katılımcı", "exhibitor"]:
                    continue
                # Check if it's a country name
                if text in ["Türkiye", "Birleşik Arap Emirlikleri", "Germany", "USA",
                            "France", "United Kingdom", "Italy", "İtalya", "Almanya",
                            "Fransa", "İngiltere", "Güney Kore", "İsrael", "Pakistan",
                            "Azerbaycan", "Qatar", "Katar"]:
                    country = text
                    continue
                if not name:
                    name = text

            if name and len(name) > 2:
                # Extract logo
                logo = None
                img = card.find("img")
                if img and img.get("src"):
                    logo = img["src"]

                company = CompanyData(
                    name=name,
                    website=href,
                    country=country,
                    logo_url=logo,
                )
                companies.append(company)

        # Strategy 2: If Strategy 1 found nothing, try general text parsing
        if not companies:
            # Look for grid/list containers
            for container in soup.find_all("div", class_=re.compile(r"grid|list|flex", re.I)):
                cards = container.find_all("div", recursive=False)
                if len(cards) >= 3:
                    for card in cards:
                        texts = [t.strip() for t in card.stripped_strings if len(t.strip()) > 2]
                        if texts:
                            companies.append(CompanyData(name=texts[0]))

        return companies
