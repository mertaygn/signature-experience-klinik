#!/usr/bin/env python3
"""
Eksik e-mailleri tamamla:
1) Website'i olanlar → Hunter.io domain search
2) Websitesiz → Apollo'da title filtresi OLMADAN en üst düzey kişiyi bul
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

def get_domain(website):
    if not website: return None
    d = website.lower().replace("https://","").replace("http://","").replace("www.","")
    return d.split("/")[0] if "." in d.split("/")[0] else None

def apollo_search_any(company_name):
    """Firma adıyla herhangi bir kişi bul (title filtresi yok)"""
    clean = company_name.split("(")[0].strip()
    for s in ["Ltd.","Ltd","LTD","S.A.","SRL","GmbH","Inc.","Inc","Corp.","A.S.","A.Ş.",
              "Pvt.","PVT","LLC","Plc","PJSC","Limited","CO.,LTD","Co.,Ltd"]:
        clean = clean.replace(s, "").strip()
    clean = clean.strip(" .,;-")
    
    try:
        resp = requests.post(
            "https://api.apollo.io/api/v1/mixed_people/api_search",
            headers={"Content-Type": "application/json", "X-Api-Key": API_KEY},
            json={
                "api_key": API_KEY,
                "q_organization_name": clean,
                "person_seniorities[]": ["c_suite", "vp", "director", "manager", "head", "founder", "owner"],
                "per_page": 10,
                "page": 1
            },
            timeout=15
        )
        if resp.status_code == 429:
            time.sleep(60)
            return apollo_search_any(company_name)
        if resp.status_code != 200:
            return None
        
        people = resp.json().get("people", [])
        if not people: return None
        
        # Firma adı eşleşen kişileri filtrele
        for p in people:
            org = (p.get("organization",{}) or {}).get("name","").lower()
            if clean.lower()[:10] in org:
                fname = p.get("first_name","")
                lname = p.get("last_name","")
                return {
                    "name": p.get("name") or f"{fname} {lname}".strip(),
                    "first_name": fname,
                    "last_name": lname,
                    "title": p.get("title"),
                    "apollo_id": p.get("id"),
                    "linkedin_url": p.get("linkedin_url"),
                }
        return None
    except:
        return None

def apollo_enrich(apollo_id, first_name, last_name, company, linkedin_url=None):
    """Apollo enrichment ile e-mail çek"""
    try:
        payload = {"api_key": API_KEY, "id": apollo_id, "reveal_personal_emails": True}
        if first_name: payload["first_name"] = first_name
        if last_name: payload["last_name"] = last_name
        if company: payload["organization_name"] = company
        if linkedin_url: payload["linkedin_url"] = linkedin_url
        
        resp = requests.post(
            "https://api.apollo.io/api/v1/people/match",
            headers={"Content-Type": "application/json", "X-Api-Key": API_KEY},
            json=payload, timeout=15
        )
        if resp.status_code == 429:
            time.sleep(60)
            return apollo_enrich(apollo_id, first_name, last_name, company, linkedin_url)
        if resp.status_code != 200:
            if "insufficient credits" in resp.text.lower():
                print(f"  🚫 KREDİ BİTTİ!")
                return "NO_CREDITS"
            return None
        
        person = resp.json().get("person", {})
        email = person.get("email")
        if not email:
            personal = person.get("personal_emails", [])
            email = personal[0] if personal else None
        return email
    except:
        return None

def main():
    conn = sqlite3.connect(DB_PATH)
    
    missing = conn.execute("""SELECT id, company_name, contact_name, contact_title, website
        FROM exhibitor_leads WHERE fair_slug=? AND notes='TARGET' 
        AND (contact_email IS NULL OR contact_email='')
        ORDER BY company_name""", (FAIR,)).fetchall()
    
    print(f"🔄 {len(missing)} eksik e-mail için alternatif kişi aranıyor...")
    print(f"{'='*70}\n")
    
    found = 0
    
    for i, (lid, company, name, title, website) in enumerate(missing, 1):
        print(f"[{i}/{len(missing)}] {company}")
        
        # Yeni kişi bul (farklı title)
        person = apollo_search_any(company)
        
        if person:
            print(f"  🔍 Yeni kişi: {person['name']} — {person['title']}")
            
            # E-mail enrichment
            email = apollo_enrich(
                person['apollo_id'], person['first_name'], person['last_name'],
                company, person.get('linkedin_url')
            )
            
            if email == "NO_CREDITS":
                print(f"\n🚫 Kredi bitti — işlem durduruldu.")
                break
            
            if email:
                found += 1
                print(f"  ✅ 📧 {email}")
                conn.execute("""UPDATE exhibitor_leads SET 
                    contact_name=?, contact_title=?, contact_email=?, contact_linkedin=?
                    WHERE id=?""", (
                    person['name'], person['title'], email, 
                    person.get('linkedin_url'), lid
                ))
                conn.commit()
            else:
                print(f"  ❌ E-mail yok")
        else:
            print(f"  ❌ Alternatif kişi bulunamadı")
        
        time.sleep(1)
    
    # Final
    final = conn.execute("""SELECT COUNT(*) FROM exhibitor_leads WHERE fair_slug=? 
        AND notes='TARGET' AND contact_email IS NOT NULL""", (FAIR,)).fetchone()[0]
    total_target = conn.execute("SELECT COUNT(*) FROM exhibitor_leads WHERE fair_slug=? AND notes='TARGET'", (FAIR,)).fetchone()[0]
    
    conn.close()
    print(f"\n{'='*70}")
    print(f"📊 Bu turda {found} yeni e-mail bulundu")
    print(f"📧 Toplam e-mail: {final}/{total_target} (%{round(final/total_target*100)})")

if __name__ == "__main__":
    main()
