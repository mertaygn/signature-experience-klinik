"""
Ajan-Bot Database Manager
SQLite database for storing fair, company, and contact data.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional
import config


class Database:
    """SQLite database manager for Ajan-Bot."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or config.DB_PATH
        self.conn = None
        self._connect()
        self._create_tables()

    def _connect(self):
        """Connect to SQLite database."""
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")

    def _create_tables(self):
        """Create database tables if they don't exist."""
        self.conn.executescript("""
            -- Fairs table
            CREATE TABLE IF NOT EXISTS fairs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                url TEXT,
                location TEXT,
                start_date TEXT,
                end_date TEXT,
                description TEXT,
                scraped_at TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            -- Companies table
            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fair_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                website TEXT,
                booth_number TEXT,
                sector TEXT,
                country TEXT,
                city TEXT,
                description TEXT,
                logo_url TEXT,
                raw_data TEXT,
                scraped_at TEXT DEFAULT (datetime('now')),
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (fair_id) REFERENCES fairs(id),
                UNIQUE(fair_id, name)
            );

            -- Contacts table (enriched data)
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                contact_type TEXT NOT NULL,  -- 'email', 'phone', 'person', 'social'
                value TEXT NOT NULL,
                label TEXT,                  -- 'general', 'sales', 'ceo', 'linkedin', etc.
                confidence REAL DEFAULT 0.0, -- 0.0 to 1.0
                source TEXT,                 -- 'website', 'hunter', 'apollo', 'manual'
                verified INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (company_id) REFERENCES companies(id),
                UNIQUE(company_id, contact_type, value)
            );

            -- Enrichment log
            CREATE TABLE IF NOT EXISTS enrichment_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                source TEXT NOT NULL,
                status TEXT NOT NULL,  -- 'success', 'failed', 'no_data'
                details TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (company_id) REFERENCES companies(id)
            );

            -- Indexes
            CREATE INDEX IF NOT EXISTS idx_companies_fair ON companies(fair_id);
            CREATE INDEX IF NOT EXISTS idx_contacts_company ON contacts(company_id);
            CREATE INDEX IF NOT EXISTS idx_contacts_type ON contacts(contact_type);
            CREATE INDEX IF NOT EXISTS idx_enrichment_company ON enrichment_log(company_id);
        """)
        
        # Add new columns if they don't exist (safe migration)
        for col in ["email", "phone", "address"]:
            try:
                self.conn.execute(f"ALTER TABLE companies ADD COLUMN {col} TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists
        
        self.conn.commit()

    # ─── Fair Operations ──────────────────────────────────────

    def upsert_fair(self, slug: str, name: str, url: str = None,
                    location: str = None, start_date: str = None,
                    end_date: str = None, description: str = None) -> int:
        """Insert or update a fair. Returns fair ID."""
        cursor = self.conn.execute("""
            INSERT INTO fairs (slug, name, url, location, start_date, end_date, description, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(slug) DO UPDATE SET
                name=excluded.name, url=excluded.url, location=excluded.location,
                start_date=excluded.start_date, end_date=excluded.end_date,
                description=excluded.description, scraped_at=datetime('now')
            RETURNING id
        """, (slug, name, url, location, start_date, end_date, description))
        fair_id = cursor.fetchone()[0]
        self.conn.commit()
        return fair_id

    def get_fair(self, slug: str) -> Optional[dict]:
        """Get a fair by slug."""
        row = self.conn.execute(
            "SELECT * FROM fairs WHERE slug = ?", (slug,)
        ).fetchone()
        return dict(row) if row else None

    def get_all_fairs(self) -> list:
        """Get all fairs."""
        rows = self.conn.execute("SELECT * FROM fairs ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

    # ─── Company Operations ───────────────────────────────────

    def upsert_company(self, fair_id: int, name: str, website: str = None,
                       booth_number: str = None, sector: str = None,
                       country: str = None, city: str = None,
                       description: str = None, logo_url: str = None,
                       raw_data: dict = None, email: str = None,
                       phone: str = None, address: str = None) -> int:
        """Insert or update a company. Returns company ID."""
        raw_json = json.dumps(raw_data, ensure_ascii=False) if raw_data else None
        cursor = self.conn.execute("""
            INSERT INTO companies (fair_id, name, website, booth_number, sector, country, city, description, logo_url, raw_data, email, phone, address)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(fair_id, name) DO UPDATE SET
                website=COALESCE(excluded.website, companies.website),
                booth_number=COALESCE(excluded.booth_number, companies.booth_number),
                sector=COALESCE(excluded.sector, companies.sector),
                country=COALESCE(excluded.country, companies.country),
                city=COALESCE(excluded.city, companies.city),
                description=COALESCE(excluded.description, companies.description),
                logo_url=COALESCE(excluded.logo_url, companies.logo_url),
                raw_data=COALESCE(excluded.raw_data, companies.raw_data),
                email=COALESCE(excluded.email, companies.email),
                phone=COALESCE(excluded.phone, companies.phone),
                address=COALESCE(excluded.address, companies.address),
                scraped_at=datetime('now')
            RETURNING id
        """, (fair_id, name, website, booth_number, sector, country, city,
              description, logo_url, raw_json, email, phone, address))
        company_id = cursor.fetchone()[0]
        self.conn.commit()
        return company_id

    def get_companies_by_fair(self, fair_id: int) -> list:
        """Get all companies for a fair."""
        rows = self.conn.execute(
            "SELECT * FROM companies WHERE fair_id = ? ORDER BY name", (fair_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_company(self, company_id: int) -> Optional[dict]:
        """Get a company by ID."""
        row = self.conn.execute(
            "SELECT * FROM companies WHERE id = ?", (company_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_companies_without_contacts(self, fair_id: int) -> list:
        """Get companies that haven't been enriched yet."""
        rows = self.conn.execute("""
            SELECT c.* FROM companies c
            LEFT JOIN enrichment_log e ON c.id = e.company_id
            WHERE c.fair_id = ? AND e.id IS NULL
            ORDER BY c.name
        """, (fair_id,)).fetchall()
        return [dict(r) for r in rows]

    def search_companies(self, query: str) -> list:
        """Search companies by name."""
        rows = self.conn.execute(
            "SELECT c.*, f.name as fair_name FROM companies c JOIN fairs f ON c.fair_id = f.id WHERE c.name LIKE ? ORDER BY c.name",
            (f"%{query}%",)
        ).fetchall()
        return [dict(r) for r in rows]

    # ─── Contact Operations ───────────────────────────────────

    def add_contact(self, company_id: int, contact_type: str, value: str,
                    label: str = None, confidence: float = 0.0,
                    source: str = None, verified: bool = False) -> Optional[int]:
        """Add a contact for a company. Returns contact ID or None if duplicate."""
        try:
            cursor = self.conn.execute("""
                INSERT INTO contacts (company_id, contact_type, value, label, confidence, source, verified)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(company_id, contact_type, value) DO UPDATE SET
                    label=COALESCE(excluded.label, contacts.label),
                    confidence=MAX(excluded.confidence, contacts.confidence),
                    source=COALESCE(excluded.source, contacts.source),
                    verified=MAX(excluded.verified, contacts.verified)
                RETURNING id
            """, (company_id, contact_type, value, label, confidence, source, int(verified)))
            contact_id = cursor.fetchone()[0]
            self.conn.commit()
            return contact_id
        except Exception:
            return None

    def get_contacts_by_company(self, company_id: int) -> list:
        """Get all contacts for a company."""
        rows = self.conn.execute(
            "SELECT * FROM contacts WHERE company_id = ? ORDER BY contact_type, confidence DESC",
            (company_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_all_enriched_data(self, fair_id: int) -> list:
        """Get all companies with their contacts for a fair."""
        companies = self.get_companies_by_fair(fair_id)
        for company in companies:
            company["contacts"] = self.get_contacts_by_company(company["id"])
        return companies

    # ─── Enrichment Log ───────────────────────────────────────

    def log_enrichment(self, company_id: int, source: str, status: str, details: str = None):
        """Log an enrichment attempt."""
        self.conn.execute("""
            INSERT INTO enrichment_log (company_id, source, status, details)
            VALUES (?, ?, ?, ?)
        """, (company_id, source, status, details))
        self.conn.commit()

    # ─── Statistics ───────────────────────────────────────────

    def get_stats(self, fair_id: int = None) -> dict:
        """Get database statistics."""
        if fair_id:
            total_companies = self.conn.execute(
                "SELECT COUNT(*) FROM companies WHERE fair_id = ?", (fair_id,)
            ).fetchone()[0]
            with_email = self.conn.execute("""
                SELECT COUNT(DISTINCT c.id) FROM companies c
                JOIN contacts ct ON c.id = ct.company_id
                WHERE c.fair_id = ? AND ct.contact_type = 'email'
            """, (fair_id,)).fetchone()[0]
            with_phone = self.conn.execute("""
                SELECT COUNT(DISTINCT c.id) FROM companies c
                JOIN contacts ct ON c.id = ct.company_id
                WHERE c.fair_id = ? AND ct.contact_type = 'phone'
            """, (fair_id,)).fetchone()[0]
            enriched = self.conn.execute("""
                SELECT COUNT(DISTINCT company_id) FROM enrichment_log
                WHERE company_id IN (SELECT id FROM companies WHERE fair_id = ?)
            """, (fair_id,)).fetchone()[0]
        else:
            total_companies = self.conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
            with_email = self.conn.execute("""
                SELECT COUNT(DISTINCT company_id) FROM contacts WHERE contact_type = 'email'
            """).fetchone()[0]
            with_phone = self.conn.execute("""
                SELECT COUNT(DISTINCT company_id) FROM contacts WHERE contact_type = 'phone'
            """).fetchone()[0]
            enriched = self.conn.execute(
                "SELECT COUNT(DISTINCT company_id) FROM enrichment_log"
            ).fetchone()[0]

        return {
            "total_companies": total_companies,
            "with_email": with_email,
            "with_phone": with_phone,
            "enriched": enriched,
            "total_fairs": self.conn.execute("SELECT COUNT(*) FROM fairs").fetchone()[0],
            "total_contacts": self.conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0],
        }

    # ─── Cleanup ──────────────────────────────────────────────

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
