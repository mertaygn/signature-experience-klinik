import time
from deep_translator import GoogleTranslator


_translator = GoogleTranslator(source="auto", target="tr")


def translate_to_turkish(text: str) -> str:
    """Metni Türkçe'ye çevir. Zaten Türkçe ise dokunma."""
    if not text or not text.strip():
        return text

    try:
        # Google Translate 5000 karakter limiti var, böl
        if len(text) > 4500:
            text = text[:4500]

        result = _translator.translate(text)
        time.sleep(0.3)  # Rate limiting
        return result or text

    except Exception as e:
        print(f"[TRANSLATOR] Çeviri hatası: {e}")
        return text  # Hata durumunda orijinali döndür


def translate_article(article: dict) -> dict:
    """Bir haber nesnesinin başlık ve özetini Türkçe'ye çevir."""
    if article.get("lang") == "tr":
        # Zaten Türkçe kaynak, çeviri gerekmiyor
        return article

    translated = article.copy()
    translated["title"] = translate_to_turkish(article["title"])
    if article.get("summary"):
        translated["summary"] = translate_to_turkish(article["summary"])

    return translated
