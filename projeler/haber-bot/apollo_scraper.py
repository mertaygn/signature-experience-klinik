#!/usr/bin/env python3
"""
Apollo.io Contact Finder — LGW Istanbul 2026
Her firmadan 1 karar verici (Marketing/CEO/Director) bulur.
"""
import sqlite3, requests, json, time, os, re
from dotenv import load_dotenv
from urllib3.util.connection import create_connection as _orig_create_connection
import urllib3, socket

# Tailscale DNS bypass — api.apollo.io IP'sini elle çöz
CUSTOM_DNS = {"api.apollo.io": "172.66.140.73"}
_orig_getaddrinfo = socket.getaddrinfo
def _patched_getaddrinfo(host, port, *args, **kwargs):
    if host in CUSTOM_DNS:
        return _orig_getaddrinfo(CUSTOM_DNS[host], port, *args, **kwargs)
    return _orig_getaddrinfo(host, port, *args, **kwargs)
socket.getaddrinfo = _patched_getaddrinfo

load_dotenv()
API_KEY = os.getenv("APOLLO_API_KEY")
DB_PATH = "data/exhibitor_leads.db"
FAIR = "liquid_gas_week_istanbul_2026"
RESULTS_FILE = "data/apollo_contacts.json"

# Aranacak pozisyonlar (sıralı öncelik)
TARGET_TITLES = ["marketing manager", "events manager", "trade fair", "exhibition", "CEO", "managing director", "general manager"]
TARGET_SENIORITIES = ["c_suite", "vp", "director", "manager", "head"]

def get_domain(website):
    """Website URL'den domain çıkar"""
    if not website:
        return None
    domain = website.lower().replace("https://", "").replace("http://", "").replace("www.", "")
    domain = domain.split("/")[0]
    return domain if "." in domain else None

def search_person(domain, company_name):
    """Apollo API ile firmada karar verici ara"""
    try:
        resp = requests.post(
            "https://api.apollo.io/api/v1/mixed_people/api_search",
            headers={"Content-Type": "application/json", "Cache-Control": "no-cache",
                      "X-Api-Key": API_KEY},
            json={
                "api_key": API_KEY,
                "q_organization_domains": domain,
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
            return search_person(domain, company_name)
        
        if resp.status_code != 200:
            print(f"  ❌ API Hata: {resp.status_code} — {resp.text[:200]}")
            return None
        
        data = resp.json()
        people = data.get("people", [])
        
        if not people:
            return None
        
        # En iyi kişiyi seç (marketing > events > CEO > director)
        best = people[0]
        for p in people:
            title = (p.get("title") or "").lower()
            if "marketing" in title:
                best = p
                break
            elif "event" in title or "fair" in title or "exhibition" in title:
                best = p
                break
            elif "ceo" in title or "chief" in title or "managing director" in title:
                best = p
                break
        
        # İsim oluştur
        fname = best.get("first_name") or ""
        lname = best.get("last_name") or ""
        full_name = best.get("name") or f"{fname} {lname}".strip() or "N/A"
        
        return {
            "name": full_name,
            "first_name": fname,
            "last_name": lname,
            "title": best.get("title"),
            "email": best.get("email"),
            "linkedin_url": best.get("linkedin_url"),
            "company": best.get("organization", {}).get("name") if best.get("organization") else company_name,
            "apollo_id": best.get("id"),
        }
    except Exception as e:
        print(f"  ❌ Hata: {e}")
        return None

def main():
    conn = sqlite3.connect(DB_PATH)
    
    # Website'i olan firmaları al
    leads = conn.execute("""
        SELECT id, company_name, website FROM exhibitor_leads 
        WHERE fair_slug=? AND website IS NOT NULL AND website != ''
        ORDER BY company_name
    """, (FAIR,)).fetchall()
    
    print(f"🔍 Apollo.io ile {len(leads)} firma taranacak...")
    print(f"{'='*70}\n")
    
    # Önceki sonuçları yükle (devam etmek için)
    results = {}
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE) as f:
            results = json.load(f)
    
    found = 0
    skipped = 0
    
    for i, (lead_id, name, website) in enumerate(leads, 1):
        domain = get_domain(website)
        if not domain:
            continue
        
        # Zaten taranmış mı?
        if domain in results:
            skipped += 1
            continue
        
        print(f"[{i}/{len(leads)}] {name} ({domain})")
        
        person = search_person(domain, name)
        
        if person:
            found += 1
            results[domain] = person
            print(f"  ✅ {person['name']} — {person['title']}")
            if person.get('email'):
                print(f"     📧 {person['email']}")
            
            # DB'ye kaydet
            conn.execute("""UPDATE exhibitor_leads SET 
                contact_name=?, contact_title=?, contact_email=?, contact_linkedin=?
                WHERE id=?""", (
                person['name'], person['title'], 
                person.get('email'), person.get('linkedin_url'),
                lead_id
            ))
            conn.commit()
        else:
            results[domain] = None
            print(f"  ❌ Bulunamadı")
        
        # Sonuçları kaydet (her 10 firmada bir)
        if i % 10 == 0:
            with open(RESULTS_FILE, "w") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            print(f"\n  💾 Kaydedildi ({found} bulundu / {i} tarandı)\n")
        
        time.sleep(1)  # Rate limit koruması
    
    # Final kayıt
    with open(RESULTS_FILE, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    conn.close()
    
    print(f"\n{'='*70}")
    print(f"📊 SONUÇ: {found} kişi bulundu / {len(leads)} firma tarandı / {skipped} atlandı")
    print(f"💾 Sonuçlar: {RESULTS_FILE}")

if __name__ == "__main__":
    main()
