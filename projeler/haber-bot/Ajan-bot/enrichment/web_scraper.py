"""
Web Contact Scraper
Scrapes company websites to find contact information (emails, phones, addresses).
"""

import re
import time
import requests
from typing import Optional
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from rich.console import Console

import config

console = Console()

# ─── Regex Patterns ───────────────────────────────────────────
EMAIL_REGEX = re.compile(
    r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
    re.IGNORECASE
)

PHONE_REGEX = re.compile(
    r'(?:\+90|0090|0)?\s*(?:\(?\d{3}\)?\s*[\s.-]?\s*\d{3}\s*[\s.-]?\s*\d{2}\s*[\s.-]?\s*\d{2})',
    re.IGNORECASE
)

# International phone format
PHONE_INTL_REGEX = re.compile(
    r'\+?\d{1,4}[\s.-]?\(?\d{1,5}\)?[\s.-]?\d{2,4}[\s.-]?\d{2,4}[\s.-]?\d{0,4}',
)

# Social media patterns
LINKEDIN_REGEX = re.compile(r'https?://(?:www\.)?linkedin\.com/(?:company|in)/[a-zA-Z0-9_-]+/?', re.I)
TWITTER_REGEX = re.compile(r'https?://(?:www\.)?(?:twitter|x)\.com/[a-zA-Z0-9_]+/?', re.I)
INSTAGRAM_REGEX = re.compile(r'https?://(?:www\.)?instagram\.com/[a-zA-Z0-9_.]+/?', re.I)

# ─── Blacklisted email domains ───────────────────────────────
BLACKLISTED_DOMAINS = {
    "example.com", "test.com", "sentry.io", "w3.org",
    "googleapis.com", "google.com", "facebook.com",
    "twitter.com", "instagram.com", "youtube.com",
    "schema.org", "wixpress.com", "cloudflare.com",
    "jquery.com", "bootstrapcdn.com", "fontawesome.com",
}


class WebContactScraper:
    """Scrapes company websites for contact information."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": config.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        })

    def scrape_company(self, website: str) -> dict:
        """
        Scrape a company website for contact information.

        Returns dict with keys:
            emails: list of found emails
            phones: list of found phones
            social: dict of social media links
            address: extracted address text
            people: list of found person names/titles
        """
        result = {
            "emails": [],
            "phones": [],
            "social": {},
            "address": None,
            "people": [],
        }

        if not website:
            return result

        # Normalize URL
        if not website.startswith(("http://", "https://")):
            website = "https://" + website

        domain = urlparse(website).netloc.replace("www.", "")

        # Step 1: Scrape homepage
        homepage_data = self._scrape_page(website)
        self._merge_results(result, homepage_data)

        # Step 2: Find and scrape contact page
        contact_url = self._find_contact_page(website)
        if contact_url:
            contact_data = self._scrape_page(contact_url)
            self._merge_results(result, contact_data)

        # Step 3: Try /about or /hakkimizda pages for people
        about_url = self._find_about_page(website)
        if about_url:
            about_data = self._scrape_page(about_url)
            self._merge_results(result, about_data)

        # Filter out junk emails
        result["emails"] = self._filter_emails(result["emails"], domain)

        # Deduplicate
        result["emails"] = list(dict.fromkeys(result["emails"]))
        result["phones"] = list(dict.fromkeys(result["phones"]))

        return result

    def _scrape_page(self, url: str) -> dict:
        """Scrape a single page for contact info."""
        data = {
            "emails": [],
            "phones": [],
            "social": {},
            "address": None,
            "people": [],
        }

        try:
            response = self.session.get(url, timeout=config.REQUEST_TIMEOUT, allow_redirects=True)
            response.raise_for_status()
            time.sleep(1)  # Be polite
        except requests.RequestException:
            return data

        html = response.text
        soup = BeautifulSoup(html, "lxml")

        # Remove script and style tags
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        text = soup.get_text(" ", strip=True)

        # Extract emails
        emails = EMAIL_REGEX.findall(text)
        # Also check href="mailto:" links
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if href.startswith("mailto:"):
                email = href.replace("mailto:", "").split("?")[0].strip()
                if email:
                    emails.append(email)
        data["emails"] = [e.lower() for e in emails]

        # Extract phones
        phones = PHONE_REGEX.findall(text)
        # Also check href="tel:" links
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if href.startswith("tel:"):
                phone = href.replace("tel:", "").strip()
                if phone:
                    phones.append(phone)
        # Also try international format
        phones += PHONE_INTL_REGEX.findall(text)
        data["phones"] = [self._clean_phone(p) for p in phones if self._is_valid_phone(p)]

        # Extract social media
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if LINKEDIN_REGEX.match(href):
                data["social"]["linkedin"] = href
            elif TWITTER_REGEX.match(href):
                data["social"]["twitter"] = href
            elif INSTAGRAM_REGEX.match(href):
                data["social"]["instagram"] = href

        # Try to extract address
        address = self._extract_address(soup)
        if address:
            data["address"] = address

        return data

    def _find_contact_page(self, base_url: str) -> Optional[str]:
        """Try to find the contact page of a website."""
        # Try common contact page paths
        contact_paths = []
        for lang, keywords in config.CONTACT_PAGE_KEYWORDS.items():
            for kw in keywords:
                contact_paths.append(f"/{kw}")
                contact_paths.append(f"/{kw}/")
                contact_paths.append(f"/{kw}.html")

        for path in contact_paths:
            url = urljoin(base_url, path)
            try:
                response = self.session.head(url, timeout=10, allow_redirects=True)
                if response.status_code == 200:
                    return url
            except requests.RequestException:
                continue

        # Fallback: look for contact links on homepage
        try:
            response = self.session.get(base_url, timeout=config.REQUEST_TIMEOUT)
            soup = BeautifulSoup(response.text, "lxml")
            for link in soup.find_all("a", href=True):
                href = link["href"].lower()
                text = link.get_text(strip=True).lower()
                if any(kw in href or kw in text for kw in ["contact", "iletisim", "iletişim", "kontak"]):
                    return urljoin(base_url, link["href"])
        except requests.RequestException:
            pass

        return None

    def _find_about_page(self, base_url: str) -> Optional[str]:
        """Try to find the about page."""
        about_paths = ["/about", "/about-us", "/hakkimizda", "/hakkımızda", "/kurumsal"]
        for path in about_paths:
            url = urljoin(base_url, path)
            try:
                response = self.session.head(url, timeout=10, allow_redirects=True)
                if response.status_code == 200:
                    return url
            except requests.RequestException:
                continue
        return None

    def _extract_address(self, soup) -> Optional[str]:
        """Try to extract physical address from page."""
        # Look for address tag
        address_el = soup.find("address")
        if address_el:
            return address_el.get_text(strip=True)

        # Look for elements with address-related classes/ids
        for selector in [
            {"class_": re.compile(r"address|adres|location|konum", re.I)},
            {"id": re.compile(r"address|adres|location|konum", re.I)},
        ]:
            el = soup.find(["div", "p", "span"], **selector)
            if el:
                text = el.get_text(strip=True)
                if text and 10 < len(text) < 300:
                    return text

        return None

    def _filter_emails(self, emails: list, company_domain: str) -> list:
        """Filter out junk/irrelevant emails."""
        filtered = []
        for email in emails:
            email = email.lower().strip()
            # Skip blacklisted domains
            email_domain = email.split("@")[-1]
            if email_domain in BLACKLISTED_DOMAINS:
                continue
            # Skip image file extensions mistakenly caught
            if any(email.endswith(ext) for ext in [".png", ".jpg", ".gif", ".svg", ".webp"]):
                continue
            # Skip very long emails
            if len(email) > 60:
                continue
            filtered.append(email)
        return filtered

    def _is_valid_phone(self, phone: str) -> bool:
        """Check if extracted phone is valid."""
        digits = re.sub(r'\D', '', phone)
        return 7 <= len(digits) <= 15

    def _clean_phone(self, phone: str) -> str:
        """Clean and normalize phone number."""
        phone = phone.strip()
        # Remove extra whitespace
        phone = re.sub(r'\s+', ' ', phone)
        return phone

    def _merge_results(self, target: dict, source: dict):
        """Merge source contact data into target."""
        target["emails"].extend(source.get("emails", []))
        target["phones"].extend(source.get("phones", []))
        target["social"].update(source.get("social", {}))
        if source.get("address") and not target.get("address"):
            target["address"] = source["address"]
        target["people"].extend(source.get("people", []))
