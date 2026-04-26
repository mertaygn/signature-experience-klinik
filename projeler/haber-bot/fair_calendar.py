"""
Global Expo Radar — Fuar Takvimi & Proaktif Satış Zaman Yönetimi

"Bugün kime yazarsam 3 ay sonra iş alırım?"

Kurallar:
  120–180 gün → 🔥 ALTIN ZAMAN (outreach başla)
  60–120 gün  → 🟡 HALA FIRSAT (hızlan)
  30–60 gün   → ⚠️ ZOR (son şans)
  <30 gün     → ❌ GEÇ
"""

from datetime import date, timedelta


# ═══════════════════════════════════════════════════════════════════════════
# GLOBAL FUAR TAKVİMİ — 2025/2026 Büyük B2B Fuarları
# ═══════════════════════════════════════════════════════════════════════════

FAIR_CALENDAR = [
    # ─── Almanya ──────────────────────────────────────────────────────────
    {
        "name": "Hannover Messe",
        "city": "Hannover", "country": "Almanya",
        "sector": "Endüstri / Üretim",
        "start": "2026-04-20", "end": "2026-04-24",
        "organizer": "Deutsche Messe",
        "slug": "hannover_messe",
        "exhibitor_url": "https://www.hannovermesse.de/en/exhibition/exhibitors-products/",
        "size": "6000+ exhibitor",
    },
    {
        "name": "Automechanika Frankfurt",
        "city": "Frankfurt", "country": "Almanya",
        "sector": "Otomotiv",
        "start": "2026-09-08", "end": "2026-09-12",
        "organizer": "Messe Frankfurt",
        "slug": "automechanika",
        "exhibitor_url": "https://automechanika.messefrankfurt.com/frankfurt/en/exhibitor-search.html",
        "size": "4800+ exhibitor",
    },
    {
        "name": "Bauma",
        "city": "München", "country": "Almanya",
        "sector": "İnşaat / Makine",
        "start": "2025-04-07", "end": "2025-04-13",
        "organizer": "Messe München",
        "slug": "bauma",
        "size": "3500+ exhibitor",
    },
    {
        "name": "MEDICA",
        "city": "Düsseldorf", "country": "Almanya",
        "sector": "Medikal",
        "start": "2025-11-10", "end": "2025-11-13",
        "organizer": "Messe Düsseldorf",
        "slug": "medica",
        "size": "5000+ exhibitor",
    },
    {
        "name": "Ambiente",
        "city": "Frankfurt", "country": "Almanya",
        "sector": "Tüketici / Yaşam",
        "start": "2026-02-06", "end": "2026-02-10",
        "organizer": "Messe Frankfurt",
        "slug": "ambiente",
        "size": "4500+ exhibitor",
    },
    {
        "name": "ISH",
        "city": "Frankfurt", "country": "Almanya",
        "sector": "Enerji / HVAC",
        "start": "2025-03-17", "end": "2025-03-21",
        "organizer": "Messe Frankfurt",
        "slug": "ish",
        "size": "2400+ exhibitor",
    },
    {
        "name": "DRUPA",
        "city": "Düsseldorf", "country": "Almanya",
        "sector": "Baskı / Ambalaj",
        "start": "2028-05-28", "end": "2028-06-07",
        "organizer": "Messe Düsseldorf",
        "slug": "drupa",
        "size": "1800+ exhibitor",
    },
    {
        "name": "Anuga",
        "city": "Köln", "country": "Almanya",
        "sector": "Gıda",
        "start": "2025-10-04", "end": "2025-10-08",
        "organizer": "Koelnmesse",
        "slug": "anuga",
        "size": "7500+ exhibitor",
    },
    {
        "name": "interzum",
        "city": "Köln", "country": "Almanya",
        "sector": "Mobilya / Ahşap",
        "start": "2025-05-20", "end": "2025-05-23",
        "organizer": "Koelnmesse",
        "slug": "interzum",
        "size": "1800+ exhibitor",
    },
    {
        "name": "K Fair",
        "city": "Düsseldorf", "country": "Almanya",
        "sector": "Plastik / Kauçuk",
        "start": "2025-10-08", "end": "2025-10-15",
        "organizer": "Messe Düsseldorf",
        "slug": "k_fair",
        "size": "3000+ exhibitor",
    },
    {
        "name": "EuroShop",
        "city": "Düsseldorf", "country": "Almanya",
        "sector": "Perakende / Mağazacılık",
        "start": "2026-02-22", "end": "2026-02-26",
        "organizer": "Messe Düsseldorf",
        "slug": "euroshop",
        "size": "2200+ exhibitor",
    },

    # ─── İtalya ───────────────────────────────────────────────────────────
    {
        "name": "Salone del Mobile",
        "city": "Milano", "country": "İtalya",
        "sector": "Mobilya / Tasarım",
        "start": "2026-04-21", "end": "2026-04-26",
        "organizer": "Fiera Milano",
        "slug": "salone_mobile",
        "size": "2000+ exhibitor",
    },
    {
        "name": "Host Milano",
        "city": "Milano", "country": "İtalya",
        "sector": "Ağırlama / HoReCa",
        "start": "2025-10-17", "end": "2025-10-21",
        "organizer": "Fiera Milano",
        "slug": "host_milano",
        "size": "2000+ exhibitor",
    },
    {
        "name": "EIMA International",
        "city": "Bologna", "country": "İtalya",
        "sector": "Tarım / Makine",
        "start": "2026-11-11", "end": "2026-11-15",
        "organizer": "FederUnacoma",
        "slug": "eima",
        "size": "1900+ exhibitor",
    },

    # ─── BAE / Körfez ────────────────────────────────────────────────────
    {
        "name": "GITEX Global",
        "city": "Dubai", "country": "BAE",
        "sector": "Teknoloji",
        "start": "2025-10-13", "end": "2025-10-17",
        "organizer": "DWTC",
        "slug": "gitex",
        "size": "6000+ exhibitor",
    },
    {
        "name": "Arab Health",
        "city": "Dubai", "country": "BAE",
        "sector": "Medikal",
        "start": "2026-01-26", "end": "2026-01-29",
        "organizer": "Informa Markets",
        "slug": "arab_health",
        "size": "3000+ exhibitor",
    },
    {
        "name": "The Big 5",
        "city": "Dubai", "country": "BAE",
        "sector": "İnşaat",
        "start": "2025-11-26", "end": "2025-11-28",
        "organizer": "DMG Events",
        "slug": "big5_dubai",
        "size": "2000+ exhibitor",
    },
    {
        "name": "IDEX",
        "city": "Abu Dhabi", "country": "BAE",
        "sector": "Savunma",
        "start": "2025-02-17", "end": "2025-02-21",
        "organizer": "ADNEC",
        "slug": "idex",
        "size": "1400+ exhibitor",
    },

    # ─── Türkiye ─────────────────────────────────────────────────────────
    {
        "name": "WIN Eurasia",
        "city": "Istanbul", "country": "Türkiye",
        "sector": "Endüstri / Üretim",
        "start": "2025-06-12", "end": "2025-06-15",
        "organizer": "Hannover Fairs Turkey",
        "slug": "win_eurasia",
        "exhibitor_url": "https://www.win-eurasia.com",
        "size": "1200+ exhibitor",
    },
    {
        "name": "IDEF",
        "city": "Istanbul", "country": "Türkiye",
        "sector": "Savunma",
        "start": "2025-05-27", "end": "2025-05-30",
        "organizer": "TÜYAP",
        "slug": "idef",
        "size": "1000+ exhibitor",
    },
    {
        "name": "SAHA EXPO",
        "city": "Istanbul", "country": "Türkiye",
        "sector": "Savunma / Havacılık",
        "start": "2024-10-22", "end": "2024-10-25",
        "organizer": "SAHA Istanbul",
        "slug": "saha_expo",
        "size": "700+ exhibitor",
    },
    {
        "name": "Eurasia Packaging",
        "city": "Istanbul", "country": "Türkiye",
        "sector": "Ambalaj",
        "start": "2025-10-22", "end": "2025-10-25",
        "organizer": "TÜYAP",
        "slug": "eurasia_packaging",
        "size": "800+ exhibitor",
    },

    # ─── Çin ─────────────────────────────────────────────────────────────
    {
        "name": "Canton Fair",
        "city": "Guangzhou", "country": "Çin",
        "sector": "Genel Ticaret",
        "start": "2025-10-15", "end": "2025-11-04",
        "organizer": "Canton Fair",
        "slug": "canton_fair",
        "size": "25000+ exhibitor",
    },
    {
        "name": "CMEF",
        "city": "Shanghai", "country": "Çin",
        "sector": "Medikal",
        "start": "2026-04-09", "end": "2026-04-12",
        "organizer": "Reed Sinopharm",
        "slug": "cmef",
        "size": "4500+ exhibitor",
    },

    # ─── Fransa ──────────────────────────────────────────────────────────
    {
        "name": "Paris Air Show",
        "city": "Paris", "country": "Fransa",
        "sector": "Havacılık / Uzay",
        "start": "2025-06-16", "end": "2025-06-22",
        "organizer": "SIAE",
        "slug": "paris_air_show",
        "size": "2400+ exhibitor",
    },
    {
        "name": "Intermat",
        "city": "Paris", "country": "Fransa",
        "sector": "İnşaat / Makine",
        "start": "2027-04-19", "end": "2027-04-24",
        "organizer": "Comexposium",
        "slug": "intermat",
        "size": "1400+ exhibitor",
    },

    # ─── İspanya ─────────────────────────────────────────────────────────
    {
        "name": "Mobile World Congress",
        "city": "Barcelona", "country": "İspanya",
        "sector": "Telekomünikasyon",
        "start": "2026-03-02", "end": "2026-03-05",
        "organizer": "GSMA",
        "slug": "mwc",
        "size": "2400+ exhibitor",
    },
    {
        "name": "Alimentaria",
        "city": "Barcelona", "country": "İspanya",
        "sector": "Gıda",
        "start": "2026-03-30", "end": "2026-04-02",
        "organizer": "Fira Barcelona",
        "slug": "alimentaria",
        "size": "3000+ exhibitor",
    },

    # ─── ABD ─────────────────────────────────────────────────────────────
    {
        "name": "CES",
        "city": "Las Vegas", "country": "ABD",
        "sector": "Teknoloji / Elektronik",
        "start": "2026-01-06", "end": "2026-01-09",
        "organizer": "CTA",
        "slug": "ces",
        "size": "4000+ exhibitor",
    },
    {
        "name": "CONEXPO-CON/AGG",
        "city": "Las Vegas", "country": "ABD",
        "sector": "İnşaat / Makine",
        "start": "2026-03-10", "end": "2026-03-14",
        "organizer": "AEM",
        "slug": "conexpo",
        "size": "2800+ exhibitor",
    },
    {
        "name": "PACK EXPO",
        "city": "Chicago", "country": "ABD",
        "sector": "Ambalaj",
        "start": "2025-09-29", "end": "2025-10-01",
        "organizer": "PMMI",
        "slug": "pack_expo",
        "size": "2500+ exhibitor",
    },

    # ─── İngiltere ───────────────────────────────────────────────────────
    {
        "name": "DSEI",
        "city": "London", "country": "İngiltere",
        "sector": "Savunma",
        "start": "2025-09-09", "end": "2025-09-12",
        "organizer": "Clarion Events",
        "slug": "dsei",
        "size": "1700+ exhibitor",
    },
    {
        "name": "Farnborough Airshow",
        "city": "London", "country": "İngiltere",
        "sector": "Havacılık",
        "start": "2026-07-20", "end": "2026-07-24",
        "organizer": "Farnborough International",
        "slug": "farnborough",
        "size": "1500+ exhibitor",
    },
]


# ═══════════════════════════════════════════════════════════════════════════
# ZAMAN KATMANLARI
# ═══════════════════════════════════════════════════════════════════════════

def classify_timing(days_until: int) -> dict:
    """Güne göre aksiyon zonu belirle."""
    if days_until >= 120:
        return {
            "zone": "🔥 ALTIN ZAMAN",
            "zone_code": "gold",
            "action": "Outreach HEMEN başla",
            "urgency": 5,
            "color": "🟢",
        }
    elif days_until >= 60:
        return {
            "zone": "🟡 HALA FIRSAT",
            "zone_code": "yellow",
            "action": "HIZLAN — bu hafta temas kur",
            "urgency": 4,
            "color": "🟡",
        }
    elif days_until >= 30:
        return {
            "zone": "⚠️ SON ŞANS",
            "zone_code": "orange",
            "action": "Acil temas — son dakika fırsatı",
            "urgency": 3,
            "color": "🟠",
        }
    elif days_until >= 0:
        return {
            "zone": "❌ GEÇ",
            "zone_code": "red",
            "action": "Çok geç — bir sonraki edisyona hazırlan",
            "urgency": 1,
            "color": "🔴",
        }
    else:
        return {
            "zone": "📋 GEÇMİŞ",
            "zone_code": "past",
            "action": "Geçmiş katılımcıları sonraki edisyon için kayıt",
            "urgency": 0,
            "color": "⬜",
        }


# ═══════════════════════════════════════════════════════════════════════════
# RADAR FONKSİYONLARI
# ═══════════════════════════════════════════════════════════════════════════

def get_upcoming_fairs(days_ahead: int = 180, min_days: int = 0) -> list[dict]:
    """
    Önümüzdeki X gün içindeki fuarları döndür.
    Her fuara days_until ve timing bilgisi ekler.
    """
    today = date.today()
    results = []

    for fair in FAIR_CALENDAR:
        try:
            start = date.fromisoformat(fair["start"])
        except (ValueError, KeyError):
            continue

        days_until = (start - today).days

        if min_days <= days_until <= days_ahead:
            entry = fair.copy()
            entry["days_until"] = days_until
            entry["timing"] = classify_timing(days_until)
            results.append(entry)

    # En yakından uzağa sırala
    results.sort(key=lambda x: x["days_until"])
    return results


def get_actionable_fairs() -> list[dict]:
    """
    Satış aksiyonu alınması gereken fuarları döndür.
    Sadece gold + yellow zondakiler (30-180 gün).
    """
    all_fairs = get_upcoming_fairs(days_ahead=180, min_days=30)
    return [f for f in all_fairs if f["timing"]["zone_code"] in ("gold", "yellow")]


def get_past_fairs_for_next_edition() -> list[dict]:
    """
    Geçmiş fuarlar — exhibitor listesi çek, sonraki edisyon için hazırlan.
    """
    today = date.today()
    results = []

    for fair in FAIR_CALENDAR:
        try:
            start = date.fromisoformat(fair["start"])
        except (ValueError, KeyError):
            continue

        days_ago = (today - start).days
        if 0 < days_ago <= 365:  # Son 1 yılda gerçekleşmiş
            entry = fair.copy()
            entry["days_ago"] = days_ago
            entry["timing"] = classify_timing(-days_ago)
            results.append(entry)

    results.sort(key=lambda x: x["days_ago"])
    return results


def format_radar_telegram() -> str:
    """Haftalık Telegram radar raporu formatı."""
    lines = [
        "📡 <b>GLOBAL EXPO RADAR</b>",
        f"📅 {date.today().strftime('%d/%m/%Y')}",
        "━━━━━━━━━━━━━━━━━━",
    ]

    # Altın zaman fuarları
    actionable = get_actionable_fairs()
    if actionable:
        lines.append("\n🔥 <b>AKSİYON AL — Outreach Başla:</b>\n")

        for fair in actionable:
            timing = fair["timing"]
            days = fair["days_until"]
            country_flag = _get_flag(fair.get("country", ""))

            lines.append(
                f"{timing['color']} <b>{fair['name']}</b>"
            )
            lines.append(
                f"   {country_flag} {fair['city']} | {fair['sector']}"
            )
            lines.append(
                f"   📅 {fair['start']} | ⏱ {days} gün | {fair.get('size', '')}"
            )
            lines.append(
                f"   💡 {timing['action']}"
            )
            lines.append("")

    # Yaklaşan (30-60 gün)
    urgent = get_upcoming_fairs(days_ahead=60, min_days=0)
    urgent = [f for f in urgent if f["timing"]["zone_code"] == "orange"]
    if urgent:
        lines.append("⚠️ <b>SON ŞANS:</b>\n")
        for fair in urgent:
            lines.append(
                f"🟠 {fair['name']} — {fair['days_until']} gün | {fair['city']}"
            )
        lines.append("")

    # Özet
    total_upcoming = len(get_upcoming_fairs(days_ahead=365))
    total_gold = len([f for f in actionable if f["timing"]["zone_code"] == "gold"])
    total_yellow = len([f for f in actionable if f["timing"]["zone_code"] == "yellow"])

    lines.append(f"📊 <b>Özet:</b> {total_upcoming} fuar takipte")
    lines.append(f"   🔥 {total_gold} altın zaman | 🟡 {total_yellow} hala fırsat")
    lines.append(f"\n🤖 <i>Detay: python main.py radar</i>")

    return "\n".join(lines)


def _get_flag(country: str) -> str:
    """Ülke bayrağı emoji."""
    flags = {
        "Almanya": "🇩🇪", "İtalya": "🇮🇹", "Fransa": "🇫🇷", "İspanya": "🇪🇸",
        "BAE": "🇦🇪", "Türkiye": "🇹🇷", "Çin": "🇨🇳", "ABD": "🇺🇸",
        "İngiltere": "🇬🇧", "Japonya": "🇯🇵", "Hindistan": "🇮🇳",
    }
    return flags.get(country, "🌐")
