"""
JSON-RPC обработчики файловой подсистемы ядра (`files.*`).

Все методы используют Smart Dependency Injection (`session_data: SessionData`, `db: AsyncSession`)
и доступны любому авторизованному пользователю (`role=[USER_ROLE, admRole.admin]`)
либо через матрицу прав (`allow_permissions=True`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pyferro2.core.constants import USER_ROLE, admRole
from pyferro2.core.session_data import SessionData
from pyferro2.files.models import StoredFile
from pyferro2.files.storage import FileStorage
from pyferro2.rpc.errors import ForbiddenError, InvalidParamsError, RpcError
from pyferro2.rpc.router import RpcRouter

if TYPE_CHECKING:
    from pyferro2.server.tokens import TokenManager

_AUTHENTICATED_ROLES = (USER_ROLE, admRole.admin.value)


def register_file_rpc(
    router: RpcRouter,
    storage: FileStorage,
    token_manager: TokenManager,
) -> None:
    """Регистрирует стандартные RPC-методы работы с файлами (`files.*`) в указанном роутере."""

    class files:
        @router.rpc_method(role=_AUTHENTICATED_ROLES)
        async def init_upload(session_data: SessionData) -> dict[str, Any]:
            tx = storage.init_upload(creator_id=session_data.user_id)
            return {
                "status": "ready",
                "folder_hash": tx.folder_hash,
                "upload_url": f"/upload?folder={tx.folder_hash}",
            }

        @router.rpc_method(role=_AUTHENTICATED_ROLES)
        async def commit(
            session_data: SessionData,
            db: AsyncSession,
            folder_hash: str,
            is_public: bool = True,
        ) -> dict[str, Any]:
            if not folder_hash:
                raise InvalidParamsError("Параметр 'folder_hash' не может быть пустым")
            try:
                records = await storage.commit_upload(
                    db=db,
                    folder_hash=folder_hash,
                    creator_id=session_data.user_id,
                    is_public=is_public,
                )
            except PermissionError as exc:
                raise ForbiddenError(str(exc)) from exc
            except ValueError as exc:
                raise InvalidParamsError(str(exc)) from exc

            return {
                "status": "committed",
                "folder_hash": folder_hash,
                "files": [r.to_dict() for r in records],
            }

        @router.rpc_method(role=_AUTHENTICATED_ROLES)
        async def rollback(session_data: SessionData, folder_hash: str) -> dict[str, Any]:
            if not folder_hash:
                raise InvalidParamsError("Параметр 'folder_hash' не может быть пустым")
            tx = storage.get_transaction(folder_hash)
            if tx is not None and not session_data.is_admin and tx.creator_id != session_data.user_id:
                raise ForbiddenError("Нельзя отменить чужую транзакцию загрузки")
            aborted = storage.rollback_upload(folder_hash)
            return {"status": "aborted" if aborted else "not_found", "folder_hash": folder_hash}

        @router.rpc_method(role=_AUTHENTICATED_ROLES)
        async def list_my(
            session_data: SessionData,
            db: AsyncSession,
            page: int = 1,
            limit: int = 50,
        ) -> list[dict[str, Any]]:
            offset = (max(1, page) - 1) * min(max(1, limit), 200)
            stmt = (
                select(StoredFile)
                .where(StoredFile.creator_id == session_data.user_id)
                .order_by(StoredFile.id.desc())
                .offset(offset)
                .limit(min(max(1, limit), 200))
            )
            rows = (await db.execute(stmt)).scalars().all()
            return [r.to_dict() for r in rows]

        @router.rpc_method(role=_AUTHENTICATED_ROLES)
        async def delete(
            session_data: SessionData,
            db: AsyncSession,
            file_id: int,
        ) -> dict[str, Any]:
            try:
                deleted = await storage.delete_file(db=db, file_id=file_id, session_data=session_data)
            except PermissionError as exc:
                raise ForbiddenError(str(exc)) from exc
            if not deleted:
                raise RpcError(f"Файл с id={file_id} не найден", code=-32004)
            return {"deleted": True, "id": file_id}

        @router.rpc_method(role=_AUTHENTICATED_ROLES)
        async def get_download_token(
            session_data: SessionData,
            db: AsyncSession,
            file_id: int,
            ttl_seconds: int = 3600,
        ) -> dict[str, Any]:
            record = (
                await db.execute(select(StoredFile).where(StoredFile.id == file_id))
            ).scalar_one_or_none()
            if record is None:
                raise RpcError(f"Файл с id={file_id} не найден", code=-32004)
            if not record.is_public and not session_data.is_admin and record.creator_id != session_data.user_id:
                raise ForbiddenError("Нет прав на скачивание приватного файла")

            token = token_manager.issue_file_token(file_id=record.id, ttl_seconds=ttl_seconds)
            return {
                "id": record.id,
                "token": token,
                "download_url": f"{record.url}?token={token}",
            }
