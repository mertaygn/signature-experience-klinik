#!/usr/bin/env python3
"""
WOC Brussels 2026 — SMTP Mail Gönderici
Evreka Stand outreach mailleri için.

Kurulum:
    .env dosyasına ekle:
        SMTP_HOST=mail.evrekastand.com
        SMTP_PORT=587
        SMTP_USER=info@evrekastand.com
        SMTP_PASS=şifren

Kullanım:
    python woc_mailer.py --test              # Kendine test maili gönder
    python woc_mailer.py --preview 5         # İlk 5 maili önizle
    python woc_mailer.py --send --limit 10   # 10 mail gönder
    python woc_mailer.py --send --priority high  # Sadece HIGH öncelikli
    python woc_mailer.py --status            # Gönderim durumu
"""

import sqlite3
import smtplib
import time
import json
import argparse
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ─── SMTP KONFİGÜRASYON ────────────────────────────────────

SMTP_HOST = os.getenv("SMTP_HOST", "mail.evrekastand.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "info@evrekastand.com")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SENDER_NAME = "Evreka Stand"
SENDER_EMAIL = SMTP_USER

DB_PATH = "data/exhibitor_leads.db"
FAIR_SLUG = "world_of_coffee_brussels_2026"
SENT_LOG = "data/woc_sent_log.json"

# Gönderim hız limitleri
DELAY_BETWEEN_EMAILS = 300  # Her mail arası 5 dakika
DAILY_LIMIT = 65             # Günlük max
BATCH_LIMIT = 10             # Tek seferde max

# ─── MAİL İÇERİĞİ ──────────────────────────────────────────

SUBJECT = "World of Coffee Brussels — quick question"

BODY_PLAIN = """Hi,

I'm reaching out to see whether your team has already confirmed a stand partner for World of Coffee Brussels (25–27 June).

We're Evreka Stand — an exhibition stand contractor delivering turnkey projects across 28+ countries, from design and production through to on-site installation.

We've previously delivered stand projects within the World of Coffee ecosystem. We also built and delivered Porland's stand at Ambiente Frankfurt and FHA HoReCa Singapore. Our team has recently completed projects in Switzerland, and we'll also be active in Thailand later this year.

Here are a few relevant projects:

→ Porland | Ambiente 2025
  https://www.evrekastand.com/work/porland-ambiente-2025

→ Porland | FHA HoReCa Singapore
  https://www.evrekastand.com/work/porland-fha-horeca

→ Rioba | Istanbul Coffee Festival
  https://www.evrekastand.com/work/rioba-istanbul-coffee-festival

→ Full portfolio
  https://www.evrekastand.com/work

If your booth partner is not yet confirmed, we'd love to set up a brief call with our project team to understand your vision for Brussels and share some initial ideas.

You can book a time here: https://www.evrekastand.com/contact
Or simply reply to this email — we'll get back to you within one business day.

Best regards,
Evreka Stand Team
https://www.evrekastand.com"""

BODY_HTML = """<div style="font-family: Arial, sans-serif; font-size: 14px; color: #333; line-height: 1.6;">

<p>Hi,</p>

<p>I'm reaching out to see whether your team has already confirmed a stand partner for <strong>World of Coffee Brussels</strong> (25–27 June).</p>

<p>We're <strong>Evreka Stand</strong> — an exhibition stand contractor delivering turnkey projects across 28+ countries, from design and production through to on-site installation.</p>

<p>We've previously delivered stand projects within the World of Coffee ecosystem. We also built and delivered <strong>Porland's stand</strong> at Ambiente Frankfurt and FHA HoReCa Singapore. Our team has recently completed projects in Switzerland, and we'll also be active in Thailand later this year.</p>

<p>Here are a few relevant projects:</p>

<ul style="list-style: none; padding-left: 0;">
<li>→ <a href="https://www.evrekastand.com/work/porland-ambiente-2025" style="color: #1a73e8;">Porland | Ambiente 2025</a></li>
<li>→ <a href="https://www.evrekastand.com/work/porland-fha-horeca" style="color: #1a73e8;">Porland | FHA HoReCa Singapore</a></li>
<li>→ <a href="https://www.evrekastand.com/work/rioba-istanbul-coffee-festival" style="color: #1a73e8;">Rioba | Istanbul Coffee Festival</a></li>
<li>→ <a href="https://www.evrekastand.com/work" style="color: #1a73e8;">Full portfolio</a></li>
</ul>

<p>If your booth partner is not yet confirmed, we'd love to set up a brief call with our project team to understand your vision for Brussels and share some initial ideas.</p>

<p>
<a href="https://www.evrekastand.com/contact" style="color: #1a73e8;">Book a time here</a> · Or simply reply to this email — we'll get back to you within one business day.
</p>

<p style="margin-top: 24px;">
Best regards,<br>
<strong>Evreka Stand Team</strong><br>
<a href="https://www.evrekastand.com" style="color: #1a73e8;">evrekastand.com</a>
</p>

</div>"""

# ─── ÖNCELİK SİSTEMİ ───────────────────────────────────────

SECTOR_KEYWORDS = {
    'equipment': ['machine', 'grinder', 'roaster', 'filter', 'press', 'tech',
                  'robot', 'system', 'appliance', 'engineering', 'espresso'],
    'roaster': ['roast', 'café', 'cafe', 'barista', 'brew', 'beans', 'roastery'],
    'packaging': ['pack', 'bag', 'label', 'box', 'pouch', 'container', 'seal'],
    'green_coffee': ['trading', 'import', 'export', 'commodity', 'green', 'farm',
                     'finca', 'hacienda', 'origin', 'sourc', 'trader'],
}

HIGH_VALUE = [
    'probat', 'dalla corte', 'la marzocco', 'victoria arduino', 'giesen',
    'neuhaus', 'sanremo', 'astoria', 'wega', 'lelit', 'loring', 'opem',
    'swiss pac', 'brita', 'scotsman', 'hario', 'fellow', 'timemore',
    'comandante', 'stronghold', 'ikawa', 'marco', 'bialetti', 'ditting',
]

def categorize(name):
    nl = name.lower()
    for sector, kws in SECTOR_KEYWORDS.items():
        if any(k in nl for k in kws):
            return sector
    return 'other'

def get_priority(name, sector):
    nl = name.lower()
    if any(hv in nl for hv in HIGH_VALUE):
        return 'high'
    if sector in ('equipment', 'packaging'):
        return 'medium'
    return 'standard'

# ─── SENT LOG ───────────────────────────────────────────────

def load_sent_log():
    if os.path.exists(SENT_LOG):
        with open(SENT_LOG, 'r') as f:
            return json.load(f)
    return {}

def save_sent_log(log):
    os.makedirs(os.path.dirname(SENT_LOG), exist_ok=True)
    with open(SENT_LOG, 'w') as f:
        json.dump(log, f, indent=2, ensure_ascii=False)

# ─── SMTP GÖNDERIM ─────────────────────────────────────────

def send_email(to_email):
    """SMTP ile tek bir mail gönder."""
    msg = MIMEMultipart('alternative')
    msg['From'] = f"{SENDER_NAME} <{SENDER_EMAIL}>"
    msg['To'] = to_email
    msg['Subject'] = SUBJECT
    msg['Reply-To'] = SENDER_EMAIL

    # Plain text + HTML (mail client'ı uygun olanı gösterir)
    msg.attach(MIMEText(BODY_PLAIN, 'plain', 'utf-8'))
    msg.attach(MIMEText(BODY_HTML, 'html', 'utf-8'))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)

    return True

# ─── LEAD YÜKLEME ──────────────────────────────────────────

def load_leads(priority_filter='all'):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT id, company_name, email, website FROM exhibitor_leads 
        WHERE fair_slug=? AND email IS NOT NULL AND email!=''
        ORDER BY company_name
    """, (FAIR_SLUG,)).fetchall()
    conn.close()

    sent_log = load_sent_log()
    leads = []

    for row_id, name, email, website in rows:
        sector = categorize(name)
        priority = get_priority(name, sector)

        if priority_filter != 'all' and priority != priority_filter:
            continue

        leads.append({
            'id': row_id,
            'company': name,
            'email': email,
            'sector': sector,
            'priority': priority,
            'sent': email in sent_log,
        })

    return leads

# ─── KOMUTLAR ───────────────────────────────────────────────

def cmd_test():
    """Kendine test maili gönder."""
    if not SMTP_PASS:
        print("❌ SMTP_PASS .env dosyasında tanımlı değil!")
        return

    print(f"📧 Test maili gönderiliyor → {SENDER_EMAIL}")
    try:
        send_email(SENDER_EMAIL)
        print("✅ Test maili gönderildi! Gelen kutunu kontrol et.")
    except Exception as e:
        print(f"❌ HATA: {e}")

def cmd_preview(count, priority):
    leads = [l for l in load_leads(priority) if not l['sent']]

    print(f"\n📊 Önizleme ({min(count, len(leads))}/{len(leads)} bekleyen)")
    print(f"{'='*65}")

    for i, lead in enumerate(leads[:count]):
        print(f"\n{'─'*65}")
        print(f"📧 #{i+1} | {lead['priority'].upper()} | {lead['sector']}")
        print(f"To: {lead['email']} ({lead['company']})")
        print(f"Subject: {SUBJECT}")
        print(f"{'─'*65}")
        print(BODY_PLAIN[:250] + "...\n")

    unsent = len(leads)
    print(f"📊 Gönderilecek: {unsent} mail")
    print(f"⏱️  Tahmini süre: {unsent * DELAY_BETWEEN_EMAILS // 60} dakika")
    print(f"📅 Günlük limit {DAILY_LIMIT} → {(unsent // DAILY_LIMIT) + 1} günde tamamlanır")

def cmd_send(limit, priority):
    if not SMTP_PASS:
        print("❌ SMTP_PASS .env dosyasında tanımlı değil!")
        print("   .env dosyasına ekle: SMTP_PASS=şifren")
        return

    leads = [l for l in load_leads(priority) if not l['sent']]
    sent_log = load_sent_log()

    # Bugün kaç gönderilmiş?
    today = datetime.now().strftime('%Y-%m-%d')
    today_count = sum(1 for v in sent_log.values()
                      if v.get('date', '').startswith(today) and 'error' not in v)

    if today_count >= DAILY_LIMIT:
        print(f"⚠️  Bugünkü limit doldu ({today_count}/{DAILY_LIMIT}). Yarın devam et.")
        return

    remaining = min(limit, DAILY_LIMIT - today_count, len(leads))

    if remaining == 0:
        print("✅ Gönderilecek mail kalmadı!")
        return

    print(f"\n🚀 WOC Brussels 2026 — Mail Gönderimi")
    print(f"{'='*50}")
    print(f"  Gönderilecek: {remaining}")
    print(f"  Bugün gönderilmiş: {today_count}/{DAILY_LIMIT}")
    print(f"  Toplam bekleyen: {len(leads)}")
    print(f"  Gecikme: {DELAY_BETWEEN_EMAILS}s/mail")
    print(f"  SMTP: {SMTP_HOST}:{SMTP_PORT}")
    print(f"  Gönderen: {SENDER_EMAIL}")
    print()

    confirm = input(f"  ▶ {remaining} mail göndermek için 'evet' yaz: ").strip().lower()
    if confirm not in ('evet', 'yes', 'e', 'y'):
        print("❌ İptal.")
        return

    sent_count = 0
    for lead in leads[:remaining]:
        try:
            send_email(lead['email'])
            sent_log[lead['email']] = {
                'company': lead['company'],
                'date': datetime.now().isoformat(),
                'priority': lead['priority'],
                'sector': lead['sector'],
                'status': 'sent',
            }
            save_sent_log(sent_log)
            sent_count += 1
            print(f"  ✅ [{sent_count}/{remaining}] {lead['company']:35s} → {lead['email']}")

            if sent_count < remaining:
                time.sleep(DELAY_BETWEEN_EMAILS)

        except Exception as e:
            print(f"  ❌ {lead['company']:35s} → HATA: {e}")
            sent_log[lead['email']] = {
                'company': lead['company'],
                'date': datetime.now().isoformat(),
                'error': str(e),
            }
            save_sent_log(sent_log)

    print(f"\n{'='*50}")
    print(f"✅ Gönderildi: {sent_count}/{remaining}")
    total_sent = len([v for v in sent_log.values() if v.get('status') == 'sent'])
    print(f"📊 Toplam gönderilmiş: {total_sent}")

def cmd_status():
    leads = load_leads()
    sent_log = load_sent_log()

    total = len(leads)
    sent = sum(1 for l in leads if l['email'] in sent_log and sent_log[l['email']].get('status') == 'sent')
    failed = sum(1 for l in leads if l['email'] in sent_log and 'error' in sent_log[l['email']])
    pending = total - sent - failed

    print(f"\n📊 WOC Brussels 2026 — Gönderim Durumu")
    print(f"{'='*50}")
    print(f"  Toplam lead: {total}")
    print(f"  ✅ Gönderildi: {sent}")
    print(f"  ❌ Başarısız: {failed}")
    print(f"  ⏳ Bekleyen: {pending}")

    # Öncelik dağılımı
    pri = {'high': 0, 'medium': 0, 'standard': 0}
    pri_sent = {'high': 0, 'medium': 0, 'standard': 0}
    for l in leads:
        pri[l['priority']] = pri.get(l['priority'], 0) + 1
        if l['email'] in sent_log and sent_log[l['email']].get('status') == 'sent':
            pri_sent[l['priority']] = pri_sent.get(l['priority'], 0) + 1

    print(f"\n  Öncelik dağılımı:")
    for p in ['high', 'medium', 'standard']:
        print(f"    {p:10s}: {pri_sent.get(p,0)}/{pri.get(p,0)} gönderildi")

    # Günlük dağılım
    if sent_log:
        dates = {}
        for v in sent_log.values():
            if v.get('status') == 'sent':
                d = v.get('date', '')[:10]
                dates[d] = dates.get(d, 0) + 1
        if dates:
            print(f"\n  📅 Günlük gönderim:")
            for d in sorted(dates):
                print(f"     {d}: {dates[d]} mail")

# ─── CLI ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='WOC Brussels 2026 — SMTP Mailer')
    parser.add_argument('--test', action='store_true', help='Kendine test maili gönder')
    parser.add_argument('--preview', type=int, nargs='?', const=3, help='Önizleme')
    parser.add_argument('--send', action='store_true', help='Mail gönder')
    parser.add_argument('--status', action='store_true', help='Gönderim durumu')
    parser.add_argument('--limit', type=int, default=BATCH_LIMIT, help=f'Max gönderim (default: {BATCH_LIMIT})')
    parser.add_argument('--priority', choices=['high','medium','standard','all'],
                       default='all', help='Öncelik filtresi')
    args = parser.parse_args()

    if args.test:
        cmd_test()
    elif args.preview is not None:
        cmd_preview(args.preview, args.priority)
    elif args.send:
        cmd_send(args.limit, args.priority)
    elif args.status:
        cmd_status()
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
