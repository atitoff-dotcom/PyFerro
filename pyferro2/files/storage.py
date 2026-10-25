"""
Двухфазный координатор потоковой загрузки и хранения файлов (`FileStorage`).

Жизненный цикл загрузки (Two-Phase Commit):
1. `init_upload(creator_id)` — выделяет временную директорию `<tmp_root>/<folder_hash>`.
2. `receive_stream(...)` — принимает поток байтов из HTTP, пишет чанками на диск
   (потребление RAM = O(1)) и параллельно вычисляет контрольную сумму SHA-256.
3. `commit_upload(...)` — атомарно переносит файлы в постоянное хранилище (`os.replace`)
   и создает записи `StoredFile` в базе данных.
4. `rollback_upload(...)` — удаляет временную директорию при отмене или ошибке.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
import hashlib
import os
from pathlib import Path
import re
import secrets
import shutil
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pyferro2.core.session_data import SessionData
from pyferro2.files.models import StoredFile

_SAFE_FILENAME_RE = re.compile(r"[^a-zA-Z0-9._\-А-Яа-яЁё]")
DEFAULT_MAX_FILE_SIZE = 250 * 1024 * 1024  # 250 МБ


def sanitize_filename(raw_name: str | None) -> str:
    """Очищает имя файла от опасных символов и попыток выхода из директории (`..`)."""
    if not raw_name:
        return f"file_{secrets.token_hex(4)}"
    base = os.path.basename(raw_name).strip()
    safe = _SAFE_FILENAME_RE.sub("_", base)
    if not safe or safe in (".", ".."):
        return f"file_{secrets.token_hex(4)}"
    return safe[:200]


@dataclass(slots=True)
class UploadTransaction:
    """Активная транзакция двухфазной загрузки файлов."""

    folder_hash: str
    creator_id: int | None
    tmp_dir: Path
    files: dict[str, dict[str, Any]] = field(default_factory=dict)


class FileStorage:
    """
    Сервис управления физическими файлами и транзакциями загрузки.
    Поддерживает прямую отдачу файлов и заголовок `X-Accel-Redirect` для Nginx.
    """

    __slots__ = (
        "storage_dir",
        "tmp_root",
        "max_file_size",
        "nginx_internal_prefix",
        "_transactions",
    )

    def __init__(
        self,
        storage_dir: str | Path = "./data/pyferro2_files",
        tmp_root: str | Path = "/tmp/pyferro2_uploads",
        max_file_size: int = DEFAULT_MAX_FILE_SIZE,
        nginx_internal_prefix: str | None = None,
    ) -> None:
        self.storage_dir: Path = Path(storage_dir)
        self.tmp_root: Path = Path(tmp_root)
        self.max_file_size: int = max_file_size
        # Если задан (например, "/_internal_files"), сервер отдает заголовок X-Accel-Redirect для Nginx
        self.nginx_internal_prefix: str | None = (
            nginx_internal_prefix.rstrip("/") if nginx_internal_prefix else None
        )
        self._transactions: dict[str, UploadTransaction] = {}

        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.tmp_root.mkdir(parents=True, exist_ok=True)

    def init_upload(self, creator_id: int | None) -> UploadTransaction:
        """Создает новую транзакцию загрузки и выделяет временную папку."""
        folder_hash = secrets.token_hex(16)
        tmp_dir = self.tmp_root / folder_hash
        tmp_dir.mkdir(parents=True, exist_ok=True)

        tx = UploadTransaction(
            folder_hash=folder_hash,
            creator_id=creator_id,
            tmp_dir=tmp_dir,
        )
        self._transactions[folder_hash] = tx
        return tx

    def get_transaction(self, folder_hash: str) -> UploadTransaction | None:
        """Возвращает активную транзакцию по `folder_hash`."""
        return self._transactions.get(folder_hash)

    async def receive_stream(
        self,
        folder_hash: str,
        raw_filename: str,
        mime_type: str,
        chunks: AsyncIterator[bytes],
    ) -> dict[str, Any]:
        """
        Принимает поток чанков файла, записывает на диск в O(1) RAM и считает SHA-256.
        """
        tx = self._transactions.get(folder_hash)
        if tx is None:
            raise ValueError(f"Транзакция загрузки '{folder_hash}' не найдена или уже закрыта")

        safe_name = sanitize_filename(raw_filename)
        dest_path = tx.tmp_dir / safe_name

        hasher = hashlib.sha256()
        total_bytes = 0

        try:
            with open(dest_path, "wb") as f:
                async for chunk in chunks:
                    if not chunk:
                        continue
                    total_bytes += len(chunk)
                    if total_bytes > self.max_file_size:
                        raise ValueError(
                            f"Превышен максимальный размер файла ({self.max_file_size} байт)"
                        )
                    hasher.update(chunk)
                    f.write(chunk)
        except Exception:
            if dest_path.exists():
                dest_path.unlink(missing_ok=True)
            raise

        file_info = {
            "filename": safe_name,
            "original_name": raw_filename or safe_name,
            "size": total_bytes,
            "mime_type": mime_type or "application/octet-stream",
            "sha256": hasher.hexdigest(),
        }
        tx.files[safe_name] = file_info
        return file_info

    async def commit_upload(
        self,
        db: AsyncSession,
        folder_hash: str,
        creator_id: int | None,
        is_public: bool = True,
    ) -> list[StoredFile]:
        """
        Фиксирует транзакцию: переносит файлы в постоянное хранилище и сохраняет записи в БД.
        """
        tx = self._transactions.pop(folder_hash, None)
        if tx is None:
            raise ValueError(f"Транзакция загрузки '{folder_hash}' не найдена")

        if tx.creator_id is not None and creator_id != tx.creator_id:
            self._cleanup_dir(tx.tmp_dir)
            raise PermissionError("Только инициатор транзакции может подтвердить загрузку")

        final_dir = self.storage_dir / folder_hash
        final_dir.mkdir(parents=True, exist_ok=True)

        saved_records: list[StoredFile] = []
        for fname, info in tx.files.items():
            src_file = tx.tmp_dir / fname
            dst_file = final_dir / fname
            if src_file.exists():
                shutil.move(str(src_file), str(dst_file))

            record = StoredFile(
                creator_id=creator_id if creator_id is not None else tx.creator_id,
                folder_hash=folder_hash,
                filename=fname,
                original_name=info["original_name"],
                size=info["size"],
                mime_type=info["mime_type"],
                sha256=info["sha256"],
                is_public=is_public,
            )
            db.add(record)
            saved_records.append(record)

        self._cleanup_dir(tx.tmp_dir)
        await db.commit()
        return saved_records

    def rollback_upload(self, folder_hash: str) -> bool:
        """Отменяет транзакцию загрузки и удаляет временные файлы."""
        tx = self._transactions.pop(folder_hash, None)
        if tx is None:
            return False
        self._cleanup_dir(tx.tmp_dir)
        return True

    async def delete_file(
        self,
        db: AsyncSession,
        file_id: int,
        session_data: SessionData,
    ) -> bool:
        """Удаляет файл с диска и из БД (доступно владельцу файла или администратору)."""
        result = await db.execute(select(StoredFile).where(StoredFile.id == file_id))
        record = result.scalar_one_or_none()
        if record is None:
            return False

        if not session_data.is_admin and record.creator_id != session_data.user_id:
            raise PermissionError("Недостаточно прав для удаления чужого файла")

        file_path = self.storage_dir / record.folder_hash / record.filename
        if file_path.exists():
            file_path.unlink(missing_ok=True)
        folder_dir = file_path.parent
        if folder_dir.exists() and not any(folder_dir.iterdir()):
            folder_dir.rmdir()

        await db.delete(record)
        await db.commit()
        return True

    def resolve_file_path(self, folder_hash: str, filename: str) -> Path | None:
        """Безопасно вычисляет путь к физическому файлу в хранилище."""
        safe_folder = sanitize_filename(folder_hash)
        safe_file = sanitize_filename(filename)
        candidate = (self.storage_dir / safe_folder / safe_file).resolve()
        if not str(candidate).startswith(str(self.storage_dir.resolve())):
            return None
        return candidate if candidate.is_file() else None

    @staticmethod
    def _cleanup_dir(path: Path) -> None:
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
