"""
Stand & Expo İş Fırsatı Dedektörü v3

Tek soru: "Bu haberi görünce stand, pavilion, build-up,
kurulum, teklif, network fırsatı çıkar mı?"

Çıktı:
  🟢 FIRSAT     → Doğrudan ticari aksiyon potansiyeli
  🟠 İZLE       → Yakın takipte tut (opsiyonel)
  🔴 GEÇME      → Gönderme

Kurallar:
  1. Fuar/expo bağlamı yoksa → 🔴
  2. Fuar bağlamı var ama ticari sinyal yoksa → 🔴
  3. Tüketici/kamu fuarı → 🔴
  4. A (fuar bağlamı) + B (ticari sinyal) → 🟠
  5. A + B + C (B2B/endüstri ölçeği) → 🟢
"""

from config import HIGH_VALUE_FAIRS


# ── Sinyal tipleri ─────────────────────────────────────────────────────────
SIGNAL_OPPORTUNITY = "opportunity"   # 🟢
SIGNAL_WATCH       = "watch"         # 🟠
SIGNAL_SKIP        = "skip"          # 🔴

SIGNAL_META = {
    SIGNAL_OPPORTUNITY: {"icon": "🟢", "label": "FIRSAT"},
    SIGNAL_WATCH:       {"icon": "🟠", "label": "İZLE"},
    SIGNAL_SKIP:        {"icon": "🔴", "label": "GEÇME"},
}


# ═══════════════════════════════════════════════════════════════════════════
# A. FUAR BAĞLAMI — bunlardan en az biri zorunlu
# ═══════════════════════════════════════════════════════════════════════════
FAIR_CONTEXT = [
    # EN
    "exhibition", "exhibitor", "exhibit ",
    "trade show", "tradeshow", "trade fair",
    "expo ", "exposition",
    "fairground", "convention center", "convention centre",
    "congress center", "congress centre",
    "pavilion", "booth", "stand ",
    "venue", "show floor",
    "exhibition hall", "exhibition center", "exhibition centre",
    "organizer", "organiser",
    "stand builder", "booth contractor",
    "exhibit design", "stand design",
    # TR
    "fuar", "fuarı", "fuarda", "fuarcılık",
    "ticaret fuarı", "ihtisas fuarı",
    "fuar alanı", "fuar merkezi",
    "stant", "kongre merkezi",
    # DE
    "messe", "messegelände", "messehalle", "aussteller",
    # FR
    "salon professionnel", "foire",
    # ES
    "feria", "exposición",
    # IT
    "fiera", "salone",
]

# ═══════════════════════════════════════════════════════════════════════════
# B. TİCARİ SİNYAL — stand/booth/pavilion işi potansiyeli
# ═══════════════════════════════════════════════════════════════════════════
COMMERCIAL_SIGNALS = [
    # Genişleme / büyüme → daha fazla stand demek
    "expansion", "expanding", "new hall", "new pavilion",
    "country pavilion", "national pavilion",
    "venue expansion", "new exhibition center",
    "new convention center",
    "groundbreaking", "inaugurat",
    # Katılımcı artışı → daha fazla stand siparişi
    "exhibitor increase", "exhibitor growth",
    "record attendance", "record number", "record exhibitor",
    "record-breaking", "largest ever", "biggest ever",
    "sold out", "oversubscribed", "fully booked",
    "exhibitor registration", "exhibitor list",
    # Stand / kurulum direkt sinyalleri
    "stand builder", "booth contractor", "booth design",
    "stand design", "exhibit design", "fit-out", "fit out",
    "build-up", "build up", "shell scheme",
    "exhibition construction", "stand construction",
    "square meter", "sqm", "gross area",
    # İş / sözleşme
    "contract awarded", "tender",
    "co-located", "co-location",
    "new launch", "first edition", "debut",
    "partnership", "joint venture",
    # TR
    "genişleme", "yeni salon", "yeni pavilyon",
    "rekor katılım", "rekor katılımcı", "rekor ziyaretçi",
    "yatırım", "uluslararası katılım",
    "ihale", "metrekare", "brüt alan",
    "kapasite artışı", "yeni fuar alanı",
    "stand kurulum", "stand üretim",
    # DE
    "rekordbesuch", "erweiterung", "neue halle",
    "rekordbeteiligung",
]

# ═══════════════════════════════════════════════════════════════════════════
# C. B2B / ENDÜSTRİ ÖLÇEĞİ — büyük ticari fuar sinyali
# ═══════════════════════════════════════════════════════════════════════════
B2B_SCALE_SIGNALS = [
    # Sektörler (stand işi çıkan büyük endüstriler)
    "manufacturing", "industrial", "machinery",
    "automotive", "medical", "healthcare", "pharma",
    "technology", "IT ", "defense", "defence",
    "energy", "oil and gas", "mining",
    "construction", "building materials",
    "food processing", "packaging", "logistics",
    "agriculture", "textile", "chemical",
    "aerospace", "maritime", "mobility",
    # Ölçek
    "international", "global", "worldwide",
    "trade-only", "b2b", "business-to-business",
    "industry", "professional",
    # TR
    "uluslararası", "endüstri", "sanayi", "savunma",
    "otomotiv", "medikal", "enerji", "gıda",
    "makine", "tekstil", "kimya", "ambalaj",
]

# ═══════════════════════════════════════════════════════════════════════════
# TÜKETİCİ / KAMU FUARLARI — direkt ele (stand işi çıkmaz)
# ═══════════════════════════════════════════════════════════════════════════
CONSUMER_FAIR_BLOCK = [
    # Kültür / eğitim
    "book fair", "kitap fuarı", "book expo",
    "education fair", "eğitim fuarı", "career fair",
    "job fair", "science fair",
    # Tüketici
    "food festival", "beer festival", "wine fair",
    "wedding fair", "wedding expo", "bridal",
    "craft fair", "flea market", "bazaar",
    "hobby fair", "hobby expo",
    # Sanat / eğlence
    "art fair", "art exhibition", "art expo",
    "music festival", "film festival",
    "comic con", "anime expo", "gaming expo",
    "fan expo", "fan convention", "pop culture",
    # Kamu / yerel
    "county fair", "state fair", "public fair",
    "municipal fair", "charity", "charity fair",
    "cultural festival", "heritage",
    # Spor
    "exhibition match", "exhibition game", "boxing exhibition",
    # TR
    "sanat sergisi", "resim sergisi", "heykel sergisi",
    "fotoğraf sergisi", "bienal", "galeri",
    "halk fuarı", "belediye",
    # Genel alakasız
    "vanity fair", "celebrity", "ticket sale",
    "marathon", "run for",
    "stock market", "share price", "quarterly earnings",
    "lawsuit", "class action", "data breach",
]

# ── Alt etiketler ──────────────────────────────────────────────────────────
OPPORTUNITY_LABELS = {
    "expansion":         "Genişleme",
    "expanding":         "Genişleme",
    "new hall":          "Yeni Salon",
    "new pavilion":      "Yeni Pavilyon",
    "country pavilion":  "Ülke Pavilyonu",
    "national pavilion": "Ülke Pavilyonu",
    "venue expansion":   "Venue Genişleme",
    "new exhibition center": "Yeni Fuar Merkezi",
    "groundbreaking":    "Temel Atma",
    "inaugurat":         "Açılış",
    "record attendance": "Rekor Katılım",
    "record exhibitor":  "Rekor Katılımcı",
    "record-breaking":   "Rekor",
    "largest ever":      "Rekor",
    "exhibitor increase":"Katılımcı Artışı",
    "exhibitor growth":  "Katılımcı Artışı",
    "sold out":          "Tükendi",
    "stand builder":     "Stand Kurulum",
    "booth contractor":  "Stand Kurulum",
    "booth design":      "Stand Tasarım",
    "stand design":      "Stand Tasarım",
    "fit-out":           "Kurulum",
    "contract awarded":  "İhale",
    "tender":            "İhale",
    "first edition":     "Yeni Fuar Lansmanı",
    "debut":             "İlk Kez",
    "new launch":        "Yeni Lansman",
    "co-located":        "Ortak Organizasyon",
    "partnership":       "Ortaklık",
    "square meter":      "Alan",
    "sqm":               "Alan",
    # TR
    "genişleme":         "Genişleme",
    "yeni salon":        "Yeni Salon",
    "rekor katılım":     "Rekor Katılım",
    "rekor katılımcı":   "Rekor Katılımcı",
    "ihale":             "İhale",
    "metrekare":         "Alan",
    "stand kurulum":     "Stand Kurulum",
    "yeni fuar alanı":   "Yeni Fuar Alanı",
    # DE
    "rekordbesuch":      "Rekor Ziyaret",
    "erweiterung":       "Genişleme",
    "neue halle":        "Yeni Salon",
}


# ═══════════════════════════════════════════════════════════════════════════
# ANA FONKSİYONLAR
# ═══════════════════════════════════════════════════════════════════════════

def _has_fair_context(text: str) -> bool:
    """Metinde fuar/expo bağlamı var mı?"""
    for kw in FAIR_CONTEXT:
        if kw.lower() in text:
            return True
    for name in HIGH_VALUE_FAIRS:
        if name.lower() in text:
            return True
    return False


def _is_consumer_fair(text: str) -> bool:
    """Tüketici/kamu fuarı mı? (Stand işi çıkmaz)"""
    for kw in CONSUMER_FAIR_BLOCK:
        if kw.lower() in text:
            return True
    return False


def _find_commercial_signals(text: str) -> tuple[int, str]:
    """Ticari sinyal sayısı ve en iyi etiket."""
    hits = 0
    label = ""
    for kw in COMMERCIAL_SIGNALS:
        kw_lower = kw.lower()
        if kw_lower in text:
            hits += 1
            if not label and kw_lower in OPPORTUNITY_LABELS:
                label = OPPORTUNITY_LABELS[kw_lower]
    return hits, label


def _has_b2b_scale(text: str) -> bool:
    """B2B / endüstri ölçeği sinyali var mı?"""
    for kw in B2B_SCALE_SIGNALS:
        if kw.lower() in text:
            return True
    return False


def classify_article(article: dict) -> dict:
    """
    Stand & Expo İş Fırsatı Sınıflandırması.

    Tek soru: "Bu haberden stand/pavilion/kurulum işi çıkar mı?"

    Kurallar:
      1. Tüketici fuarı → 🔴
      2. Fuar bağlamı yok → 🔴
      3. Fuar bağlamı var + ticari sinyal yok → 🔴
      4. A (fuar, başlıkta) + B (ticari sinyal) → 🟠 İZLE
      5. A + B + C (B2B ölçek) → 🟢 FIRSAT
    """
    title = article.get("title", "").lower()
    summary = (article.get("summary") or "").lower()
    text = title + " " + summary

    # ── 1. Tüketici/kamu fuarı → direkt 🔴 ───────────────────────────────
    if _is_consumer_fair(text):
        return _make(SIGNAL_SKIP)

    # ── 2. Fuar bağlamı zorunlu ───────────────────────────────────────────
    has_context_title = _has_fair_context(title)
    has_context_any   = _has_fair_context(text)

    if not has_context_any:
        return _make(SIGNAL_SKIP)

    # ── 3. Ticari sinyal zorunlu ──────────────────────────────────────────
    biz_count, biz_label = _find_commercial_signals(text)

    if biz_count == 0:
        # Fuar haberi ama ticari sinyal yok → gösterme
        return _make(SIGNAL_SKIP)

    # ── 4. A + B var → en az 🟠 ──────────────────────────────────────────
    if not has_context_title:
        # Bağlam sadece özette → 🟠 (zayıf)
        return _make(SIGNAL_WATCH, biz_label or "İzle")

    # ── 5. A (başlık) + B + C → 🟢 ───────────────────────────────────────
    has_scale = _has_b2b_scale(text)

    if has_scale or biz_count >= 2:
        return _make(SIGNAL_OPPORTUNITY, biz_label or "İş Fırsatı")

    # ── 6. A (başlık) + B ama C yok → 🟠 ─────────────────────────────────
    return _make(SIGNAL_WATCH, biz_label or "İzle")


def _make(signal_type: str, tag: str = "") -> dict:
    meta = SIGNAL_META[signal_type]
    return {
        "signal_type":  signal_type,
        "signal_icon":  meta["icon"],
        "signal_label": meta["label"],
        "signal_tag":   tag,
    }


def signal_sort_key(article: dict) -> int:
    """Sıralama: 🟢 → 0, 🟠 → 1."""
    sig = article.get("signal_type", SIGNAL_WATCH)
    if sig == SIGNAL_OPPORTUNITY:
        return 0
    return 1
