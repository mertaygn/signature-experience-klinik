#!/usr/bin/env python3
"""
Apollo.io Contact Finder V2 — Website'i olmayan firmalar
Firma adıyla arama yaparak karar verici bulur.
"""
import sqlite3, requests, json, time, os
from dotenv import load_dotenv
import socket

# Tailscale DNS bypass
CUSTOM_DNS = {"api.apollo.io": "172.66.140.73"}
_orig = socket.getaddrinfo
def _patched(host, port, *a, **kw):
    if host in CUSTOM_DNS: return _orig(CUSTOM_DNS[host], port, *a, **kw)
    return _orig(host, port, *a, **kw)
socket.getaddrinfo = _patched

load_dotenv()
API_KEY = os.getenv("APOLLO_API_KEY")
DB_PATH = "data/exhibitor_leads.db"
FAIR = "liquid_gas_week_istanbul_2026"
RESULTS_FILE = "data/apollo_contacts_v2.json"

TARGET_TITLES = ["marketing manager", "events manager", "CEO", "managing director", "general manager", "sales director"]
TARGET_SENIORITIES = ["c_suite", "vp", "director", "manager", "head", "founder", "owner"]

def search_by_company_name(company_name):
    """Firma adıyla Apollo'da karar verici ara"""
    try:
        # Firma adını temizle
        clean_name = company_name.split("(")[0].strip()  # parantez içini çıkar
        for suffix in ["Ltd.", "Ltd", "LTD", "S.A.", "SRL", "S.R.L.", "S.p.A", "GmbH", 
                       "CO.,LTD", "Co.,Ltd", "A.S.", "A.Ş.", "Inc.", "Inc", "Corp.", 
                       "Pvt.", "PVT", "LLP", "LLC", "Plc", "PJSC", "Limited"]:
            clean_name = clean_name.replace(suffix, "").strip()
        clean_name = clean_name.strip(" .,;-")
        
        resp = requests.post(
            "https://api.apollo.io/api/v1/mixed_people/api_search",
            headers={"Content-Type": "application/json", "X-Api-Key": API_KEY},
            json={
                "api_key": API_KEY,
                "q_organization_name": clean_name,
                "person_titles[]": TARGET_TITLES,
                "person_seniorities[]": TARGET_SENIORITIES,
                "per_page": 5,
                "page": 1
            },
            timeout=15
        )
        
        if resp.status_code == 429:
            print(f"  ⏳ Rate limit — 60s bekleniyor...")
            time.sleep(60)
            return search_by_company_name(company_name)
        
        if resp.status_code != 200:
            print(f"  ❌ {resp.status_code}: {resp.text[:150]}")
            return None
        
        data = resp.json()
        people = data.get("people", [])
        
        if not people:
            return None
        
        # En iyi kişiyi seç
        best = people[0]
        for p in people:
            title = (p.get("title") or "").lower()
            org = (p.get("organization", {}) or {}).get("name", "").lower() if p.get("organization") else ""
            # Firma adının eşleştiğinden emin ol
            if clean_name.lower()[:10] not in org and company_name.lower()[:10] not in org:
                continue
            if "marketing" in title:
                best = p; break
            elif "event" in title or "exhibition" in title:
                best = p; break
            elif "ceo" in title or "chief executive" in title or "managing director" in title:
                best = p; break
            elif "sales" in title or "business development" in title:
                best = p; break
        
        fname = best.get("first_name") or ""
        lname = best.get("last_name") or ""
        full_name = best.get("name") or f"{fname} {lname}".strip() or "N/A"
        org_name = best.get("organization", {}).get("name") if best.get("organization") else company_name
        
        return {
            "name": full_name,
            "first_name": fname,
            "last_name": lname,
            "title": best.get("title"),
            "email": best.get("email"),
            "linkedin_url": best.get("linkedin_url"),
            "company": org_name,
            "apollo_id": best.get("id"),
        }
    except Exception as e:
        print(f"  ❌ Hata: {e}")
        return None

def main():
    conn = sqlite3.connect(DB_PATH)
    
    # Website'i OLMAYAN firmaları al (henüz contact bulunmamış)
    leads = conn.execute("""
        SELECT id, company_name FROM exhibitor_leads 
        WHERE fair_slug=? AND (website IS NULL OR website='')
        AND contact_name IS NULL
        ORDER BY company_name
    """, (FAIR,)).fetchall()
    
    print(f"🔍 Apollo.io V2 — {len(leads)} firma (isimle aranacak)")
    print(f"{'='*70}\n")
    
    results = {}
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE) as f:
            results = json.load(f)
    
    found = 0
    skipped = 0
    
    for i, (lead_id, name) in enumerate(leads, 1):
        if name in results:
            skipped += 1
            continue
        
        print(f"[{i}/{len(leads)}] {name}")
        
        person = search_by_company_name(name)
        
        if person:
            found += 1
            results[name] = person
            print(f"  ✅ {person['name']} — {person['title']} @ {person['company']}")
            
            conn.execute("""UPDATE exhibitor_leads SET 
                contact_name=?, contact_title=?, contact_email=?, contact_linkedin=?
                WHERE id=?""", (
                person['name'], person['title'],
                person.get('email'), person.get('linkedin_url'),
                lead_id
            ))
            conn.commit()
        else:
            results[name] = None
            print(f"  ❌ Bulunamadı")
        
        if i % 20 == 0:
            with open(RESULTS_FILE, "w") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            print(f"\n  💾 Kaydedildi ({found} bulundu / {i} tarandı)\n")
        
        time.sleep(1)
    
    with open(RESULTS_FILE, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    conn.close()
    
    print(f"\n{'='*70}")
    print(f"📊 SONUÇ: {found} kişi bulundu / {len(leads)} firma tarandı / {skipped} atlandı")

if __name__ == "__main__":
    main()
