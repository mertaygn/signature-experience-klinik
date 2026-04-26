#!/usr/bin/env python3
"""
Apollo.io E-mail Enrichment — 206 hedef kontağın e-mailini çek.
Apollo ID kullanarak People Enrichment API'si ile e-mail bulur.
Her kişi 1 kredi tüketir.
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
ENRICHED_FILE = "data/apollo_enriched.json"

def enrich_person(apollo_id, first_name, last_name, company, linkedin_url=None):
    """Apollo Enrichment API ile e-mail çek"""
    try:
        payload = {
            "api_key": API_KEY,
            "id": apollo_id,
            "reveal_personal_emails": True,
        }
        # Yedek bilgi
        if first_name: payload["first_name"] = first_name
        if last_name: payload["last_name"] = last_name
        if company: payload["organization_name"] = company
        if linkedin_url: payload["linkedin_url"] = linkedin_url
        
        resp = requests.post(
            "https://api.apollo.io/api/v1/people/match",
            headers={"Content-Type": "application/json", "X-Api-Key": API_KEY},
            json=payload,
            timeout=15
        )
        
        if resp.status_code == 429:
            print(f"  ⏳ Rate limit — 60s bekleniyor...")
            time.sleep(60)
            return enrich_person(apollo_id, first_name, last_name, company, linkedin_url)
        
        if resp.status_code != 200:
            print(f"  ❌ API Hata: {resp.status_code} — {resp.text[:150]}")
            return None
        
        data = resp.json()
        person = data.get("person", {})
        
        if not person:
            return None
        
        email = person.get("email")
        personal_emails = person.get("personal_emails", [])
        
        return {
            "email": email,
            "personal_emails": personal_emails,
            "name": person.get("name"),
            "title": person.get("title"),
            "linkedin_url": person.get("linkedin_url"),
            "company": person.get("organization", {}).get("name") if person.get("organization") else company,
        }
    except Exception as e:
        print(f"  ❌ Hata: {e}")
        return None

def main():
    conn = sqlite3.connect(DB_PATH)
    
    # TARGET olarak işaretlenmiş firmalar (apollo_id ile)
    leads = conn.execute("""
        SELECT el.id, el.company_name, el.contact_name, el.contact_title, el.contact_linkedin
        FROM exhibitor_leads el
        WHERE el.fair_slug=? AND el.notes='TARGET'
        AND el.contact_email IS NULL
        ORDER BY el.company_name
    """, (FAIR,)).fetchall()
    
    # Apollo ID'lerini JSON'dan al
    apollo_data = {}
    for f in ["data/apollo_contacts.json", "data/apollo_contacts_v2.json"]:
        if os.path.exists(f):
            with open(f) as fh:
                d = json.load(fh)
                for key, val in d.items():
                    if val and val.get("apollo_id"):
                        apollo_data[val.get("name", "")] = val
    
    print(f"🔍 E-mail Enrichment — {len(leads)} hedef kişi")
    print(f"💰 Tahmini kredi tüketimi: ~{len(leads)}")
    print(f"{'='*70}\n")
    
    enriched = {}
    if os.path.exists(ENRICHED_FILE):
        with open(ENRICHED_FILE) as f:
            enriched = json.load(f)
    
    found = 0
    no_email = 0
    
    for i, (lead_id, company, name, title, linkedin) in enumerate(leads, 1):
        if name in enriched:
            continue
        
        # Apollo ID bul
        apollo_info = apollo_data.get(name, {})
        apollo_id = apollo_info.get("apollo_id")
        first_name = apollo_info.get("first_name", "")
        last_name = apollo_info.get("last_name", "")
        
        print(f"[{i}/{len(leads)}] {name} — {title} @ {company}")
        
        result = enrich_person(apollo_id, first_name, last_name, company, linkedin)
        
        if result and result.get("email"):
            found += 1
            enriched[name] = result
            print(f"  ✅ 📧 {result['email']}")
            
            conn.execute("UPDATE exhibitor_leads SET contact_email=? WHERE id=?", 
                        (result['email'], lead_id))
            conn.commit()
        elif result and result.get("personal_emails"):
            found += 1
            email = result["personal_emails"][0]
            enriched[name] = result
            print(f"  ✅ 📧 {email} (personal)")
            
            conn.execute("UPDATE exhibitor_leads SET contact_email=? WHERE id=?", 
                        (email, lead_id))
            conn.commit()
        else:
            no_email += 1
            enriched[name] = None
            print(f"  ❌ E-mail bulunamadı")
        
        if i % 10 == 0:
            with open(ENRICHED_FILE, "w") as f:
                json.dump(enriched, f, indent=2, ensure_ascii=False)
            print(f"\n  💾 {found} e-mail bulundu / {i} tarandı\n")
        
        time.sleep(0.5)
    
    with open(ENRICHED_FILE, "w") as f:
        json.dump(enriched, f, indent=2, ensure_ascii=False)
    
    conn.close()
    
    print(f"\n{'='*70}")
    print(f"📊 SONUÇ: {found} e-mail bulundu / {len(leads)} kişi tarandı")
    print(f"📧 Bulunamayan: {no_email}")

if __name__ == "__main__":
    main()
