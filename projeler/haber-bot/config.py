import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# NewsAPI
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY")

# Zamanlama
DAILY_SEND_HOUR = 9    # 09:00 Türkiye saati
DAILY_SEND_MINUTE = 0

# Haber limitleri
MAX_NEWS_PER_DAY = 10      # Az ama isabetli (3-8 ideal)
MIN_NEWS_TO_SEND = 1       # Bu kadar yoksa sessiz kal
DB_CLEANUP_DAYS = 30       # Kaç gün önceki kayıtlar silinsin

# Minimum keyword skor eşiği (düşük güvenilirlik kaynaklarda daha yüksek)
MIN_SCORE_TRUSTED = 1      # TSNN, UFI, Trade Fair Times gibi kaynaklar
MIN_SCORE_GENERAL = 3      # NewsAPI genel kaynaklar
MIN_SCORE_PRESS_RELEASE = 4  # PR Newswire/GlobeNewswire — daha sıkı, gürültü filtresi

# ── FUAR ANAHTAR KELİMELERİ — ÇOK DİLLİ ──────────────────────────────────

# 🇹🇷 Türkçe
KEYWORDS_TR = [
    "fuar", "fuarı", "fuarda", "fuarcılık", "fuarlar",
    "uluslararası fuar",
    "ihtisas fuarı", "ticaret fuarı", "yurt dışı fuar",
    "fuar organizasyonu", "fuar standı", "fuar katılımcı",
    "TÜYAP", "CNR expo", "İstanbul fuar", "Ankara fuar",
    "fuar dergisi", "fuar sektörü", "expo", "expoya",
    # ── YENİ: Ticari sinyal ──
    "fuar katılımcı sayısı", "yeni fuar alanı",
    "fuar yatırımı", "sergi alanı", "fuar genişleme",
]

# 🇬🇧 İngilizce
KEYWORDS_EN = [
    "trade show", "tradeshow", "trade fair", "trade expo",
    "exhibition", "exhibitor", "exhibiting", "exhibit hall",
    "expo", "world expo", "international expo",
    "fair", "international fair", "industry fair",
    "convention", "convention center", "congress",
    "pavilion", "booth", "stand design",
    "event industry", "MICE industry", "event organizer",
    "show floor", "trade event", "b2b event",
    "hannover messe", "bauma", "drupa", "interpack",
    "IMTS", "SEMA", "automechanika", "medica",
    "arab health", "gitex", "CES trade", "ISE exhibition",
    "world fair", "expo 2025", "expo 2026",
    "IAEE", "UFI", "TSNN", "exhibitor magazine",
    # ── YENİ: Ticari sinyal keyword'leri ──
    "exhibitor growth", "new pavilion", "country pavilion",
    "expo expansion", "venue expansion", "exhibition build",
    "stand contractor", "booth design company",
    "trade fair construction", "exhibit design",
    "exhibition space", "show management",
]

# 🇩🇪 Almanca
KEYWORDS_DE = [
    "messe", "fachmesse", "weltmesse", "ausstellung",
    "ausstellungswesen", "messegelände", "messehalle",
    "aussteller", "messestand", "handelsmesse",
    "hannover messe", "frankfurter messe", "düsseldorf messe",
    "Munich messe", "messe münchen", "messe frankfurt",
    "messe berlin", "messe köln", "messe stuttgart",
    "messe düsseldorf", "messe hamburg",
]

# 🇫🇷 Fransızca
KEYWORDS_FR = [
    "salon professionnel", "salon international",
    "foire internationale", "foire exposition",
    "exposition universelle", "exposant",
    "salon de l'auto", "salon du livre",
    "paris expo", "palais des congrès",
]

# 🇪🇸 İspanyolca
KEYWORDS_ES = [
    "feria internacional", "feria comercial",
    "exposición internacional", "salón internacional",
    "expositor", "exhibición", "feria de muestras",
    "ifema", "fitur", "feria de barcelona",
]

# 🇮🇹 İtalyanca
KEYWORDS_IT = [
    "fiera internazionale", "salone internazionale",
    "esposizione", "mostra convegno", "fieramilano",
    "salone del mobile", "fiera di bologna",
]

# 🇦🇪 Arapça
KEYWORDS_AR = [
    "معرض", "معرض دولي", "معرض تجاري", "جيتكس",
    "معارض", "سيتي سكيب", "أرابيان ترافيل ماركت",
    "أبوظبي الدولي", "دبي إكسبو", "عرض تجاري",
]

# 🇨🇳 Çince (ana fuarlar için)
KEYWORDS_ZH = [
    "展览", "展会", "博览会", "展销会",
    "国际展览", "广交会", "进博会",
]

# Tüm keyword'leri birleştir
FAIR_KEYWORDS = (
    KEYWORDS_TR + KEYWORDS_EN + KEYWORDS_DE +
    KEYWORDS_FR + KEYWORDS_ES + KEYWORDS_IT +
    KEYWORDS_AR + KEYWORDS_ZH
)

# ══ SPESIFİK FUAR İSİMLERİ (yüksek ağırlık — başlıkta geçerse otomatik geçer) ══
HIGH_VALUE_FAIRS = [
    "Touch Taiwan", "Asia Pacific Maritime", "Sporting Goods Fair",
    "Cosmoprof", "Equiplast", "Pitti Uomo", "Pitti Immagine",
    "IDEF", "Eurasia Boat Show", "WIN Eurasia",
    "Motek", "Productronica", "Electronica", "Formnext",
    "AERO Friedrichshafen", "ILA Berlin", "InnoTrans",
    "Anuga", "ISM Cologne", "Ambiente", "Heimtextil",
    "Canton Fair", "CIIE", "CIFF", "Fitur",
    "IDEX", "NAVDEX", "ISNR", "Gulfood",
    "The Big 5", "Beautyworld", "Paperworld",
    "Computex", "Semicon", "Electronica", "Light + Building",
    # ── YENİ: Organizatör isimleri (başlıkta geçerse otomatik yüksek skor) ──
    "Messe Frankfurt", "RX Global", "Koelnmesse", "Fiera Milano",
    "Informa Markets", "Dubai World Trade", "Fira Barcelona",
    "IFEMA", "TÜYAP", "CNR Expo",
]

# ── DIŞLAMA KELİMELERİ (alakasız "fair/expo" kullanımları) ────────────────
EXCLUDE_KEYWORDS = [
    # Kariyer / eğitim fuarları
    "career fair", "job fair", "science fair",
    # ABD yerel festivalleri
    "county fair", "state fair",
    # Dergi / marka adı
    "vanity fair",
    # Sanat sergileri (ticaret fuarı değil)
    "art exhibition", "museum exhibition",
    "sanat sergisi", "resim sergisi", "heykel sergisi",
    "fotoğraf sergisi", "dijital sergi", "çağdaş sanat",
    "cermodern", "galeri", "bienal", "bienali",
    "retrospektif", "koleksiyon sergisi",
    "painting exhibition", "sculpture", "gallery exhibition",
    "art gallery", "retrospective", "art show",
    # Fan / eğlence etkinlikleri
    "fan expo", "fan convention", "comic con", "comic-con",
    "comiccon", "anime expo", "anime convention",
    "gaming expo", "game fest", "dream fest",
    "fan fest", "pop culture",
    # Spor
    "exhibition match", "exhibition game", "boxing exhibition",
    # Güvenlik / siyaset / alakasız
    "hackers accessed", "data breach", "medical records",
    "halloween", "world record", "Medicaid", "Netanyahu", "pirat",
]

# Güvenilir kaynaklar (düşük skor eşiği)
TRUSTED_SOURCES = [
    "UFI", "Trade Fair Times", "Exhibitor Magazine",
    "Event Marketer", "Google News TR", "Fuar",
    "Trade Show Executive", "Exhibit City News",
    "Event Industry News", "Skift Meetings",
    "Exhibition World",
]

# ══ TİCARİ SİNYAL SİSTEMİ ════════════════════════════════════════════════

# 🟢 İŞ FIRSATI — bu keyword'ler geçerse skorlama boost alır
HIGH_VALUE_SIGNALS = [
    # EN — genişleme / büyüme
    "expansion", "expanding", "new hall", "new pavilion",
    "country pavilion", "national pavilion",
    "exhibitor increase", "record attendance", "record number",
    "record-breaking", "largest ever", "biggest ever",
    # EN — yatırım / inşaat
    "investment", "construction", "venue expansion",
    "new exhibition center", "new convention center",
    "groundbreaking", "inaugurat",
    # EN — iş/sözleşme sinyalleri
    "international participation", "contract awarded",
    "stand builder", "booth contractor", "square meter",
    "co-located", "partnership", "joint venture",
    "exhibitor registration", "sold out", "oversubscribed",
    # TR — genişleme / büyüme
    "genişleme", "yeni salon", "rekor katılım", "rekor ziyaretçi",
    "yatırım", "uluslararası katılım", "ihale", "metrekare",
    "kapasite artışı", "yeni fuar alanı",
    # DE
    "rekordbesuch", "erweiterung", "neue halle",
]

# 🔴 DÜŞÜK DEĞER — puan düşürücü (skor negatife düşerse elenir)
LOW_VALUE_SIGNALS = [
    # Tüketici / lifestyle
    "food festival", "wedding fair", "wedding expo",
    "music festival", "film festival", "beer festival",
    "wine fair", "craft fair", "flea market",
    "charity", "marathon", "run for",
    # Eğlence / fan
    "fan event", "ticket sale", "celebrity",
    "cosplay", "meet and greet",
    # Finans / alakasız
    "stock market", "share price", "quarterly earnings",
    "lawsuit", "class action", "securities fraud",
]
