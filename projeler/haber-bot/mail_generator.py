#!/usr/bin/env python3
"""
WOC Brussels 2026 — Kişiselleştirilmiş Mail Üretici
Evreka Stand için exhibitor outreach mailleri oluşturur.

Kullanım:
    python mail_generator.py --preview          # İlk 5 maili önizle
    python mail_generator.py --export           # CSV olarak dışa aktar
    python mail_generator.py --priority high    # Sadece yüksek öncelikli firmalar
"""

import sqlite3
import csv
import argparse
from datetime import datetime

# ─── KONFİGÜRASYON ─────────────────────────────────────────
SENDER_NAME = "Evreka Stand Team"          # ← Buraya kendi adını yaz
SENDER_EMAIL = "info@evrekastand.com"       # ← Buraya kendi mail adresini yaz
SENDER_PHONE = "+90 xxx xxx xx xx"          # ← Telefon numarası
WEBSITE = "evrekastand.com"                 # ← Website
PORTFOLIO_URL = "evrekastand.com/portfolio" # ← Portfolyo linki

DB_PATH = "data/exhibitor_leads.db"
FAIR_SLUG = "world_of_coffee_brussels_2026"

# ─── SEKTÖR KATEGORİZASYONU ────────────────────────────────
SECTOR_KEYWORDS = {
    'equipment': ['machine', 'grinder', 'roaster', 'filter', 'press', 'tech',
                  'robot', 'system', 'appliance', 'engineering', 'espresso'],
    'roaster': ['roast', 'café', 'cafe', 'barista', 'brew', 'beans', 'roastery',
                'kaffee', 'coffee house', 'kavurucu'],
    'packaging': ['pack', 'bag', 'label', 'box', 'pouch', 'container', 'seal',
                  'dry-bag', 'logistics', 'freight'],
    'green_coffee': ['trading', 'import', 'export', 'commodity', 'green', 'farm',
                     'finca', 'hacienda', 'origin', 'sourc', 'trader'],
}

def categorize(name):
    nl = name.lower()
    for sector, keywords in SECTOR_KEYWORDS.items():
        if any(k in nl for k in keywords):
            return sector
    return 'other'

# ─── SEKTÖRE GÖRE AÇILIŞ CÜMLELERİ ────────────────────────
SECTOR_OPENERS = {
    'equipment': (
        "Showcasing coffee machines and equipment at a trade fair demands a stand "
        "that matches the quality and precision of your products."
    ),
    'roaster': (
        "As a specialty coffee brand, your story deserves a booth that brings it "
        "to life — from the aroma to the aesthetics."
    ),
    'packaging': (
        "Packaging is all about first impressions — and so is your exhibition stand. "
        "Let's make sure both are unforgettable."
    ),
    'green_coffee': (
        "Green coffee traders need functional meeting spaces that also reflect "
        "professionalism and trust — we can deliver exactly that."
    ),
    'other': (
        "Standing out at World of Coffee requires more than a great product — "
        "it requires a booth that stops people in their tracks."
    ),
}

# ─── ÖNCELİK SEVİYESİ ──────────────────────────────────────
def get_priority(name, sector):
    """Firma büyüklüğü ve sektöre göre öncelik belirle."""
    high_value = [
        'probat', 'dalla corte', 'la marzocco', 'victoria arduino', 'giesen',
        'bühler', 'neuhaus', 'sanremo', 'astoria', 'wega', 'lelit', 'cime',
        'loring', 'brambati', 'pinhalense', 'opem', 'goglio', 'ica spa',
        'swiss pac', 'brita', 'scotsman', 'pentair', 'hario', 'fellow',
        'timemore', 'comandante', 'stronghold', 'ikawa', 'marco',
    ]
    nl = name.lower()
    if any(hv in nl for hv in high_value):
        return 'high'
    if sector in ('equipment', 'packaging'):
        return 'medium'
    return 'standard'

# ─── MAİL TEMPLATE ──────────────────────────────────────────
def generate_email(company_name, email, sector, priority):
    """Kişiselleştirilmiş mail içeriği üret."""
    
    opener = SECTOR_OPENERS.get(sector, SECTOR_OPENERS['other'])
    
    subject = f"Your stand at WOC Brussels — let's make it unforgettable"
    
    body = f"""Hi {company_name} Team,

I noticed that {company_name} will be exhibiting at World of Coffee Brussels this June — congratulations on being part of such an exciting event!

{opener}

I'm reaching out from Evreka Stand, a Turkey-based exhibition stand design and build company. We specialize in creating custom stands for international trade fairs across Europe, including food & beverage events.

Here's what we can offer for WOC Brussels:

  ✅ Custom stand design tailored to your brand
  ✅ Full turnkey build & installation in Brussels
  ✅ On-site project management — you just show up
  ✅ Competitive pricing with early-booking advantage

We've worked with exhibitors at HOST Milano, Anuga, and SIAL — so we know exactly what it takes to stand out in a crowded expo hall.

Would you be open to a quick 15-minute call to discuss your stand needs? I'd be happy to share some design concepts — no obligation.

Best regards,
{SENDER_NAME}
Evreka Stand
📞 {SENDER_PHONE}
🌐 {WEBSITE}

---
You received this email because {company_name} is listed as an exhibitor at WOC Brussels 2026.
If you'd prefer not to hear from us, simply reply with "unsubscribe"."""

    return {
        'company': company_name,
        'email': email,
        'subject': subject,
        'body': body,
        'sector': sector,
        'priority': priority,
    }


def main():
    parser = argparse.ArgumentParser(description='WOC Brussels 2026 Mail Generator')
    parser.add_argument('--preview', action='store_true', help='İlk 5 maili önizle')
    parser.add_argument('--export', action='store_true', help='CSV olarak dışa aktar')
    parser.add_argument('--priority', choices=['high','medium','standard','all'], 
                       default='all', help='Öncelik filtresi')
    args = parser.parse_args()
    
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT company_name, email, website FROM exhibitor_leads 
        WHERE fair_slug=? AND email IS NOT NULL AND email!=''
        ORDER BY company_name
    """, (FAIR_SLUG,)).fetchall()
    conn.close()
    
    # Mailleri üret
    mails = []
    for name, email, website in rows:
        sector = categorize(name)
        priority = get_priority(name, sector)
        
        if args.priority != 'all' and priority != args.priority:
            continue
        
        mail = generate_email(name, email, sector, priority)
        mails.append(mail)
    
    # İstatistik
    priorities = {}
    for m in mails:
        priorities[m['priority']] = priorities.get(m['priority'], 0) + 1
    
    print(f"\n📊 WOC Brussels 2026 — Mail Üretici")
    print(f"{'='*50}")
    print(f"  Toplam mail: {len(mails)}")
    for p in ['high', 'medium', 'standard']:
        print(f"  {p:10s}: {priorities.get(p, 0)}")
    print()
    
    # Önizleme
    if args.preview:
        for i, m in enumerate(mails[:5]):
            print(f"\n{'─'*60}")
            print(f"📧 #{i+1} | {m['priority'].upper()} | {m['sector']}")
            print(f"To: {m['email']}")
            print(f"Subject: {m['subject']}")
            print(f"{'─'*60}")
            print(m['body'][:500] + "...")
            print()
    
    # CSV Export
    if args.export:
        out = f"data/woc_outreach_{datetime.now().strftime('%Y%m%d')}.csv"
        with open(out, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['company','email','subject','body','sector','priority'])
            writer.writeheader()
            writer.writerows(mails)
        print(f"✅ {len(mails)} mail → {out}")


if __name__ == '__main__':
    main()
