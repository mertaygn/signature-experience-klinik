"""
Enrichment Orchestrator
Combines web scraping and API sources to enrich company data with contacts.
"""

import re
import time
from urllib.parse import urlparse
from typing import Optional
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

import config
from database.db import Database
from enrichment.web_scraper import WebContactScraper
from enrichment.hunter_io import HunterIO

console = Console()


class Enricher:
    """Orchestrates contact enrichment from multiple sources."""

    def __init__(self, db: Database):
        self.db = db
        self.web_scraper = WebContactScraper()
        self.hunter = HunterIO()

    def enrich_company(self, company_id: int, use_hunter: bool = True) -> dict:
        """
        Enrich a single company with contact information.

        Returns summary of what was found.
        """
        company = self.db.get_company(company_id)
        if not company:
            return {"error": "Company not found"}

        name = company["name"]
        website = company["website"]
        domain = self._extract_domain(website)

        console.print(f"\n  [bold]Enriching: {name}[/bold]")
        if website:
            console.print(f"  [dim]Website: {website}[/dim]")

        found = {
            "emails": 0,
            "phones": 0,
            "social": 0,
            "people": 0,
        }

        # ─── Source 1: Company Website ────────────────────────
        if website:
            console.print("  [dim]→ Scraping company website...[/dim]")
            try:
                web_data = self.web_scraper.scrape_company(website)

                # Save emails
                for email in web_data.get("emails", []):
                    self.db.add_contact(
                        company_id=company_id,
                        contact_type="email",
                        value=email,
                        label=self._classify_email(email),
                        confidence=0.7,
                        source="website",
                    )
                    found["emails"] += 1

                # Save phones
                for phone in web_data.get("phones", []):
                    self.db.add_contact(
                        company_id=company_id,
                        contact_type="phone",
                        value=phone,
                        label="general",
                        confidence=0.7,
                        source="website",
                    )
                    found["phones"] += 1

                # Save social media
                for platform, url in web_data.get("social", {}).items():
                    self.db.add_contact(
                        company_id=company_id,
                        contact_type="social",
                        value=url,
                        label=platform,
                        confidence=0.9,
                        source="website",
                    )
                    found["social"] += 1

                # Save address
                if web_data.get("address"):
                    self.db.add_contact(
                        company_id=company_id,
                        contact_type="address",
                        value=web_data["address"],
                        label="headquarters",
                        confidence=0.6,
                        source="website",
                    )

                self.db.log_enrichment(
                    company_id, "website",
                    "success" if any(v > 0 for v in found.values()) else "no_data",
                    f"emails={found['emails']}, phones={found['phones']}"
                )

            except Exception as e:
                console.print(f"  [red]Web scraping error: {e}[/red]")
                self.db.log_enrichment(company_id, "website", "failed", str(e))

        # ─── Source 2: Hunter.io ──────────────────────────────
        if use_hunter and domain and self.hunter.is_configured:
            console.print("  [dim]→ Querying Hunter.io...[/dim]")
            try:
                hunter_data = self.hunter.domain_search(domain)

                for email_data in hunter_data.get("emails", []):
                    email = email_data.get("value")
                    if email:
                        label = "general"
                        if email_data.get("first_name"):
                            label = f"{email_data['first_name']} {email_data.get('last_name', '')}"
                            if email_data.get("position"):
                                label += f" ({email_data['position']})"

                            # Also save as person contact
                            person_name = f"{email_data['first_name']} {email_data.get('last_name', '')}".strip()
                            position = email_data.get("position", "")
                            self.db.add_contact(
                                company_id=company_id,
                                contact_type="person",
                                value=person_name,
                                label=position or email_data.get("department"),
                                confidence=email_data.get("confidence", 0) / 100,
                                source="hunter",
                            )
                            found["people"] += 1

                        self.db.add_contact(
                            company_id=company_id,
                            contact_type="email",
                            value=email,
                            label=label.strip(),
                            confidence=email_data.get("confidence", 0) / 100,
                            source="hunter",
                        )
                        found["emails"] += 1

                self.db.log_enrichment(
                    company_id, "hunter",
                    "success" if hunter_data["emails"] else "no_data",
                    f"Found {len(hunter_data['emails'])} emails"
                )

            except Exception as e:
                console.print(f"  [red]Hunter.io error: {e}[/red]")
                self.db.log_enrichment(company_id, "hunter", "failed", str(e))

        # Print summary
        total = sum(found.values())
        if total > 0:
            console.print(f"  [green]✓ Found: {found['emails']} emails, {found['phones']} phones, "
                          f"{found['people']} people, {found['social']} social[/green]")
        else:
            console.print(f"  [yellow]✗ No contact data found[/yellow]")

        return found

    def enrich_fair(self, fair_id: int, use_hunter: bool = True,
                    limit: int = None, skip_enriched: bool = True) -> dict:
        """
        Enrich all companies from a fair.

        Args:
            fair_id: ID of the fair
            use_hunter: Whether to use Hunter.io API
            limit: Maximum number of companies to enrich
            skip_enriched: Skip companies that were already enriched
        """
        if skip_enriched:
            companies = self.db.get_companies_without_contacts(fair_id)
        else:
            companies = self.db.get_companies_by_fair(fair_id)

        if limit:
            companies = companies[:limit]

        total_found = {"emails": 0, "phones": 0, "social": 0, "people": 0}
        total = len(companies)

        console.print(f"\n[bold blue]{'═' * 50}[/bold blue]")
        console.print(f"[bold]Enriching {total} companies...[/bold]")
        console.print(f"[bold blue]{'═' * 50}[/bold blue]")

        if use_hunter and self.hunter.is_configured:
            credits = self.hunter.get_remaining_credits()
            console.print(f"[dim]Hunter.io credits remaining: {credits}[/dim]")
            if credits < total:
                console.print(f"[yellow]⚠ Not enough Hunter.io credits for all companies. "
                              f"Will use web scraping for the rest.[/yellow]")

        for i, company in enumerate(companies, 1):
            console.print(f"\n[dim]── [{i}/{total}] ──[/dim]")

            # Check Hunter credits
            use_hunter_for_this = use_hunter
            if use_hunter and self.hunter.is_configured:
                if self.hunter._remaining_requests is not None and self.hunter._remaining_requests <= 0:
                    use_hunter_for_this = False

            found = self.enrich_company(company["id"], use_hunter=use_hunter_for_this)

            for key in total_found:
                total_found[key] += found.get(key, 0)

            # Respect rate limits
            time.sleep(config.REQUEST_DELAY)

        # Print final summary
        console.print(f"\n[bold green]{'═' * 50}[/bold green]")
        console.print(f"[bold]Enrichment Complete![/bold]")
        console.print(f"[bold green]{'═' * 50}[/bold green]")
        console.print(f"  Companies processed: [bold]{total}[/bold]")
        console.print(f"  Emails found:        [bold cyan]{total_found['emails']}[/bold cyan]")
        console.print(f"  Phones found:        [bold cyan]{total_found['phones']}[/bold cyan]")
        console.print(f"  People found:        [bold cyan]{total_found['people']}[/bold cyan]")
        console.print(f"  Social links found:  [bold cyan]{total_found['social']}[/bold cyan]")

        return total_found

    def _extract_domain(self, url: str) -> Optional[str]:
        """Extract clean domain from URL."""
        if not url:
            return None
        try:
            parsed = urlparse(url if url.startswith("http") else f"https://{url}")
            domain = parsed.netloc.replace("www.", "")
            return domain if domain else None
        except Exception:
            return None

    def _classify_email(self, email: str) -> str:
        """Classify an email as general, sales, support, etc."""
        local_part = email.split("@")[0].lower()
        if local_part in ["info", "bilgi"]:
            return "general"
        elif local_part in ["sales", "satis", "satış", "ticaret"]:
            return "sales"
        elif local_part in ["support", "destek", "help"]:
            return "support"
        elif local_part in ["hr", "ik", "kariyer", "career"]:
            return "hr"
        elif local_part in ["marketing", "pazarlama"]:
            return "marketing"
        else:
            return "general"
