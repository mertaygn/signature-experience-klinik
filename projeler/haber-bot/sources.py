# ═══════════════════════════════════════════════════════════════════════════
# HABER KAYNAKLARI — Ticari Sinyal Odaklı
# ═══════════════════════════════════════════════════════════════════════════

# ── 1. Güvenilir Sektör RSS Kaynakları ────────────────────────────────────

RSS_FEEDS = [
    # ── Mevcut (çalışan) ──────────────────────────────────────────────────
    {
        "url": "https://www.ufi.org/feed/",
        "name": "UFI - Global Exhibition Industry",
        "lang": "en", "trust": "trusted",
    },
    {
        "url": "https://www.tradefairtimes.com/feed/",
        "name": "Trade Fair Times",
        "lang": "en", "trust": "trusted",
    },
    {
        "url": "https://www.eventmarketer.com/feed/",
        "name": "Event Marketer",
        "lang": "en", "trust": "trusted",
    },
    {
        "url": "https://www.exhibitionworld.co.uk/feed",
        "name": "Exhibition World",
        "lang": "en", "trust": "trusted",
    },

    # ── YENİ: Sektörel Medya ─────────────────────────────────────────────
    {
        "url": "https://tradeshowexecutive.com/feed",
        "name": "Trade Show Executive",
        "lang": "en", "trust": "trusted",
    },
    {
        "url": "https://exhibitcitynews.com/feed/",
        "name": "Exhibit City News",
        "lang": "en", "trust": "trusted",
    },
    {
        "url": "https://eventindustrynews.com/feed",
        "name": "Event Industry News",
        "lang": "en", "trust": "trusted",
    },
    {
        "url": "https://meetings.skift.com/feed",
        "name": "Skift Meetings",
        "lang": "en", "trust": "trusted",
    },

    # ── YENİ: Press Release Aggregator'lar (HAM SİNYAL) ──────────────────
    {
        "url": "https://www.prnewswire.com/rss/news-releases/trade-show-news/trade-show-news-list.rss",
        "name": "PR Newswire - Trade Show",
        "lang": "en", "trust": "press_release",
    },
    {
        "url": "https://www.globenewswire.com/RssFeed/subjectcode/14-Conference%20Call%20and%20Webcast%20Announcements/feedTitle/GlobeNewswire%20-%20Conference%20Call%20and%20Webcast%20Announcements",
        "name": "GlobeNewswire - Events",
        "lang": "en", "trust": "press_release",
    },
]

# ── 2. NewsAPI — Dil + Ticari Sinyal Sorguları ────────────────────────────
# Her sorgu 1 API isteği = günde 11 istek (limit: 100/gün)

NEWSAPI_QUERIES = [
    # 🇬🇧 İngilizce — genel fuar
    {
        "q": '("trade show" OR "trade fair" OR "exhibition" OR "expo" OR "exhibitor") AND (industry OR international OR fair OR messe)',
        "language": "en",
        "label": "EN: Trade Show / Exhibition",
    },
    # 🇬🇧 İngilizce — büyük fuarlar
    {
        "q": '"Hannover Messe" OR "Bauma" OR "Drupa" OR "Interpack" OR "Formnext" OR "SEMA" OR "IMTS" OR "Pack Expo" OR "GITEX" OR "Arab Health" OR "CES 2026" OR "ISE 2026" OR "Medica" OR "Automechanika"',
        "language": "en",
        "label": "EN: Büyük Fuarlar",
    },
    # 🇬🇧 İngilizce — endüstri/MICE
    {
        "q": '"convention center" OR "MICE industry" OR "event organizer" OR "exhibition industry" OR "trade event" OR "world expo" OR "UFI" OR "IAEE" OR "TSNN"',
        "language": "en",
        "label": "EN: Endüstri / MICE",
    },

    # ── YENİ: Organizatör Sinyalleri ─────────────────────────────────────
    {
        "q": '"Messe Frankfurt" OR "RX Global" OR "Koelnmesse" OR "Fiera Milano" OR "Informa Markets" OR "Dubai World Trade" OR "Fira Barcelona" OR "IFEMA"',
        "language": "en",
        "label": "EN: Organizatör Sinyalleri",
    },
    # ── YENİ: Venue & Genişleme ──────────────────────────────────────────
    {
        "q": '"new exhibition hall" OR "venue expansion" OR "new pavilion" OR "country pavilion" OR "expo expansion" OR "exhibition center" OR "fairground"',
        "language": "en",
        "label": "EN: Venue & Genişleme",
    },
    # ── YENİ: Stand & Kurulum ────────────────────────────────────────────
    {
        "q": '"booth design" OR "stand contractor" OR "exhibition build" OR "exhibitor growth" OR "trade fair construction" OR "exhibit design"',
        "language": "en",
        "label": "EN: Stand & Kurulum",
    },

    # 🇹🇷 Türkçe
    {
        "q": 'fuar OR "ihtisas fuarı" OR "ticaret fuarı" OR "uluslararası fuar" OR sergi OR TÜYAP OR "CNR expo" OR "fuar yatırımı" OR "yeni fuar alanı"',
        "language": "tr",
        "label": "TR: Fuar Haberleri",
    },
    # 🇩🇪 Almanca
    {
        "q": 'Messe OR Fachmesse OR Ausstellung OR Aussteller OR "Hannover Messe" OR "Messe Frankfurt" OR "Messe München" OR "Messe Düsseldorf"',
        "language": "de",
        "label": "DE: Messe / Fachmesse",
    },
    # 🇫🇷 Fransızca
    {
        "q": '"salon professionnel" OR "salon international" OR "foire internationale" OR "exposition internationale" OR exposant',
        "language": "fr",
        "label": "FR: Salon / Foire",
    },
    # 🇪🇸 İspanyolca
    {
        "q": '"feria internacional" OR "feria comercial" OR "exposición internacional" OR "salón internacional" OR IFEMA OR FITUR',
        "language": "es",
        "label": "ES: Feria Internacional",
    },
    # 🇮🇹 İtalyanca
    {
        "q": '"fiera internazionale" OR "salone internazionale" OR Fieramilano OR "Salone del Mobile" OR "fiera di Bologna" OR espositore',
        "language": "it",
        "label": "IT: Fiera Internazionale",
    },
]
