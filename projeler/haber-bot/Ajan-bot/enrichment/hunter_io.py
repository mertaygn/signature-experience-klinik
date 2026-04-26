"""
Hunter.io API Integration
Email finding and verification via Hunter.io API.
"""

import requests
import time
from typing import Optional
from rich.console import Console

import config

console = Console()

HUNTER_BASE_URL = "https://api.hunter.io/v2"


class HunterIO:
    """Hunter.io API client for email finding."""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or config.HUNTER_API_KEY
        self.session = requests.Session()
        self._remaining_requests = None

    @property
    def is_configured(self) -> bool:
        """Check if API key is set."""
        return bool(self.api_key) and self.api_key != "your_hunter_api_key_here"

    def get_account_info(self) -> Optional[dict]:
        """Get account information including remaining credits."""
        if not self.is_configured:
            return None
        try:
            response = self.session.get(
                f"{HUNTER_BASE_URL}/account",
                params={"api_key": self.api_key},
                timeout=10
            )
            response.raise_for_status()
            data = response.json().get("data", {})
            self._remaining_requests = data.get("requests", {}).get("searches", {}).get("available", 0)
            return data
        except requests.RequestException:
            return None

    def domain_search(self, domain: str, limit: int = 10) -> dict:
        """
        Search for email addresses associated with a domain.

        Returns dict with:
            emails: list of {value, type, confidence, first_name, last_name, position}
            organization: company name from Hunter
            pattern: email pattern (e.g., "{first}.{last}")
        """
        result = {
            "emails": [],
            "organization": None,
            "pattern": None,
        }

        if not self.is_configured:
            console.print("  [yellow]Hunter.io API key not configured.[/yellow]")
            return result

        try:
            response = self.session.get(
                f"{HUNTER_BASE_URL}/domain-search",
                params={
                    "domain": domain,
                    "api_key": self.api_key,
                    "limit": limit,
                },
                timeout=15,
            )
            response.raise_for_status()
            data = response.json().get("data", {})

            result["organization"] = data.get("organization")
            result["pattern"] = data.get("pattern")

            for email in data.get("emails", []):
                result["emails"].append({
                    "value": email.get("value"),
                    "type": email.get("type"),  # 'personal' or 'generic'
                    "confidence": email.get("confidence", 0),
                    "first_name": email.get("first_name"),
                    "last_name": email.get("last_name"),
                    "position": email.get("position"),
                    "department": email.get("department"),
                    "sources_count": email.get("sources_count", 0),
                })

            time.sleep(config.ENRICHMENT_DELAY)

        except requests.RequestException as e:
            console.print(f"  [red]Hunter.io error for {domain}: {e}[/red]")

        return result

    def email_finder(self, domain: str, first_name: str, last_name: str) -> Optional[dict]:
        """
        Find the email address of a specific person at a company.

        Returns dict with:
            email, confidence, score, position
        """
        if not self.is_configured:
            return None

        try:
            response = self.session.get(
                f"{HUNTER_BASE_URL}/email-finder",
                params={
                    "domain": domain,
                    "first_name": first_name,
                    "last_name": last_name,
                    "api_key": self.api_key,
                },
                timeout=15,
            )
            response.raise_for_status()
            data = response.json().get("data", {})

            if data.get("email"):
                time.sleep(config.ENRICHMENT_DELAY)
                return {
                    "email": data["email"],
                    "confidence": data.get("confidence", 0),
                    "score": data.get("score", 0),
                    "position": data.get("position"),
                    "first_name": first_name,
                    "last_name": last_name,
                }
        except requests.RequestException as e:
            console.print(f"  [red]Hunter.io email finder error: {e}[/red]")

        return None

    def verify_email(self, email: str) -> Optional[dict]:
        """
        Verify if an email address is valid.

        Returns dict with:
            status: 'valid', 'invalid', 'accept_all', 'webmail', 'disposable', 'unknown'
            score: 0-100
        """
        if not self.is_configured:
            return None

        try:
            response = self.session.get(
                f"{HUNTER_BASE_URL}/email-verifier",
                params={
                    "email": email,
                    "api_key": self.api_key,
                },
                timeout=15,
            )
            response.raise_for_status()
            data = response.json().get("data", {})

            time.sleep(config.ENRICHMENT_DELAY)
            return {
                "email": email,
                "status": data.get("status"),
                "score": data.get("score", 0),
                "regexp": data.get("regexp"),
                "smtp_server": data.get("smtp_server"),
                "smtp_check": data.get("smtp_check"),
            }
        except requests.RequestException as e:
            console.print(f"  [red]Hunter.io verify error: {e}[/red]")

        return None

    def get_remaining_credits(self) -> int:
        """Get the number of remaining search credits."""
        if self._remaining_requests is not None:
            return self._remaining_requests
        info = self.get_account_info()
        if info:
            return self._remaining_requests or 0
        return 0
