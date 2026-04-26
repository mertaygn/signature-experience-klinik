"""
Ana iş akışı:
1. Tüm kaynaklardan haber topla
2. Lead analizi (event/ülke/sektör/teklif)
3. Türkçe'ye çevir
4. Telegram'a satış formatında gönder
5. Veritabanına işaretle

📌 Fallback modu: Gün içinde hiç yeni haber yoksa,
   son 72 saatteki en iyi haberler gösterilir.
"""

from config import MAX_NEWS_PER_DAY
from collector import collect_all_news, collect_top_recent
from lead_generator import generate_lead
from translator import translate_article
from sender import send_daily_digest, send_fallback_digest
from database import mark_seen, cleanup_old_records


def run_job():
    """Günlük haber toplama, lead analizi ve gönderme işi."""
    print("\n" + "=" * 50)
    print("🏗️ Stand & Expo İş Fırsatı Dedektörü başlatıldı...")
    print("=" * 50)

    # 1. Eski kayıtları temizle
    cleanup_old_records()

    # 2. Yeni haberleri topla
    articles = collect_all_news()

    # 3a. Yeni haber varsa normal akış
    if articles:
        articles = articles[:MAX_NEWS_PER_DAY]
        print(f"[JOB] {len(articles)} fırsat işlenecek...")

        # Lead analizi (çeviriden ÖNCE — orijinal dilde daha doğru)
        for i, article in enumerate(articles):
            lead = generate_lead(article)
            event = lead.get("event_name", "?")
            country = lead.get("country", "?")
            industry = lead.get("industry", "?")
            print(f"[LEAD] {i+1}/{len(articles)}: {event or '—'} / {country or '—'} / {industry or '—'}")

        raw_articles = []
        translated_articles = []

        for i, article in enumerate(articles):
            print(f"[JOB] Çeviriliyor {i+1}/{len(articles)}: {article['title'][:60]}...")
            raw_articles.append(article.copy())
            translated = translate_article(article)
            translated_articles.append(translated)

        # Gönder
        sent = send_daily_digest(translated_articles, raw_articles)

        for article in translated_articles[:sent]:
            mark_seen(article["url"], article["title"], article["source"])

        print(f"\n[JOB] ✅ Tamamlandı. {sent} fırsat gönderildi.")

        # ─── Otomatik Lead Keşfi ──────────────────────────────────
        # Tespit edilen fuar isimlerinden exhibitor keşfi dene
        _auto_discover_exhibitors(articles)

        print("=" * 50)

    # 3b. Yeni haber yoksa → fallback: son 48 saatin en iyi 5 haberi
    else:
        print("[JOB] ⚠️  Yeni haber bulunamadı — Fallback modu: en iyi haberler gönderiliyor...")
        top_articles = collect_top_recent(limit=5)

        if not top_articles:
            print("[JOB] Fallback için de haber bulunamadı. Sessiz kalınıyor.")
            return

        raw_articles = []
        translated_articles = []

        for i, article in enumerate(top_articles):
            print(f"[JOB] (Fallback) Çeviriliyor {i+1}/{len(top_articles)}: {article['title'][:60]}...")
            raw_articles.append(article.copy())
            translated = translate_article(article)
            translated_articles.append(translated)

        send_fallback_digest(translated_articles, raw_articles)
        print(f"\n[JOB] ✅ Fallback tamamlandı. {len(translated_articles)} haber gönderildi.")
        print("=" * 50)


def _auto_discover_exhibitors(articles: list):
    """
    🟢 fırsatlarda tespit edilen fuar isimlerinden otomatik exhibitor keşfi.
    Başarısız olursa sessizce geçer — ana pipeline'ı etkilemez.
    """
    # Lead'lerdeki fuar isimlerini topla
    fair_names = set()
    for article in articles:
        lead = article.get("lead", {})
        event = lead.get("event_name", "")
        if event and len(event) > 3:
            fair_names.add(event)

    if not fair_names:
        print("[AJAN] Bilinen fuar ismi tespit edilmedi, exhibitor keşfi atlanıyor.")
        return

    print(f"\n[AJAN] 🕵️ {len(fair_names)} fuar için exhibitor keşfi deneniyor: {fair_names}")

    for fair_name in fair_names:
        try:
            from ajan_bridge import AjanBot
            Database = AjanBot.get_database()
            SmartFairDiscoverer = AjanBot.get_discoverer()

            discoverer = SmartFairDiscoverer()
            result = discoverer.discover_and_scrape(fair_name, enrich_details=True)

            companies = result.get("companies", [])
            if not companies:
                print(f"[AJAN] ⚠️ '{fair_name}': exhibitor bulunamadı.")
                continue

            # DB'ye kaydet
            with Database() as db:
                slug = fair_name.lower().replace(" ", "_").replace("-", "_")[:30]
                fair_id = db.upsert_fair(slug=slug, name=fair_name, url=result.get("fair_url"))

                saved = 0
                for company in companies:
                    data = company.to_dict()
                    db.upsert_company(
                        fair_id=fair_id,
                        name=data["name"],
                        website=data.get("website"),
                        booth_number=data.get("booth_number"),
                        sector=data.get("sector"),
                        country=data.get("country"),
                        city=data.get("city"),
                        email=data.get("email"),
                        phone=data.get("phone"),
                        address=data.get("address"),
                    )
                    saved += 1

                print(f"[AJAN] ✅ '{fair_name}': {saved} firma kaydedildi.")

                # Telegram'a lead özeti gönder
                _send_lead_summary_telegram(db, fair_id, fair_name, saved)

        except Exception as e:
            print(f"[AJAN] ❌ '{fair_name}' keşfi başarısız: {e}")


def _send_lead_summary_telegram(db, fair_id: int, fair_name: str, total: int):
    """Telegram'a lead havuzu özeti gönder."""
    try:
        from sender import send_message

        companies = db.get_companies_by_fair(fair_id)
        if not companies:
            return

        with_web = sum(1 for c in companies if c.get("website"))
        with_email = sum(1 for c in companies if c.get("email"))

        # İlk 5 firmayı göster
        lines = [
            f"📋 <b>LEAD HAVUZU — {fair_name}</b>",
            f"━━━━━━━━━━━━━━━━",
        ]

        for c in companies[:5]:
            name = c.get("name", "?")[:35]
            country = c.get("country", "")
            sector = c.get("sector", "")[:25] if c.get("sector") else ""
            web = "🌐" if c.get("website") else ""
            email = "✉️" if c.get("email") else ""

            info_parts = []
            if country:
                info_parts.append(country)
            if sector:
                info_parts.append(sector)
            info_str = " | ".join(info_parts)

            lines.append(f"🏢 <b>{name}</b>  {web}{email}")
            if info_str:
                lines.append(f"   {info_str}")

        if total > 5:
            lines.append(f"\n... ve {total - 5} firma daha")

        lines.append(f"\n📊 Toplam: <b>{total}</b> firma | 🌐 {with_web} web | ✉️ {with_email} email")
        lines.append(f"\n💡 <i>Detay: python main.py export {fair_name.lower().replace(' ', '_')[:30]}</i>")

        msg = "\n".join(lines)
        send_message(msg)

    except Exception as e:
        print(f"[AJAN] Lead özeti gönderilemedi: {e}")

