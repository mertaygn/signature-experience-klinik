"""
Haber toplayıcı:
1. NewsAPI.org — Ana kaynak (başlık + açıklama + kaynak + tarih)
2. Güvenilir RSS feed'leri — İkincil kaynak (TSNN, UFI, Trade Fair Times vb.)
"""

import time
import html
import re
import feedparser
import requests
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from datetime import datetime, timezone, timedelta

from config import FAIR_KEYWORDS, EXCLUDE_KEYWORDS, TRUSTED_SOURCES, NEWSAPI_KEY
from config import MIN_SCORE_TRUSTED, MIN_SCORE_GENERAL, MIN_SCORE_PRESS_RELEASE, HIGH_VALUE_FAIRS
from config import HIGH_VALUE_SIGNALS, LOW_VALUE_SIGNALS
from sources import RSS_FEEDS, NEWSAPI_QUERIES
from database import is_seen
from classifier import classify_article, signal_sort_key, SIGNAL_SKIP

# NewsAPI ücretsiz plan 24 saat gecikmeli çalışır,
# 48 saatlik pencere hem dün hem bugün haberlerini kapsar
NEWS_MAX_AGE_HOURS = 72

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; FuarHaberBot/1.0; +https://evrekastand.com)"
}

NEWSAPI_URL = "https://newsapi.org/v2/everything"


# ─────────────────────────────────────────────────────────────
# 1. NewsAPI toplayıcı
# ─────────────────────────────────────────────────────────────

def fetch_from_newsapi() -> list[dict]:
    """NewsAPI.org'dan tüm sorgular için haber çek."""
    all_articles = []

    from_date = (datetime.now(timezone.utc) - timedelta(hours=NEWS_MAX_AGE_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")

    for query in NEWSAPI_QUERIES:
        params = {
            "q":        query["q"],
            "sortBy":   "publishedAt",
            "language": query.get("language", "en"),
            "pageSize": 100,
            "from":     from_date,
            "apiKey":   NEWSAPI_KEY,
        }
        label = query.get("label", query["q"][:40])

        try:
            resp = requests.get(NEWSAPI_URL, params=params, timeout=15)
            data = resp.json()

            if data.get("status") != "ok":
                print(f"[NEWSAPI] ⚠️  {label}: {data.get('message', 'Hata')}")
                continue

            articles_raw = data.get("articles", [])
            count = 0

            for item in articles_raw:
                # Silinen/kaldırılan haberler
                if item.get("title") in ("[Removed]", None, ""):
                    continue

                title    = _clean_text(item.get("title", ""))
                url      = item.get("url", "")
                summary  = _clean_text(item.get("description", "") or "")
                source   = item.get("source", {}).get("name", label)
                pub_str  = item.get("publishedAt", "")

                # Başlıktan kaynak adı tekrarını temizle (NewsAPI bazen "Başlık - Kaynak" gönderir)
                title, _ = _extract_publisher(title)

                # Özet = başlık tekrarıysa temizle
                summary = _dedupe_summary(title, summary)

                # Tarih parse
                published = _parse_iso(pub_str)

                if not url or not title:
                    continue

                all_articles.append({
                    "title":     title.strip(),
                    "url":       _clean_url(url.strip()),
                    "summary":   summary.strip(),
                    "source":    source,
                    "feed":      label,
                    "lang":      query.get("language", "en"),
                    "trust":     "newsapi",
                    "published": published,
                })
                count += 1

            print(f"[NEWSAPI] ✅ {label}: {count} haber")
            time.sleep(0.5)  # rate limit

        except Exception as e:
            print(f"[NEWSAPI] ❌ {label} hatası: {e}")

    return all_articles


# ─────────────────────────────────────────────────────────────
# 2. RSS toplayıcı (güvenilir sektör siteleri)
# ─────────────────────────────────────────────────────────────

def fetch_from_rss() -> list[dict]:
    """Güvenilir sektör RSS feed'lerinden haber çek."""
    all_articles = []

    for source in RSS_FEEDS:
        url   = source["url"]
        name  = source.get("name", url)
        lang  = source.get("lang", "en")
        trust = source.get("trust", "trusted")
        articles = []

        try:
            feed = feedparser.parse(url, request_headers=HEADERS)

            if feed.bozo and not feed.entries:
                print(f"[RSS] ⚠️  {name}")
                continue

            for entry in feed.entries:
                raw_title   = getattr(entry, "title", "") or ""
                link        = getattr(entry, "link", "")  or ""
                raw_summary = getattr(entry, "summary", "") or ""

                title   = _clean_text(raw_title)
                summary = _clean_text(raw_summary)[:600]

                title, publisher = _extract_publisher(title)
                act_source = publisher if publisher else name
                summary = _dedupe_summary(title, summary)

                published = _parse_date(entry)

                if not link or not title:
                    continue

                articles.append({
                    "title":     title.strip(),
                    "url":       _clean_url(link.strip()),
                    "summary":   summary.strip(),
                    "source":    act_source,
                    "feed":      name,
                    "lang":      lang,
                    "trust":     trust,
                    "published": published,
                })

            print(f"[RSS] ✅ {name}: {len(articles)} haber")

        except Exception as e:
            print(f"[RSS] ❌ {name} hatası: {e}")

        all_articles.extend(articles)
        time.sleep(0.3)

    return all_articles


# ─────────────────────────────────────────────────────────────
# 3. Ana toplayıcı
# ─────────────────────────────────────────────────────────────

def collect_all_news() -> list[dict]:
    """NewsAPI + RSS birleştir, filtrele, deduplike et."""

    # Kaynakları topla
    newsapi_articles = fetch_from_newsapi()
    rss_articles     = fetch_from_rss()
    all_articles     = newsapi_articles + rss_articles

    print(f"\n[COLLECTOR] Toplam ham haber: {len(all_articles)}")

    # 1. Dışlama filtresi
    after_exclude = [a for a in all_articles if not _is_excluded(a)]
    print(f"[COLLECTOR] Dışlama sonrası: {len(after_exclude)}")

    # 2. Fuar ilgililik filtresi
    relevant = [a for a in after_exclude if _is_fair_related(a)]
    print(f"[COLLECTOR] Fuar ilgili: {len(relevant)}")

    # 3. 48 saatlik tarih filtresi
    cutoff = datetime.now(timezone.utc) - timedelta(hours=NEWS_MAX_AGE_HOURS)
    fresh = [a for a in relevant if a["published"] >= cutoff]
    print(f"[COLLECTOR] Son {NEWS_MAX_AGE_HOURS} saatte: {len(fresh)}")

    # 4. Duplikasyon kontrolü (URL + başlık bazlı)
    seen_urls = set()
    seen_titles = []
    deduped = []
    for a in fresh:
        tkey = _title_key(a["title"])
        if a["url"] not in seen_urls and not _is_title_dup(tkey, seen_titles) and not is_seen(a["url"]):
            seen_urls.add(a["url"])
            seen_titles.append(tkey)
            deduped.append(a)
    print(f"[COLLECTOR] Yeni haber: {len(deduped)}")

    # 5. Skor + tarihe göre sırala
    deduped.sort(key=lambda x: (_relevance_score(x), x["published"]), reverse=True)

    # 6. Sinyal sınıflandırma — sadece 🟢 ve 🟠 geçer
    classified = []
    skip_count = 0
    for a in deduped:
        sig = classify_article(a)
        a.update(sig)
        if a["signal_type"] == SIGNAL_SKIP:
            skip_count += 1
            continue  # 🔴 GEÇME → gönderme
        classified.append(a)

    print(f"[COLLECTOR] 🔴 {skip_count} haber elendi (stand işi çıkmaz)")

    # 7. 🟢 Fırsatlar en üste
    classified.sort(key=lambda x: (signal_sort_key(x), -_relevance_score(x)))

    opp = sum(1 for a in classified if a["signal_type"] == "opportunity")
    watch = sum(1 for a in classified if a["signal_type"] == "watch")
    print(f"[COLLECTOR] ✅ Sonuç: 🟢 {opp} fırsat + 🟠 {watch} izle")

    return classified


def collect_top_recent(limit: int = 5) -> list[dict]:
    """
    Fallback modu: Veritabanında kayıtlı olsa bile
    son 48 saatteki en yüksek skorlu haberleri döndür.
    Yeni haber yokken günlük özet oluşturmak için kullanılır.
    """
    print(f"[COLLECTOR] Fallback: son 48 saatin en iyi {limit} haberi aranıyor...")

    newsapi_articles = fetch_from_newsapi()
    rss_articles     = fetch_from_rss()
    all_articles     = newsapi_articles + rss_articles

    # Dışlama + fuar filtresi
    filtered = [a for a in all_articles if not _is_excluded(a) and _is_fair_related(a)]

    # Son 48 saat
    cutoff = datetime.now(timezone.utc) - timedelta(hours=NEWS_MAX_AGE_HOURS)
    fresh = [a for a in filtered if a["published"] >= cutoff]

    # URL + başlık dedupe (aynı oturumda tekrar gösterme)
    seen_urls = set()
    seen_titles = []
    deduped = []
    for a in fresh:
        tkey = _title_key(a["title"])
        if a["url"] not in seen_urls and not _is_title_dup(tkey, seen_titles):
            seen_urls.add(a["url"])
            seen_titles.append(tkey)
            deduped.append(a)

    # Skor + tarihe göre sırala, en iyi limit kadar al
    deduped.sort(key=lambda x: (_relevance_score(x), x["published"]), reverse=True)
    top = deduped[:limit]

    print(f"[COLLECTOR] Fallback: {len(top)} haber seçildi.")
    return top


# ─────────────────────────────────────────────────────────────
# 4. Filtre & yardımcı fonksiyonlar
# ─────────────────────────────────────────────────────────────

def _is_fair_related(article: dict) -> bool:
    score     = _relevance_score(article)
    feed_name = article.get("feed", article.get("source", ""))
    trust     = article.get("trust", "general")

    # Güvenilir RSS kaynakları (TSNN, UFI, Trade Fair Times) — düşük eşik
    if trust == "trusted":
        return score >= MIN_SCORE_TRUSTED

    # Press release kaynakları (PR Newswire, GlobeNewswire) — sıkı eşik
    if trust == "press_release":
        return score >= MIN_SCORE_PRESS_RELEASE

    # NewsAPI ve diğerleri
    return score >= MIN_SCORE_GENERAL


def _relevance_score(article: dict) -> int:
    title_text   = article["title"].lower()
    summary_text = (article.get("summary") or "").lower()

    score = 0

    # Spesifik fuar isimleri — başlıkta geçerse yüksek puan
    for fair in HIGH_VALUE_FAIRS:
        if fair.lower() in title_text:
            score += 4
        elif fair.lower() in summary_text:
            score += 2

    # Genel keyword'ler
    for kw in FAIR_KEYWORDS:
        kw_lower = kw.lower()
        if kw_lower in title_text:
            score += 2
        elif kw_lower in summary_text:
            score += 1

    # 🟢 BOOST: Ticari sinyaller — SADECE fuar bağlamı varsa
    # ("expansion" tek başına yetmez, "exhibition expansion" gibi olmalı)
    from classifier import _has_fair_context
    full_text = title_text + " " + summary_text
    if _has_fair_context(full_text):
        for sig in HIGH_VALUE_SIGNALS:
            sig_lower = sig.lower()
            if sig_lower in title_text:
                score += 3
            elif sig_lower in summary_text:
                score += 2

    # 🔴 PENALTY: Düşük değerli sinyaller
    for low in LOW_VALUE_SIGNALS:
        if low.lower() in full_text:
            score -= 3

    return score


def _is_excluded(article: dict) -> bool:
    text = (article["title"] + " " + (article.get("summary") or "")).lower()
    return any(kw.lower() in text for kw in EXCLUDE_KEYWORDS)


# ─────────────────────────────────────────────────────────────
# 5. Metin yardımcıları
# ─────────────────────────────────────────────────────────────

def _clean_text(text: str) -> str:
    """HTML tag + entity temizle, boşlukları normalize et."""
    result = re.sub(r"<[^>]+>", "", text)
    result = html.unescape(result)
    result = re.sub(r"[\r\n\t]+", " ", result)
    result = re.sub(r" {2,}", " ", result)
    return result.strip()


def _clean_url(url: str) -> str:
    """URL'den UTM ve diğer izleme parametrelerini temizle."""
    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        clean_params = {k: v for k, v in params.items()
                        if not k.startswith(('utm_', 'ref', 'fbclid', 'gclid'))}
        clean_query = urlencode(clean_params, doseq=True)
        return urlunparse(parsed._replace(query=clean_query))
    except Exception:
        return url


def _title_key(title: str) -> str:
    """Başlığı normalize et (duplikasyon kontrolü için).
    Noktalama ve boşlukları silerek sadece harf/rakam bırakır.
    """
    return re.sub(r'[^a-z0-9]', '', title.lower())[:80]


def _is_title_dup(key: str, seen_keys: list[str], threshold: int = 40) -> bool:
    """Başlığın daha önce görülmüş bir başlığın duplikaşı olup olmadığını kontrol et.
    İlk 'threshold' karakter eşleşiyorsa duplikat sayılır.
    Eşiği 50'den 40'a düşürdük — cross-language varyasyonları yakalar.
    """
    prefix = key[:threshold]
    for seen in seen_keys:
        if seen[:threshold] == prefix:
            return True
    return False


def _extract_publisher(title: str) -> tuple[str, str]:
    """'Başlık - Yayın Organı' formatını ayır."""
    parts = title.rsplit(" - ", 1)
    if len(parts) == 2:
        clean_title = parts[0].strip()
        publisher   = parts[1].strip()
        if len(publisher) < 60 and len(clean_title) > 10:
            return clean_title, publisher
    return title, ""


def _dedupe_summary(title: str, summary: str) -> str:
    """Özet başlıkla aynıysa boş döndür."""
    if not summary:
        return ""
    t = title.lower().strip()
    s = summary.lower().strip()
    if t in s or s.startswith(t[:40]):
        return ""
    return summary


def _parse_iso(dt_str: str) -> datetime:
    """ISO 8601 string → datetime (NewsAPI formatı)."""
    try:
        dt_str = dt_str.replace("Z", "+00:00")
        return datetime.fromisoformat(dt_str)
    except Exception:
        return datetime.now(timezone.utc)


def _parse_date(entry) -> datetime:
    """RSS entry'den datetime parse et."""
    try:
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        if hasattr(entry, "updated_parsed") and entry.updated_parsed:
            return datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
    except Exception:
        pass
    return datetime.now(timezone.utc)
