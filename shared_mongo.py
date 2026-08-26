"""Один клиент MongoDB на процесс, общий для хаба и плагинов.

Раньше корневой main.py, evenfest, markbin и toadcode создавали каждый свой
AsyncIOMotorClient к одному и тому же кластеру. У motor maxPoolSize по
умолчанию 100, то есть четыре клиента могли открыть до 400 соединений — при
лимите 500 на бесплатном Atlas M0, где живёт этот кластер. Здесь один пул с
явным потолком.

Файл лежит в корне модулем, а не пакетом `shared/`: автодискавери в main.py
перебирает каталоги корня и пометил бы `shared/` как сломанный плагин.

Модуль намеренно не пакет netlazy: у netlazy свой клиент с retry-логикой и
собственным жизненным циклом, трогать его здесь нечего.
"""

from __future__ import annotations

import logging
from os import environ

from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger(__name__)

_client: AsyncIOMotorClient | None = None


def _env_flag(name: str, default: bool) -> bool:
    raw = environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ('1', 'true', 'yes', 'on')


def get_client() -> AsyncIOMotorClient:
    """Возвращает общий клиент, создавая его при первом обращении."""
    global _client
    if _client is None:
        uri = environ.get('MONGODB_URI', 'mongodb://localhost:27017')
        kwargs = {
            'maxPoolSize': int(environ.get('MONGO_MAX_POOL_SIZE', '20')),
            'serverSelectionTimeoutMS': 10000,
        }
        if _env_flag('MONGO_TLS', True):
            kwargs['tls'] = True
            # Проверка сертификата отключена по умолчанию только чтобы не
            # менять поведение работающего деплоя. Atlas отдаёт сертификат
            # обычного публичного CA, так что после проверки, что CA-бандл
            # образа его принимает, поставить MONGO_TLS_ALLOW_INVALID_CERTS=0
            # и убрать этот дефолт — сейчас соединение уязвимо к MITM.
            kwargs['tlsAllowInvalidCertificates'] = _env_flag(
                'MONGO_TLS_ALLOW_INVALID_CERTS', True
            )
        _client = AsyncIOMotorClient(uri, **kwargs)
        logger.info(f"Shared Mongo client created (maxPoolSize={kwargs['maxPoolSize']})")
    return _client


def close_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
