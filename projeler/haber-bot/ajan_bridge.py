"""
Ajan-Bot Köprüsü — Haber-Bot ile Ajan-Bot arası import yönetimi.

Haber-bot'un config.py/database.py dosyaları ile Ajan-bot'un config.py ve
database/ paketi Python'da ad çakışması yaratıyor. Bu köprü, Ajan-bot
modüllerini subprocess yerine izole sys.path ile import eder.
"""

import sys
import os

AJAN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Ajan-bot")
HABER_DIR = os.path.dirname(os.path.abspath(__file__))


def _with_ajan_path(func):
    """Ajan-bot modüllerini import etmek için path'leri geçici olarak değiştir."""

    def wrapper(*args, **kwargs):
        # Mevcut state'i kaydet
        original_path = sys.path[:]
        saved_modules = {}

        # Çakışan modülleri geçici olarak kaldır
        conflicting = ["config", "database", "database.db"]
        for mod_name in list(sys.modules.keys()):
            if mod_name in conflicting or mod_name.startswith("database."):
                saved_modules[mod_name] = sys.modules.pop(mod_name)

        try:
            # Haber-bot'u path'ten çıkar, Ajan-bot'u ekle
            sys.path = [AJAN_DIR] + [p for p in sys.path
                                      if os.path.abspath(p) != os.path.abspath(HABER_DIR)]

            result = func(*args, **kwargs)
            return result

        finally:
            # Path'i geri yükle
            sys.path = original_path

            # Ajan-bot modüllerini farklı isimle sakla, haber-bot'un modüllerini geri koy
            ajan_modules = {}
            for mod_name in list(sys.modules.keys()):
                if mod_name in conflicting or mod_name.startswith("database."):
                    ajan_modules[mod_name] = sys.modules.pop(mod_name)

            # Haber-bot'un orijinal modüllerini geri yükle
            for mod_name, mod in saved_modules.items():
                sys.modules[mod_name] = mod

            # Ajan-bot modüllerini _ajan_ prefix'i ile sakla
            for mod_name, mod in ajan_modules.items():
                sys.modules[f"_ajan_{mod_name}"] = mod

    return wrapper


# Ajan-bot sınıflarını tutan cache
_cache = {}


@_with_ajan_path
def _load_database():
    from database.db import Database
    return Database


@_with_ajan_path
def _load_discoverer():
    import config as ajan_config  # noqa — Ajan-bot'un config'i
    from scrapers.smart_discoverer import SmartFairDiscoverer
    return SmartFairDiscoverer


@_with_ajan_path
def _load_enricher():
    import config as ajan_config  # noqa
    from enrichment.enricher import Enricher
    return Enricher


class AjanBot:
    """Ajan-Bot fonksiyonlarına erişim sağlayan sınıf."""

    @classmethod
    def get_database(cls):
        if "Database" not in _cache:
            _cache["Database"] = _load_database()
        return _cache["Database"]

    @classmethod
    def get_discoverer(cls):
        if "SmartFairDiscoverer" not in _cache:
            _cache["SmartFairDiscoverer"] = _load_discoverer()
        return _cache["SmartFairDiscoverer"]

    @classmethod
    def get_enricher(cls):
        if "Enricher" not in _cache:
            _cache["Enricher"] = _load_enricher()
        return _cache["Enricher"]
