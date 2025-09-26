# bot/utils/media.py
# Утилиты для работы с медиа (фото) в отчётах/экспортах.

import os
from urllib.parse import urlparse
from aiogram import Bot  # ← Bot нужно импортировать отсюда, не из aiogram.types

MEDIA_ROOT = os.getenv("MEDIA_ROOT", "media")


def _is_url(s: str) -> bool:
    try:
        u = urlparse(s or "")
        return bool(u.scheme and u.netloc)
    except Exception:
        return False


async def hydrate_photos_for_attempt(data, bot: Bot) -> None:
    """
    Пробегаемся по data.answers и приводим photo_path к локальным файлам.
    - если путь абсолютный и файл существует — оставляем
    - если путь относительный — пробуем в MEDIA_ROOT
    - если это URL — пока не докачиваем, просто пропускаем (экспорт проигнорирует)
    """
    if not hasattr(data, "answers") or not data.answers:
        return

    for row in data.answers:
        p = getattr(row, "photo_path", None)
        if not p:
            continue

        # 1) Абсолютный локальный путь
        if os.path.isabs(p) and os.path.exists(p):
            continue

        # 2) Относительный путь — проверим в MEDIA_ROOT
        candidate = os.path.join(MEDIA_ROOT, p) if not os.path.isabs(p) else p
        if os.path.exists(candidate):
            row.photo_path = candidate
            continue

        # 3) URL — пока пропускаем (если захотим — тут можно скачать)
        if _is_url(p):
            continue

        # иначе — ничего не делаем
