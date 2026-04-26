#!/usr/bin/env python3
"""
Liquid Gas Week Istanbul 2026 — SMTP Mail Gönderici
Evreka Stand outreach mailleri.

Kullanım:
    python lgw_mailer.py --test              # Kendine test maili gönder
    python lgw_mailer.py --preview 5         # İlk 5 maili önizle
    python lgw_mailer.py --send --limit 10   # 10 mail gönder
    python lgw_mailer.py --status            # Gönderim durumu
"""

import sqlite3, smtplib, time, json, argparse, os, socket
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from dotenv import load_dotenv

# Python 3.14 macOS DNS fix — ping çalışır ama Python çözemez
_DNS_MAP = {"smtp.gmail.com": "142.251.127.108"}
_orig_gai = socket.getaddrinfo
def _patched_gai(host, port, *a, **kw):
    if host in _DNS_MAP:
        return _orig_gai(_DNS_MAP[host], port, *a, **kw)
    return _orig_gai(host, port, *a, **kw)
socket.getaddrinfo = _patched_gai

load_dotenv()

# ─── SMTP KONFİGÜRASYON ────────────────────────────────────
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "info@evrekastand.com")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SENDER_NAME = "Evreka Stand"
SENDER_EMAIL = SMTP_USER

DB_PATH = "data/exhibitor_leads.db"
FAIR_SLUG = "liquid_gas_week_istanbul_2026"
SENT_LOG = "data/lgw_sent_log.json"

# Gönderim hız limitleri
DELAY_BETWEEN_EMAILS = 300   # 5 dakika
DAILY_LIMIT = 250
BATCH_LIMIT = 100

# ─── MAİL İÇERİĞİ ──────────────────────────────────────────

def clean_company_name(name):
    """Firma adını mail için temizle — gereksiz suffix ve ALL CAPS düzelt"""
    import re
    
    # Parantez içinde kısa ad varsa onu kullan: "Federation of Indian Petroleum Industry (FIPI)" → "FIPI"
    # Ama sadece kısa kısaltmaysa (5 harf altı), yoksa parantezi sil
    paren = re.search(r'\(([^)]+)\)', name)
    if paren:
        inner = paren.group(1).strip()
        # Kısa kısaltma mı (FIPI, KNPC) yoksa açıklama mı (Go Gas, Emarat)?
        if len(inner) <= 6 and inner.isupper():
            # Kısaltma — ana ismi kullan, parantezi sil
            name = name[:paren.start()].strip()
        elif len(inner) > 2:
            # Açıklayıcı isim — bu daha iyi olabilir
            name = name[:paren.start()].strip()
    
    # Yasal suffix'leri kaldır — birden fazla pass (Corporation Ltd gibi zincirleri yakala)
    suffixes = ["PRIVATE LIMITED", "CO., LTD.", "CO., LTD", "CO.,LTD", "Co.,Ltd", "Co., Ltd",
                "Corporation", "Pvt. Ltd.", "PVT LTD", "PVT. LTD.",
                "GmbH & Co. KG", "GmbH",
                "S.R.L.", "SRL", "S.p.A.", "S.p.A",
                "Limited", "Ltd.", "Ltd", "LTD",
                "S.A.S", "S.A.", "LLC", "LLc", "LLP", "Plc", "PJSC", "Pty",
                "A.S.", "A.Ş.", "Inc.", "Inc", "Corp.",
                "B.V..", "B.V.", "B.V",
                "San. Ve Tic.", "San.ve Dis Tic", "END. ÜRN. SAN. VE DIŞ TİC. LTD. ŞTİ.",
                "iml san ve tic ltd sti", "Sde RL de CV", "SA DE CV", "SA de CV",
                "S.P.A.", "S.P.A", "KG"]
    changed = True
    while changed:
        changed = False
        for suffix in suffixes:
            if name.lower().endswith(suffix.lower()):
                name = name[:-len(suffix)].strip(" .,;-")
                changed = True
                break
    
    # Kalan "CO", "PVT", "CO,," gibi artıkları temizle (sadece ayrı kelime ise)
    name = name.rstrip(" .,;-")
    for tail in ["CO,,", "CO,", "CO."]:
        if name.endswith(tail):
            name = name[:-len(tail)].strip(" .,;-")
    # CO ve PVT sadece bağımsız kelime ise sil (OGECO gibi kelimeleri bozma)
    words_check = name.split()
    if words_check and words_check[-1] in ("CO", "Co", "PVT", "Corp"):
        name = " ".join(words_check[:-1]).strip(" .,;-")
    
    # ALL CAPS düzelt → Title Case (5+ harf, bilinen kısaltmalar hariç)
    keep_upper = {"LPG", "LNG", "CNG", "UAE", "USA", "SCG", "OPW", "GTI", "YPF", "VRA",
                  "IDEF", "SAHA", "EXPO", "HYENA", "OPIS", "JOGMEC", "DVFG", "FIPI",
                  "NGC", "MEC", "MCA", "CPS", "DCC", "IMZ", "KNPC", "NGL", "BW",
                  "TEC4FUELS", "OGECO", "SHV", "OMAL", "PKL", "NLNG", "GOK", "SMPC",
                  "IDEX", "FLOGAS", "STIGC", "SAOG"}
    lower_words = {"AND", "OF", "FOR", "THE", "IN", "DE", "DES", "ET"}
    words = name.split()
    fixed = []
    for i, w in enumerate(words):
        if w.upper() in keep_upper:
            fixed.append(w.upper())
        elif w.upper() in lower_words and i > 0:  # İlk kelimeyi küçültme
            fixed.append(w.lower())
        elif w.isupper() and len(w) > 4 and not any(c.isdigit() for c in w):
            fixed.append(w.title())
        else:
            fixed.append(w)
    name = " ".join(fixed)
    
    # Fazla boşluk ve trailing nokta temizle
    name = " ".join(name.split()).strip(" .,;-")
    
    return name

def clean_contact_name(first_name):
    """İsmi mail için temizle — Türkçe transliterasyon + geçersiz isim kontrolü"""
    if not first_name or len(first_name) <= 1:
        return None  # Tek harf isim geçersiz
    
    # Apollo'nun Türkçe karakter transliterasyonlarını düzelt
    replacements = {
        "Guenay": "Günay", "Goezde": "Gözde", "Oezge": "Özge",
        "Oemer": "Ömer", "Oezer": "Özer", "Oezlem": "Özlem",
        "Guenes": "Güneş", "Guelten": "Gülten", "Gueler": "Güler",
        "Guengoer": "Güngör", "Guelbey": "Gülbey", "Guelay": "Gülay",
        "Uenal": "Ünal", "Uemit": "Ümit",
        "Sueha": "Süha", "Tuerkan": "Türkan",
        "Buesra": "Büşra", "Huelya": "Hülya",
        "Muenevver": "Münevver", "Nuesret": "Nüsret",
    }
    
    for latin, turkish in replacements.items():
        if first_name == latin:
            return turkish
    
    return first_name

def get_greeting(contact_name):
    """İsimden selamlama oluştur"""
    first = contact_name.split()[0] if contact_name else ""
    first = clean_contact_name(first)
    if first and first != "N/A":
        return f"Dear {first},"
    return "Hello,"

def get_subject(contact_name, company_name):
    return f"Liquid Gas Week Istanbul — Local Stand Partner"

def get_body_plain(contact_name, company_name):
    company_name = clean_company_name(company_name)
    greeting = get_greeting(contact_name)
    
    return f"""{greeting}

I noticed that {company_name} will be exhibiting at Liquid Gas Week 2026 in Istanbul (12–16 October), and wanted to reach out ahead of your stand planning.

We are Evreka Stand — an Istanbul-based exhibition stand contractor delivering turnkey booth projects across 28+ countries. From concept and 3D design to production, logistics, and on-site installation, we manage the entire process in-house so your team can stay focused on the event itself.

As a local contractor in Istanbul, we offer clear advantages for Liquid Gas Week:

  • Local production → faster turnaround and cost efficiency
  • Direct logistics to Istanbul Congress Center (ICC) → no international shipping
  • On-site team → immediate support during build-up and show days
  • Proven experience in energy and industrial exhibitions worldwide

Recent projects from Istanbul and the energy sector:

→ TotalEnergies | COP29
  https://www.evrekastand.com/work/total-energies-cop29

→ UAE National Pavilion | SAHA EXPO Istanbul
  https://www.evrekastand.com/work/the-uae-national-pavilion-saha-expo

→ Baykar | Marrakech Air Show
  https://www.evrekastand.com/work/baykar-marrakech-air-show

→ China Defence Pavilion | IDEF Istanbul
  https://www.evrekastand.com/work/china-defence-pavilion-idef

→ Full Portfolio
  https://www.evrekastand.com/work

If your stand partner for Istanbul is not yet confirmed, we can quickly share initial design directions tailored to your brand — with no obligation.

You can book a short call here → https://www.evrekastand.com/contact
Or simply reply to this email.

Best regards,
Evreka Stand Team
Istanbul, Türkiye
https://www.evrekastand.com"""

def get_body_html(contact_name, company_name):
    company_name = clean_company_name(company_name)
    greeting = get_greeting(contact_name)
    
    return f"""<div style="font-family: 'Segoe UI', Arial, sans-serif; font-size: 14px; color: #2c2c2c; line-height: 1.7; max-width: 600px;">

<p>{greeting}</p>

<p>I noticed that <strong>{company_name}</strong> will be exhibiting at <strong>Liquid Gas Week 2026 in Istanbul</strong> (12–16 October), and wanted to reach out ahead of your stand planning.</p>

<p>We are <strong>Evreka Stand</strong> — an Istanbul-based exhibition stand contractor delivering turnkey booth projects across <strong>28+ countries</strong>. From concept and 3D design to production, logistics, and on-site installation, we manage the entire process in-house so your team can stay focused on the event itself.</p>

<p>As a <strong>local contractor in Istanbul</strong>, we offer clear advantages for Liquid Gas Week:</p>

<ul style="padding-left: 20px; color: #444;">
  <li>🏭 <strong>Local production</strong> → faster turnaround and cost efficiency</li>
  <li>🚚 <strong>Direct logistics</strong> to Istanbul Congress Center (ICC) → no international shipping</li>
  <li>🔧 <strong>On-site team</strong> → immediate support during build-up and show days</li>
  <li>⚡ <strong>Proven experience</strong> in energy and industrial exhibitions worldwide</li>
</ul>

<p>Recent projects from <strong>Istanbul and the energy sector</strong>:</p>

<table style="border-collapse: collapse; margin: 12px 0;">
  <tr>
    <td style="padding: 6px 16px 6px 0;">→</td>
    <td><a href="https://www.evrekastand.com/work/total-energies-cop29" style="color: #1a73e8; text-decoration: none; font-weight: 600;">TotalEnergies | COP29</a></td>
  </tr>
  <tr>
    <td style="padding: 6px 16px 6px 0;">→</td>
    <td><a href="https://www.evrekastand.com/work/the-uae-national-pavilion-saha-expo" style="color: #1a73e8; text-decoration: none; font-weight: 600;">UAE National Pavilion | SAHA EXPO Istanbul</a></td>
  </tr>
  <tr>
    <td style="padding: 6px 16px 6px 0;">→</td>
    <td><a href="https://www.evrekastand.com/work/baykar-marrakech-air-show" style="color: #1a73e8; text-decoration: none; font-weight: 600;">Baykar | Marrakech Air Show</a></td>
  </tr>
  <tr>
    <td style="padding: 6px 16px 6px 0;">→</td>
    <td><a href="https://www.evrekastand.com/work/china-defence-pavilion-idef" style="color: #1a73e8; text-decoration: none; font-weight: 600;">China Defence Pavilion | IDEF Istanbul</a></td>
  </tr>
  <tr>
    <td style="padding: 6px 16px 6px 0;">→</td>
    <td><a href="https://www.evrekastand.com/work" style="color: #1a73e8; text-decoration: none; font-weight: 600;">Full Portfolio</a></td>
  </tr>
</table>

<p>If your stand partner for Istanbul is not yet confirmed, we can quickly share initial design directions tailored to your brand — with no obligation.</p>

<p>
  <a href="https://www.evrekastand.com/contact" style="display: inline-block; padding: 10px 24px; background: #1a73e8; color: white; text-decoration: none; border-radius: 6px; font-weight: 600;">Book a Short Call →</a>
  &nbsp;&nbsp;or simply reply to this email
</p>

<p style="margin-top: 28px; border-top: 1px solid #e0e0e0; padding-top: 16px;">
  Best regards,<br>
  <strong>Evreka Stand Team</strong><br>
  <span style="color: #888;">Istanbul, Türkiye</span><br>
  <a href="https://www.evrekastand.com" style="color: #1a73e8; text-decoration: none;">evrekastand.com</a>
</p>

</div>"""

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

def send_email(to_email, contact_name, company_name):
    msg = MIMEMultipart('alternative')
    msg['From'] = f"{SENDER_NAME} <{SENDER_EMAIL}>"
    msg['To'] = to_email
    msg['Subject'] = get_subject(contact_name, company_name)
    msg['Reply-To'] = SENDER_EMAIL

    msg.attach(MIMEText(get_body_plain(contact_name, company_name), 'plain', 'utf-8'))
    msg.attach(MIMEText(get_body_html(contact_name, company_name), 'html', 'utf-8'))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)
    return True

# ─── LEAD YÜKLEME ──────────────────────────────────────────

def load_leads():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT id, company_name, contact_name, contact_title, contact_email
        FROM exhibitor_leads 
        WHERE fair_slug=? AND contact_email IS NOT NULL AND contact_email!=''
        ORDER BY company_name
    """, (FAIR_SLUG,)).fetchall()
    conn.close()

    sent_log = load_sent_log()
    leads = []
    seen_emails = set()

    for row_id, company, name, title, email in rows:
        email_lower = email.lower().strip()
        if email_lower in seen_emails:
            continue
        seen_emails.add(email_lower)
        
        leads.append({
            'id': row_id,
            'company': company,
            'contact_name': name or '',
            'contact_title': title or '',
            'email': email,
            'sent': email_lower in {k.lower() for k in sent_log},
        })
    return leads

# ─── KOMUTLAR ───────────────────────────────────────────────

def cmd_test():
    if not SMTP_PASS:
        print("❌ SMTP_PASS .env dosyasında tanımlı değil!")
        return
    print(f"📧 Test maili gönderiliyor → {SENDER_EMAIL}")
    try:
        send_email(SENDER_EMAIL, "Test", "Test Company")
        print("✅ Test maili gönderildi! Gelen kutunu kontrol et.")
    except Exception as e:
        print(f"❌ HATA: {e}")

def cmd_preview(count):
    leads = [l for l in load_leads() if not l['sent']]
    print(f"\n📊 Önizleme ({min(count, len(leads))}/{len(leads)} bekleyen)")
    print(f"{'='*70}")

    for i, lead in enumerate(leads[:count]):
        print(f"\n{'─'*70}")
        print(f"📧 #{i+1}")
        print(f"To: {lead['contact_name']} <{lead['email']}> ({lead['company']})")
        print(f"Title: {lead['contact_title']}")
        print(f"Subject: {get_subject(lead['contact_name'], lead['company'])}")
        print(f"{'─'*70}")
        print(get_body_plain(lead['contact_name'], lead['company'])[:400] + "...\n")

    unsent = len(leads)
    print(f"📊 Gönderilecek: {unsent} mail")
    print(f"⏱️  Tahmini süre: {unsent * DELAY_BETWEEN_EMAILS // 60} dakika")
    print(f"📅 Günlük limit {DAILY_LIMIT} → {(unsent // DAILY_LIMIT) + 1} günde tamamlanır")

def cmd_send(limit, auto_confirm=False):
    if not SMTP_PASS:
        print("❌ SMTP_PASS .env dosyasında tanımlı değil!")
        return

    leads = [l for l in load_leads() if not l['sent']]
    sent_log = load_sent_log()

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

    print(f"\n🚀 Liquid Gas Week Istanbul 2026 — Mail Gönderimi")
    print(f"{'='*55}")
    print(f"  Gönderilecek: {remaining}")
    print(f"  Bugün gönderilmiş: {today_count}/{DAILY_LIMIT}")
    print(f"  Toplam bekleyen: {len(leads)}")
    print(f"  Gecikme: {DELAY_BETWEEN_EMAILS}s/mail")
    print(f"  SMTP: {SMTP_HOST}:{SMTP_PORT}")
    print(f"  Gönderen: {SENDER_EMAIL}")
    print()

    confirm = auto_confirm or input(f"  ▶ {remaining} mail göndermek için 'evet' yaz: ").strip().lower()
    if confirm not in ('evet', 'yes', 'e', 'y', True):
        print("❌ İptal.")
        return

    sent_count = 0
    for lead in leads[:remaining]:
        try:
            send_email(lead['email'], lead['contact_name'], lead['company'])
            sent_log[lead['email']] = {
                'company': lead['company'],
                'contact': lead['contact_name'],
                'title': lead['contact_title'],
                'date': datetime.now().isoformat(),
                'status': 'sent',
            }
            save_sent_log(sent_log)
            sent_count += 1
            print(f"  ✅ [{sent_count}/{remaining}] {lead['contact_name']:20s} @ {lead['company']:30s} → {lead['email']}")
            if sent_count < remaining:
                time.sleep(DELAY_BETWEEN_EMAILS)
        except Exception as e:
            print(f"  ❌ {lead['company']:30s} → HATA: {e}")
            sent_log[lead['email']] = {
                'company': lead['company'],
                'date': datetime.now().isoformat(),
                'error': str(e),
            }
            save_sent_log(sent_log)

    print(f"\n{'='*55}")
    print(f"✅ Gönderildi: {sent_count}/{remaining}")
    total_sent = len([v for v in sent_log.values() if v.get('status') == 'sent'])
    print(f"📊 Toplam gönderilmiş: {total_sent}")

def cmd_status():
    leads = load_leads()
    sent_log = load_sent_log()

    total = len(leads)
    sent = sum(1 for l in leads if l['sent'])
    pending = total - sent

    print(f"\n📊 LGW Istanbul 2026 — Gönderim Durumu")
    print(f"{'='*50}")
    print(f"  Toplam lead: {total}")
    print(f"  ✅ Gönderildi: {sent}")
    print(f"  ⏳ Bekleyen: {pending}")

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
    parser = argparse.ArgumentParser(description='LGW Istanbul 2026 — SMTP Mailer')
    parser.add_argument('--test', action='store_true', help='Kendine test maili gönder')
    parser.add_argument('--preview', type=int, nargs='?', const=3, help='Önizleme')
    parser.add_argument('--send', action='store_true', help='Mail gönder')
    parser.add_argument('--status', action='store_true', help='Gönderim durumu')
    parser.add_argument('--yes', '-y', action='store_true', help='Onay atlama (zamanlı görevler için)')
    parser.add_argument('--limit', type=int, default=BATCH_LIMIT, help=f'Max gönderim (default: {BATCH_LIMIT})')
    args = parser.parse_args()

    if args.test:
        cmd_test()
    elif args.preview is not None:
        cmd_preview(args.preview)
    elif args.send:
        cmd_send(args.limit, auto_confirm=args.yes)
    elif args.status:
        cmd_status()
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
