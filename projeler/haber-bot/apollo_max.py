#!/usr/bin/env python3
"""
Apollo MAX — Tüm 253 eksik firmayı tara:
1) 116 kontak bulunamayan → geniş arama (filtre yok) + enrichment
2) 116 zayıf kontak → direkt enrichment  
3) 21 TARGET mailsiz → tekrar enrichment
"""
import sqlite3, requests, json, time, os
from dotenv import load_dotenv
import socket

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
CACHE_FILE = "data/apollo_max_cache.json"

def get_domain(website):
    if not website: return None
    d = website.lower().replace("https://","").replace("http://","").replace("www.","")
    return d.split("/")[0] if "." in d.split("/")[0] else None

def clean_company(name):
    clean = name.split("(")[0].strip()
    for s in ["Ltd.","Ltd","LTD","S.A.","SRL","S.R.L.","GmbH","Inc.","Inc","Corp.",
              "A.S.","A.Ş.","Pvt.","PVT","LLC","Plc","PJSC","Limited","CO.,LTD",
              "Co.,Ltd","S.p.A","S.p.A.","KG","AG","Pty","SAOG"]:
        clean = clean.replace(s, "").strip()
    return clean.strip(" .,;-")

def apollo_search_broad(company_name, domain=None):
    """Hiç filtre olmadan kişi bul"""
    try:
        payload = {
            "api_key": API_KEY,
            "per_page": 10,
            "page": 1
        }
        if domain:
            payload["q_organization_domains"] = domain
        else:
            payload["q_organization_name"] = clean_company(company_name)
        
        resp = requests.post(
            "https://api.apollo.io/api/v1/mixed_people/api_search",
            headers={"Content-Type": "application/json", "X-Api-Key": API_KEY},
            json=payload, timeout=15
        )
        if resp.status_code == 429:
            time.sleep(60)
            return apollo_search_broad(company_name, domain)
        if resp.status_code != 200:
            return None
        
        people = resp.json().get("people", [])
        if not people: return None
        
        clean = clean_company(company_name).lower()
        
        # Firma eşleşmesini kontrol et
        for p in people:
            org = (p.get("organization",{}) or {}).get("name","").lower()
            if clean[:8] in org or (domain and domain.lower() in org):
                fname = p.get("first_name","")
                lname = p.get("last_name","")
                return {
                    "name": p.get("name") or f"{fname} {lname}".strip(),
                    "first_name": fname, "last_name": lname,
                    "title": p.get("title"),
                    "apollo_id": p.get("id"),
                    "linkedin_url": p.get("linkedin_url"),
                    "company": (p.get("organization",{}) or {}).get("name", company_name)
                }
        # Eşleşme yoksa domain varsa ilk kişiyi al
        if domain and people:
            p = people[0]
            fname = p.get("first_name","")
            lname = p.get("last_name","")
            return {
                "name": p.get("name") or f"{fname} {lname}".strip(),
                "first_name": fname, "last_name": lname,
                "title": p.get("title"),
                "apollo_id": p.get("id"),
                "linkedin_url": p.get("linkedin_url"),
                "company": (p.get("organization",{}) or {}).get("name", company_name)
            }
        return None
    except:
        return None

def apollo_enrich(apollo_id, first_name=None, last_name=None, company=None, linkedin=None):
    """E-mail enrichment"""
    try:
        payload = {"api_key": API_KEY, "id": apollo_id, "reveal_personal_emails": True}
        if first_name: payload["first_name"] = first_name
        if last_name: payload["last_name"] = last_name
        if company: payload["organization_name"] = company
        if linkedin: payload["linkedin_url"] = linkedin
        
        resp = requests.post(
            "https://api.apollo.io/api/v1/people/match",
            headers={"Content-Type": "application/json", "X-Api-Key": API_KEY},
            json=payload, timeout=15
        )
        if resp.status_code == 429:
            time.sleep(60)
            return apollo_enrich(apollo_id, first_name, last_name, company, linkedin)
        if resp.status_code != 200:
            if "insufficient credits" in resp.text.lower():
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
    
    # ===== KATMAN 1: Hiç kontak yok =====
    no_contact = conn.execute("""SELECT id, company_name, website FROM exhibitor_leads 
        WHERE fair_slug=? AND contact_name IS NULL ORDER BY company_name""", (FAIR,)).fetchall()
    
    # ===== KATMAN 2: Zayıf kontak, mail yok =====
    weak = conn.execute("""SELECT id, company_name, contact_name, contact_title, contact_linkedin
        FROM exhibitor_leads WHERE fair_slug=? AND contact_name IS NOT NULL 
        AND (notes IS NULL OR notes!='TARGET')
        AND (contact_email IS NULL OR contact_email='')
        ORDER BY company_name""", (FAIR,)).fetchall()
    
    # ===== KATMAN 3: TARGET, mail yok =====
    target_no = conn.execute("""SELECT id, company_name, contact_name, contact_title, contact_linkedin
        FROM exhibitor_leads WHERE fair_slug=? AND notes='TARGET' 
        AND (contact_email IS NULL OR contact_email='')
        ORDER BY company_name""", (FAIR,)).fetchall()
    
    # Apollo contact JSON'ları
    apollo_data = {}
    for f in ["data/apollo_contacts.json", "data/apollo_contacts_v2.json"]:
        if os.path.exists(f):
            with open(f) as fh:
                d = json.load(fh)
                for k, v in d.items():
                    if v and v.get("apollo_id"):
                        apollo_data[v.get("name","")] = v
    
    cache = {}
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE) as f:
            cache = json.load(f)
    
    total_tasks = len(no_contact) + len(weak) + len(target_no)
    print(f"🚀 APOLLO MAX — {total_tasks} firma taranacak")
    print(f"   🔴 Kontaksız: {len(no_contact)}")
    print(f"   🟡 Zayıf kontak: {len(weak)}")
    print(f"   🟠 TARGET mailsiz: {len(target_no)}")
    print(f"{'='*70}\n")
    
    found = 0
    idx = 0
    
    # ── KATMAN 1: Kontaksız firmalar ──
    print("━━━ KATMAN 1: Kontaksız firmalar ━━━\n")
    for lid, company, website in no_contact:
        idx += 1
        if company in cache: continue
        
        domain = get_domain(website)
        print(f"[{idx}/{total_tasks}] {company}")
        
        person = apollo_search_broad(company, domain)
        if person:
            print(f"  🔍 {person['name']} — {person['title']}")
            email = apollo_enrich(person['apollo_id'], person['first_name'], 
                                  person['last_name'], company, person.get('linkedin_url'))
            
            if email == "NO_CREDITS":
                print(f"\n🚫 KREDİ BİTTİ!"); break
            
            if email:
                found += 1
                cache[company] = {"email": email, "name": person['name']}
                print(f"  ✅ 📧 {email}")
                conn.execute("""UPDATE exhibitor_leads SET 
                    contact_name=?, contact_title=?, contact_email=?, contact_linkedin=?, notes='TARGET'
                    WHERE id=?""", (person['name'], person['title'], email, person.get('linkedin_url'), lid))
                conn.commit()
            else:
                cache[company] = None
                print(f"  ❌ Mail yok")
        else:
            cache[company] = None
            print(f"  ❌ Kimse bulunamadı")
        
        time.sleep(1)
    
    # ── KATMAN 2: Zayıf kontaklar ──
    print(f"\n━━━ KATMAN 2: Zayıf kontakların maili ━━━\n")
    for lid, company, name, title, linkedin in weak:
        idx += 1
        if f"weak_{name}_{company}" in cache: continue
        
        info = apollo_data.get(name, {})
        apollo_id = info.get("apollo_id")
        
        if not apollo_id:
            # Yeni arama yap
            person = apollo_search_broad(company)
            if person:
                apollo_id = person['apollo_id']
                name = person['name']
                title = person['title']
                linkedin = person.get('linkedin_url')
        
        if not apollo_id:
            cache[f"weak_{name}_{company}"] = None
            continue
        
        print(f"[{idx}/{total_tasks}] {name} @ {company}")
        email = apollo_enrich(apollo_id, info.get("first_name",""), info.get("last_name",""),
                              company, linkedin)
        
        if email == "NO_CREDITS":
            print(f"\n🚫 KREDİ BİTTİ!"); break
        
        if email:
            found += 1
            cache[f"weak_{name}_{company}"] = email
            print(f"  ✅ 📧 {email}")
            conn.execute("""UPDATE exhibitor_leads SET 
                contact_email=?, notes='TARGET' WHERE id=?""", (email, lid))
            conn.commit()
        else:
            cache[f"weak_{name}_{company}"] = None
            print(f"  ❌ Mail yok")
        
        time.sleep(0.5)
    
    # ── KATMAN 3: TARGET mailsiz — son deneme ──
    print(f"\n━━━ KATMAN 3: TARGET mailsiz — son deneme ━━━\n")
    for lid, company, name, title, linkedin in target_no:
        idx += 1
        # Website varsa info@ dene
        web = conn.execute("SELECT website FROM exhibitor_leads WHERE id=?", (lid,)).fetchone()
        website = web[0] if web else None
        domain = get_domain(website)
        
        if domain:
            generic = f"info@{domain}"
            print(f"[{idx}/{total_tasks}] {company} → {generic}")
            found += 1
            conn.execute("UPDATE exhibitor_leads SET contact_email=? WHERE id=?", (generic, lid))
            conn.commit()
    
    conn.commit()
    
    # Save cache
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)
    
    # Final rapor
    final = conn.execute("""SELECT COUNT(*) FROM exhibitor_leads WHERE fair_slug=? 
        AND contact_email IS NOT NULL AND contact_email != ''""", (FAIR,)).fetchone()[0]
    conn.close()
    
    print(f"\n{'='*70}")
    print(f"📊 Bu turda {found} yeni e-mail eklendi")
    print(f"📧 TOPLAM GÖNDERİME HAZIR: {final}")

if __name__ == "__main__":
    main()
