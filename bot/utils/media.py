# bot/utils/media.py
# Утилиты для работы с медиа (фото) в отчётах/экспортах.

import json
import logging
import os
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

MEDIA_ROOT = os.getenv("MEDIA_ROOT", "media")
logger = logging.getLogger(__name__)


def _is_url(s: str) -> bool:
    try:
        u = urlparse(s or "")
        return bool(u.scheme and u.netloc)
    except Exception:
        return False


def _extract_file_id(raw: str) -> str | None:
    if not raw:
        return None
    value = raw.strip()
    if value.startswith("file_id:"):
        return value.split("file_id:", 1)[1].strip() or None
    if value.startswith("{") or value.startswith("["):
        try:
            obj = json.loads(value)
            if isinstance(obj, dict) and "file_id" in obj:
                return str(obj["file_id"])
            if (
                isinstance(obj, list)
                and obj
                and isinstance(obj[0], dict)
                and "file_id" in obj[0]
            ):
                return str(obj[0]["file_id"])
        except Exception:
            return None
    # если это похоже на путь, не трогаем
    if "/" in value or "\\" in value or value.startswith("."):
        return None
    # file_id Telegram — обычно не содержит точек и двоеточий; допускаем символы '_' и '-'
    if value.count(":") > 1:
        return None
    return value


async def _download_from_url(url: str) -> str | None:
    suffix = Path(urlparse(url).path).suffix or ".jpg"
    tmp_path = Path(tempfile.gettempdir()) / f"chk_{uuid.uuid4().hex}{suffix}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    logger.warning("Failed to fetch photo URL %s (status %s)", url, resp.status)
                    return None
                data = await resp.read()
    except Exception:
        logger.exception("Error while downloading photo from URL %s", url)
        return None

    try:
        tmp_path.write_bytes(data)
        return str(tmp_path)
    except Exception:
        logger.exception("Error while writing downloaded photo from URL %s", url)
        return None


async def _download_from_file_id(bot: Bot, file_id: str) -> str | None:
    suffix = ".jpg"
    try:
        file_info = await bot.get_file(file_id)
        suffix = Path(getattr(file_info, "file_path", "")).suffix or suffix
    except TelegramBadRequest:
        logger.warning("Telegram returned BadRequest for file_id %s", file_id)
        return None
    except Exception:
        logger.exception("Failed to get file info for file_id %s", file_id)
        return None

    tmp_path = Path(tempfile.gettempdir()) / f"chk_{uuid.uuid4().hex}{suffix}"
    tmp_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        await bot.download(file_id, destination=str(tmp_path))
    except Exception:
        logger.exception("Failed to download telegram file %s", file_id)
        return None

    if not tmp_path.exists():
        logger.warning("Downloaded file for %s not found at %s", file_id, tmp_path)
        return None
    return str(tmp_path)


async def hydrate_photos_for_attempt(data, bot: Bot) -> None:
    """Превращаем сохранённые ссылки на фото в локальные файлы."""
    if not hasattr(data, "answers") or not data.answers:
        return

    for row in data.answers:
        raw_path = getattr(row, "photo_path", None)
        if not raw_path:
            continue

        logger.debug("Hydrating photo for attempt %s answer %s: %s", getattr(data, "attempt_id", "?"), row.number, raw_path)

        # нормализуем разделители путей
        normalized = str(raw_path).strip()
        normalized = normalized.replace("\\", "/")

        # 1) Абсолютный путь
        if os.path.isabs(normalized) and os.path.exists(normalized):
            logger.debug("Using absolute path for photo: %s", normalized)
            row.photo_path = normalized
            continue

        # Проверим относительный путь как есть
        rel_path = Path(normalized)
        if rel_path.exists():
            row.photo_path = str(rel_path)
            logger.debug("Resolved photo by relative path: %s", rel_path)
            continue

        # 2) Путь относительно MEDIA_ROOT
        if not rel_path.is_absolute():
            candidate = Path(MEDIA_ROOT) / rel_path
            if candidate.exists():
                row.photo_path = str(candidate)
                logger.debug("Resolved photo in MEDIA_ROOT: %s", candidate)
                continue

        raw_path = normalized  # для дальнейших проверок

        # 3) URL → скачиваем во временный файл
        if _is_url(raw_path):
            downloaded = await _download_from_url(raw_path)
            if downloaded:
                row.photo_path = downloaded
                logger.debug("Downloaded photo from URL to %s", downloaded)
            else:
                row.photo_path = None
                logger.warning("Failed to download photo from URL %s", raw_path)
            continue

        # 4) file_id → скачиваем через Telegram API
        file_id = _extract_file_id(raw_path)
        if file_id:
            downloaded = await _download_from_file_id(bot, file_id)
            row.photo_path = downloaded
            if downloaded:
                logger.debug("Downloaded photo from file_id %s to %s", file_id, downloaded)
            else:
                logger.warning("Failed to download photo for file_id %s", file_id)
            continue

        # если ничего не вышло — фотографию пропускаем
        row.photo_path = None
        logger.warning("Could not resolve photo path for %s", raw_path)
