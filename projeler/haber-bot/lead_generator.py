"""
Lead Generator — Fırsat haberinden satış aksiyonu üretir.

Pipeline:
  HABER → FIRSAT → LEAD ANALİZİ → TEKLİF → OUTREACH

Her 🟢 haberden çıkarır:
  1. Event bilgisi (isim, ülke, sektör, organizatör)
  2. Hedef müşteri segmenti
  3. Teklif önerisi
  4. Aksiyon adımları
"""

import re
from config import HIGH_VALUE_FAIRS


# ═══════════════════════════════════════════════════════════════════════════
# 1. ÜLKE TESPİT + STRATEJİ
# ═══════════════════════════════════════════════════════════════════════════

# Şehir/venue → ülke mapping
LOCATION_TO_COUNTRY = {
    # Almanya
    "hannover": "Almanya", "frankfurt": "Almanya", "munich": "Almanya",
    "münchen": "Almanya", "düsseldorf": "Almanya", "cologne": "Almanya",
    "köln": "Almanya", "berlin": "Almanya", "nuremberg": "Almanya",
    "nürnberg": "Almanya", "stuttgart": "Almanya", "hamburg": "Almanya",
    "friedrichshafen": "Almanya",
    # İtalya
    "milan": "İtalya", "milano": "İtalya", "bologna": "İtalya",
    "verona": "İtalya", "rimini": "İtalya", "rome": "İtalya",
    # İspanya
    "barcelona": "İspanya", "madrid": "İspanya", "valencia": "İspanya",
    # Fransa
    "paris": "Fransa", "lyon": "Fransa", "villepinte": "Fransa",
    # BAE / Körfez
    "dubai": "BAE", "abu dhabi": "BAE", "riyadh": "Suudi Arabistan",
    "doha": "Katar", "muscat": "Umman",
    # Asya
    "shanghai": "Çin", "guangzhou": "Çin", "beijing": "Çin",
    "shenzhen": "Çin", "hong kong": "Hong Kong",
    "tokyo": "Japonya", "osaka": "Japonya",
    "singapore": "Singapur", "bangkok": "Tayland",
    "taipei": "Tayvan", "seoul": "Güney Kore",
    "mumbai": "Hindistan", "new delhi": "Hindistan",
    "jakarta": "Endonezya",
    # Amerika
    "las vegas": "ABD", "chicago": "ABD", "new york": "ABD",
    "orlando": "ABD", "atlanta": "ABD", "boston": "ABD",
    "san francisco": "ABD", "los angeles": "ABD",
    "são paulo": "Brezilya", "mexico city": "Meksika",
    # Türkiye
    "istanbul": "Türkiye", "ankara": "Türkiye", "izmir": "Türkiye",
    "antalya": "Türkiye",
    # Diğer
    "london": "İngiltere", "birmingham": "İngiltere",
    "amsterdam": "Hollanda", "brussels": "Belçika",
    "vienna": "Avusturya", "zurich": "İsviçre", "geneva": "İsviçre",
    "moscow": "Rusya", "johannesburg": "Güney Afrika",
    "cairo": "Mısır", "nairobi": "Kenya",
}

# Ülke → Satış stratejisi
COUNTRY_STRATEGY = {
    "Almanya":  {"tip": "Büyük exhibitor + organizer", "aksiyon": "Exhibitor listesi çek, organizer'a direkt ulaş"},
    "İtalya":   {"tip": "Tasarım odaklı exhibitor", "aksiyon": "Tasarım portföyü ile yaklaş"},
    "İspanya":  {"tip": "Exhibitor + yerel partner", "aksiyon": "IFEMA/Fira ile temas kur"},
    "Fransa":   {"tip": "Exhibitor + lüks segment", "aksiyon": "Premium stand portföyü sun"},
    "BAE":      {"tip": "Hızlı satış + stand builder partner", "aksiyon": "Yerel partner ile ortak teklif"},
    "Suudi Arabistan": {"tip": "Mega proje + devlet fuarı", "aksiyon": "Büyük metraj teklif hazırla"},
    "Çin":      {"tip": "Partner bul + ortak üretim", "aksiyon": "Yerel üretici ile işbirliği"},
    "Hong Kong": {"tip": "Premium exhibitor", "aksiyon": "Uluslararası firma listesi çek"},
    "Türkiye":  {"tip": "Direkt satış", "aksiyon": "Doğrudan müşteri ziyareti"},
    "ABD":      {"tip": "Büyük bütçe exhibitor", "aksiyon": "Fortune 500 exhibitor listesi"},
    "Hindistan": {"tip": "Hacim + pavilion işi", "aksiyon": "Ülke pavilyonu ihalesi takip"},
    "Japonya":  {"tip": "Premium + teknoloji", "aksiyon": "Japon exhibitor'lara özel teklif"},
    "Singapur": {"tip": "Hub + premium", "aksiyon": "ASEAN firmalarına ulaş"},
    "İngiltere": {"tip": "Exhibitor + organizer", "aksiyon": "ExCeL/NEC etkinlik takvimi takip"},
}

DEFAULT_STRATEGY = {"tip": "Exhibitor + yerel partner", "aksiyon": "Exhibitor listesi ve yerel partner ara"}


# ═══════════════════════════════════════════════════════════════════════════
# 2. SEKTÖR TESPİT + TEKLİF
# ═══════════════════════════════════════════════════════════════════════════

INDUSTRY_KEYWORDS = {
    "manufacturing":  "Endüstri / Üretim",
    "industrial":     "Endüstri / Üretim",
    "machinery":      "Makine",
    "automotive":     "Otomotiv",
    "medical":        "Medikal",
    "healthcare":     "Sağlık",
    "pharma":         "İlaç",
    "technology":     "Teknoloji",
    "IT ":            "Bilgi Teknolojisi",
    "software":       "Yazılım",
    "defense":        "Savunma",
    "defence":        "Savunma",
    "military":       "Savunma",
    "energy":         "Enerji",
    "oil ":           "Petrol & Gaz",
    "mining":         "Madencilik",
    "construction":   "İnşaat",
    "building":       "Yapı Malzemeleri",
    "food":           "Gıda",
    "packaging":      "Ambalaj",
    "logistics":      "Lojistik",
    "agriculture":    "Tarım",
    "textile":        "Tekstil",
    "chemical":       "Kimya",
    "aerospace":      "Havacılık",
    "maritime":       "Denizcilik",
    "mobility":       "Mobilite",
    "furniture":      "Mobilya",
    "electronics":    "Elektronik",
    "telecom":        "Telekomünikasyon",
    "space":          "Uzay",
    "cosmetic":       "Kozmetik",
    "beauty":         "Kozmetik",
}

# Sektör → Teklif önerisi
INDUSTRY_OFFER = {
    "Endüstri / Üretim": {"stand": "Büyük metraj endüstriyel stand", "öne_çıkan": "Ağır ürün sergileme + demo alanı"},
    "Makine":            {"stand": "Açık plan + ağır yük platformu", "öne_çıkan": "Makine demo alanı + vinç noktası"},
    "Otomotiv":          {"stand": "Showroom konsept + döner platform", "öne_çıkan": "Araç sergileme + LED duvar"},
    "Medikal":           {"stand": "Modüler + steril tasarım", "öne_çıkan": "Temiz oda hissi + ürün vitrin"},
    "Sağlık":            {"stand": "Modüler + steril tasarım", "öne_çıkan": "Temiz oda hissi + ürün vitrin"},
    "İlaç":              {"stand": "Premium kapalı stand", "öne_çıkan": "Meeting odası + NDA alanı"},
    "Teknoloji":         {"stand": "LED + deneyim odaklı", "öne_çıkan": "Interaktif ekran + VR demo"},
    "Savunma":           {"stand": "High security + premium", "öne_çıkan": "Kapalı toplantı + ürün maketi"},
    "Enerji":            {"stand": "Büyük metraj açık stand", "öne_çıkan": "Maket + sürdürülebilirlik teması"},
    "Gıda":              {"stand": "Açık mutfak + tadım alanı", "öne_çıkan": "Soğuk zincir vitrin + demo"},
    "Ambalaj":           {"stand": "Makine demo + numune alanı", "öne_çıkan": "Canlı üretim hattı demo"},
    "Tekstil":           {"stand": "Showroom + kumaş sergileme", "öne_çıkan": "Işık odaklı ürün sunumu"},
    "Mobilya":           {"stand": "Estetik + geniş alan showroom", "öne_çıkan": "Yaşam alanı konsepti"},
    "Elektronik":        {"stand": "LED + interaktif", "öne_çıkan": "Ürün deneyim istasyonu"},
    "Havacılık":         {"stand": "Premium + maket alanı", "öne_çıkan": "1:1 maket + simülatör"},
    "Kozmetik":          {"stand": "Lüks + deneyim", "öne_çıkan": "Test bar + ayna duvar + ışık"},
    "Uzay":              {"stand": "Premium + maket alanı", "öne_çıkan": "Uydu/uzay aracı maketi"},
}

DEFAULT_OFFER = {"stand": "Özel tasarım modüler stand", "öne_çıkan": "Marka kimliğine uygun premium tasarım"}


# ═══════════════════════════════════════════════════════════════════════════
# 3. ORGANİZATÖR TESPİT
# ═══════════════════════════════════════════════════════════════════════════

KNOWN_ORGANIZERS = {
    "messe frankfurt": "Messe Frankfurt",
    "deutsche messe":  "Deutsche Messe",
    "rx global":       "RX Global",
    "reed exhibitions": "RX Global",
    "koelnmesse":      "Koelnmesse",
    "fiera milano":    "Fiera Milano",
    "informa markets": "Informa Markets",
    "informa":         "Informa Markets",
    "dwtc":            "Dubai World Trade Centre",
    "dubai world trade": "Dubai World Trade Centre",
    "fira barcelona":  "Fira Barcelona",
    "ifema":           "IFEMA Madrid",
    "tüyap":           "TÜYAP",
    "cnr expo":        "CNR Expo",
    "nürnbergmesse":   "NürnbergMesse",
    "messe münchen":   "Messe München",
    "messe düsseldorf": "Messe Düsseldorf",
    "messe berlin":    "Messe Berlin",
    "messe stuttgart":  "Messe Stuttgart",
    "hamburg messe":   "Hamburg Messe",
    "palexpo":         "Palexpo Geneva",
    "rai amsterdam":   "RAI Amsterdam",
    "excel london":    "ExCeL London",
    "javits":          "Javits Center NYC",
}


# ═══════════════════════════════════════════════════════════════════════════
# 4. FUAR İSİM TESPİT
# ═══════════════════════════════════════════════════════════════════════════

def _detect_event_name(text: str) -> str:
    """Bilinen fuar isimlerini metinden çıkar."""
    for fair in HIGH_VALUE_FAIRS:
        if fair.lower() in text.lower():
            return fair
    return ""


def _detect_country(text: str) -> str:
    """Lokasyon → ülke tespiti."""
    text_lower = text.lower()
    for location, country in LOCATION_TO_COUNTRY.items():
        if location in text_lower:
            return country
    return ""


def _detect_industry(text: str) -> str:
    """Sektör tespiti."""
    text_lower = text.lower()
    for keyword, industry in INDUSTRY_KEYWORDS.items():
        if keyword.lower() in text_lower:
            return industry
    return ""


def _detect_organizer(text: str) -> str:
    """Organizatör tespiti."""
    text_lower = text.lower()
    for keyword, name in KNOWN_ORGANIZERS.items():
        if keyword in text_lower:
            return name
    return ""


def _get_signal_reason(signal_tag: str) -> str:
    """Sinyal etiketinden satış nedeni üret."""
    reasons = {
        "Genişleme":        "Yeni alan = yeni stand ihtiyacı",
        "Yeni Salon":       "Yeni salon = onlarca yeni stand fırsatı",
        "Yeni Pavilyon":    "Yeni pavilyon = tam donanım kurulum işi",
        "Ülke Pavilyonu":   "Ülke pavilyonu = büyük metraj + diplomatik bütçe",
        "Venue Genişleme":  "Venue genişleme = uzun vadeli stand kapasitesi artışı",
        "Rekor Katılım":    "Rekor katılım = artan stand talebi",
        "Rekor Katılımcı":  "Rekor exhibitor = daha fazla stand siparişi",
        "Rekor":            "Rekor büyüklük = büyük stand bütçeleri",
        "Katılımcı Artışı": "Artan katılımcı = yeni müşteri havuzu",
        "Stand Kurulum":    "Direkt stand/kurulum sinyali",
        "Stand Tasarım":    "Tasarım talebi = teklif fırsatı",
        "İhale":            "İhale/tender = doğrudan teklif ver",
        "Kurulum":          "Fit-out işi = kurulum ekibi gönder",
        "Yeni Fuar Lansmanı": "Yeni fuar = sıfırdan stand üretimi fırsatı",
        "İlk Kez":          "İlk edisyon = tüm exhibitor'lar yeni stand yaptıracak",
        "Ortaklık":         "Ortaklık = network + iş geliştirme",
        "Ortak Organizasyon": "Co-located = çapraz satış fırsatı",
        "Tükendi":          "Sold out = güçlü talep, premium fiyat",
        "Alan":             "Büyük alan = büyük metraj stand fırsatı",
        "İş Sinyali":       "Aktif ticari faaliyet sinyali",
        "İzle":             "Yakın takipte tut",
    }
    return reasons.get(signal_tag, "Ticari potansiyel mevcut")


# ═══════════════════════════════════════════════════════════════════════════
# 5. ANA FONKSİYON — Lead üret
# ═══════════════════════════════════════════════════════════════════════════

def generate_lead(article: dict) -> dict:
    """
    Bir 🟢/🟠 haberden satış lead'i üret.

    Döndürür:
        {
            "event_name": str,
            "country": str,
            "industry": str,
            "organizer": str,
            "signal_tag": str,
            "reason": str,
            "strategy": dict,
            "offer": dict,
        }
    """
    title = article.get("title", "")
    summary = article.get("summary") or ""
    text = title + " " + summary
    signal_tag = article.get("signal_tag", "")

    # Extraction
    event    = _detect_event_name(text)
    country  = _detect_country(text)
    industry = _detect_industry(text)
    organizer = _detect_organizer(text)
    reason   = _get_signal_reason(signal_tag)

    # Strateji & teklif
    strategy = COUNTRY_STRATEGY.get(country, DEFAULT_STRATEGY)
    offer    = INDUSTRY_OFFER.get(industry, DEFAULT_OFFER)

    lead = {
        "event_name": event,
        "country":    country,
        "industry":   industry,
        "organizer":  organizer,
        "signal_tag": signal_tag,
        "reason":     reason,
        "strategy":   strategy,
        "offer":      offer,
    }

    article["lead"] = lead
    return lead
