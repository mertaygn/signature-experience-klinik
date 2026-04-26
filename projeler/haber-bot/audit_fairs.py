#!/usr/bin/env python3
"""Fair Radar DB — Tam Audit Raporu"""

import sqlite3, re, random, csv
from datetime import date
from collections import Counter

conn = sqlite3.connect('data/fair_radar.db')
conn.row_factory = sqlite3.Row
rows = conn.execute('SELECT * FROM discovered_fairs').fetchall()
fairs = [dict(r) for r in rows]
today = date.today()
total = len(fairs)

print('='*70)
print('📊 FAIR RADAR DB — TAM AUDİT RAPORU')
print(f'Tarih: {today}  |  Toplam: {total} kayıt')
print('='*70)

# ═══════════════════════════════════════════════════════════════
# 1. ZORUNLU ALAN DOLULUK ORANI
# ═══════════════════════════════════════════════════════════════
print('\n' + '─'*70)
print('1️⃣  ZORUNLU ALAN DOLULUK ORANI')
print('─'*70)

fields = ['name', 'country', 'city', 'start_date', 'end_date',
          'sector', 'venue', 'source_url', 'professional_only',
          'exhibitor_count', 'organizer']

for field in fields:
    if field == 'professional_only':
        filled = sum(1 for f in fairs if f.get(field) in (0, 1))
    else:
        filled = sum(1 for f in fairs if f.get(field) not in (None, ''))
    pct = filled * 100 // total if total else 0
    bar = '█' * (pct // 5) + '░' * (20 - pct // 5)
    status = '✅' if pct >= 90 else '⚠️' if pct >= 50 else '❌'
    print(f'  {status} {field:20s} {filled:4d}/{total}  {bar}  {pct}%')

# ═══════════════════════════════════════════════════════════════
# 2. TARİH DENETİMİ
# ═══════════════════════════════════════════════════════════════
print('\n' + '─'*70)
print('2️⃣  TARİH DENETİMİ')
print('─'*70)

date_issues = {'tarihi_yok': 0, 'gecmis': 0, 'start>end': 0, 'tek_gun': 0, 'uzak_gelecek_365+': 0, 'ok': 0}
zone_dist = Counter()
past_but_listed = []

for f in fairs:
    sd = f.get('start_date')
    ed = f.get('end_date')
    if not sd:
        date_issues['tarihi_yok'] += 1
        continue
    try:
        start = date.fromisoformat(sd)
        end = date.fromisoformat(ed) if ed else start
        days = (start - today).days

        if start < today:
            date_issues['gecmis'] += 1
            past_but_listed.append((f['name'], f.get('city',''), sd, days))
        elif start > end:
            date_issues['start>end'] += 1
        else:
            if start == end:
                date_issues['tek_gun'] += 1
            if days > 365:
                date_issues['uzak_gelecek_365+'] += 1
            date_issues['ok'] += 1

        # Zonlama
        if days < 0:
            zone_dist['❌ GEÇMİŞ'] += 1
        elif days < 30:
            zone_dist['🔴 <30g'] += 1
        elif days < 60:
            zone_dist['⚠️ 30-60g'] += 1
        elif days < 120:
            zone_dist['🟡 60-120g'] += 1
        elif days <= 180:
            zone_dist['🔥 120-180g'] += 1
        else:
            zone_dist['🟢 >180g'] += 1
    except Exception as e:
        date_issues['tarihi_yok'] += 1

for k, v in date_issues.items():
    print(f'  {k:20s}: {v}')

print()
print('  ZON DAĞILIMI:')
for zone in ['❌ GEÇMİŞ', '🔴 <30g', '⚠️ 30-60g', '🟡 60-120g', '🔥 120-180g', '🟢 >180g']:
    cnt = zone_dist.get(zone, 0)
    bar = '█' * max(1, cnt // 3) if cnt else ''
    print(f'    {zone:15s}: {cnt:4d}  {bar}')

if past_but_listed:
    print()
    print(f'  ⚠️ GEÇMİŞTE KALMIŞ {len(past_but_listed)} KAYIT (ilk 10):')
    for name, city, sd, days in past_but_listed[:10]:
        print(f'    {name:35s} | {city:15s} | {sd} | {days}g önce')

# ═══════════════════════════════════════════════════════════════
# 3. DUPLICATE DENETİMİ (hafif versiyon)
# ═══════════════════════════════════════════════════════════════
print('\n' + '─'*70)
print('3️⃣  DUPLICATE DENETİMİ')
print('─'*70)

def normalize(name):
    n = name.lower().strip()
    n = re.sub(r'[^a-z0-9\s]', '', n)
    n = re.sub(r'\s+', ' ', n).strip()
    return n

# İsim + ülke bazlı (tarihsiz) kontrol
name_country = Counter()
for f in fairs:
    key = (normalize(f['name']), f.get('country',''))
    name_country[key] += 1

exact_dupes = {k: v for k, v in name_country.items() if v > 1}
print(f'  Toplam unique (isim+ülke): {len(name_country)}')
print(f'  Tam duplicate: {len(exact_dupes)}')
if exact_dupes:
    for (name, country), cnt in list(exact_dupes.items())[:10]:
        print(f'    ⚠️ "{name}" ({country}) x{cnt}')

# Basit fuzzy: aynı ülke + ilk 10 karakter aynı
prefix_groups = {}
for f in fairs:
    key = (normalize(f['name'])[:10], f.get('country', ''))
    prefix_groups.setdefault(key, []).append(f['name'])

fuzzy = {k: v for k, v in prefix_groups.items() if len(set(v)) > 1}
print(f'  Prefix benzerlik (ilk10char+ülke): {len(fuzzy)}')
if fuzzy:
    for (prefix, country), names in list(fuzzy.items())[:10]:
        unique_names = list(set(names))
        print(f'    ⚠️ {country}: {" ↔ ".join(n[:30] for n in unique_names[:3])}')

# ═══════════════════════════════════════════════════════════════
# 4. B2B FİLTRE KALİTESİ
# ═══════════════════════════════════════════════════════════════
print('\n' + '─'*70)
print('4️⃣  B2B FİLTRE KALİTESİ')
print('─'*70)

b2b = [f for f in fairs if f.get('professional_only') == 1]
consumer = [f for f in fairs if f.get('professional_only') == 0]

print(f'  B2B (professional):   {len(b2b)} ({len(b2b)*100//total}%)')
print(f'  Consumer (public):    {len(consumer)} ({len(consumer)*100//total}%)')

print()
print('  CONSUMER etiketli örnekler (doğru mu?):')
for f in consumer[:15]:
    s = (f.get('sector') or '')[:30]
    print(f'    🏷️  {f["name"]:35s} | {f.get("city",""):12s} | {f.get("country",""):8s} | {s}')

print()
print('  B2B etiketli rastgele 15 örnek (doğru mu?):')
random.seed(42)
for f in random.sample(b2b, min(15, len(b2b))):
    s = (f.get('sector') or '')[:30]
    print(f'    🏢 {f["name"]:35s} | {f.get("city",""):12s} | {f.get("country",""):8s} | {s}')

# ═══════════════════════════════════════════════════════════════
# 5. EXHIBITOR COUNT DENETİMİ
# ═══════════════════════════════════════════════════════════════
print('\n' + '─'*70)
print('5️⃣  EXHIBITOR COUNT DENETİMİ')
print('─'*70)

with_exhib = [f for f in fairs if f.get('exhibitor_count')]
print(f'  Exhibitor count olan: {len(with_exhib)}/{total} ({len(with_exhib)*100//total}%)')

counts = []
for f in with_exhib:
    try:
        c = int(str(f['exhibitor_count']).replace(',','').replace('.',''))
        counts.append((c, f['name'], f.get('country',''), f.get('start_date','')))
    except:
        print(f'    ⚠️ Parse edilemeyen: "{f["exhibitor_count"]}" ({f["name"]})')

if counts:
    counts.sort(reverse=True)
    print(f'  Min: {counts[-1][0]:,} ({counts[-1][1]})')
    print(f'  Max: {counts[0][0]:,} ({counts[0][1]})')
    print(f'  Ortalama: {sum(c[0] for c in counts)//len(counts):,}')
    print(f'  Medyan: {counts[len(counts)//2][0]:,}')

    print()
    print('  TOP 15:')
    for i, (cnt, name, country, sd) in enumerate(counts[:15], 1):
        print(f'    {i:2d}. {name:35s} | {country:12s} | {cnt:>6,} exhib | {sd}')

    suspicious = [c for c in counts if c[0] < 10 or c[0] > 10000]
    if suspicious:
        print()
        print(f'  ⚠️ ŞÜPHELİ DEĞERLER ({len(suspicious)}):')
        for cnt, name, country, sd in suspicious:
            print(f'    {name:35s} | {country:12s} | {cnt:>6,}')
    else:
        print('  ✅ Şüpheli değer yok')

# ═══════════════════════════════════════════════════════════════
# 6. ÜLKE DAĞILIMI
# ═══════════════════════════════════════════════════════════════
print('\n' + '─'*70)
print('6️⃣  ÜLKE DAĞILIMI')
print('─'*70)

country_stats = Counter()
country_b2b = Counter()
country_exhib = Counter()
for f in fairs:
    c = f.get('country', '?')
    country_stats[c] += 1
    if f.get('professional_only') == 1: country_b2b[c] += 1
    if f.get('exhibitor_count'): country_exhib[c] += 1

print(f'  {"Ülke":18s}  {"Fuar":>5s}  {"B2B":>5s}  {"Exhib":>5s}  {"B2B%":>5s}')
print(f'  {"─"*18}  {"─"*5}  {"─"*5}  {"─"*5}  {"─"*5}')
for country, cnt in country_stats.most_common():
    b = country_b2b.get(country, 0)
    e = country_exhib.get(country, 0)
    print(f'  {country:18s}  {cnt:5d}  {b:5d}  {e:5d}  {b*100//cnt if cnt else 0:4d}%')

# ═══════════════════════════════════════════════════════════════
# CSV EXPORT
# ═══════════════════════════════════════════════════════════════
csv_path = 'data/fair_radar_export.csv'
with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
    writer = csv.DictWriter(csvfile, fieldnames=[
        'name', 'city', 'country', 'start_date', 'end_date',
        'sector', 'venue', 'organizer', 'exhibitor_count',
        'professional_only', 'source', 'source_url', 'website'
    ])
    writer.writeheader()
    for f in sorted(fairs, key=lambda x: x.get('start_date') or '9999'):
        writer.writerow({k: f.get(k, '') for k in writer.fieldnames})

print(f'\n✅ CSV export: {csv_path} ({total} kayıt)')
conn.close()
