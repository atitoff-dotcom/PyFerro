"""
Модель метаданных файлов в ядре PyFerro 2.0 (`pyferro2/files/models.py`).

Наследует `RowSecureModel`, поэтому использует единые поля `id`, `creator_id`,
`created_at` и `updated_at` без дублирующих синонимов (`file_id`, `owner_id`).
"""

from typing import Any

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from pyferro2.db.base import RowSecureModel


class StoredFile(RowSecureModel):
    """
    Запись о сохраненном файле в таблице `pf_file_metadata`.
    """

    __tablename__ = "pf_file_metadata"

    folder_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_name: Mapped[str] = mapped_column(String(512), nullable=False)
    size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mime_type: Mapped[str] = mapped_column(
        String(128), default="application/octet-stream", nullable=False
    )
    sha256: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    is_public: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False
    )

    @property
    def url(self) -> str:
        """Относительный HTTP-путь для скачивания или раздачи через Nginx."""
        return f"/files/{self.folder_hash}/{self.filename}"

    def to_dict(self) -> dict[str, Any]:
        """Преобразует метаданные файла в чистый словарь для JSON-RPC ответов."""
        return {
            "id": self.id,
            "creator_id": self.creator_id,
            "folder_hash": self.folder_hash,
            "filename": self.filename,
            "original_name": self.original_name,
            "size": self.size,
            "mime_type": self.mime_type,
            "sha256": self.sha256,
            "is_public": self.is_public,
            "url": self.url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
