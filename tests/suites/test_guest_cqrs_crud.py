# -*- coding: utf-8 -*-
"""
Тест-сьют: CQRS и публичное CRUD-чтение для роли «Гость» (guest).
Проверяет:
1. Системную роль guest в матрице ролей (Zero Special Cases).
2. Публичное чтение разрешенной модели через crud.list ($tabular) и crud.get при user_id is None.
3. Запрет чтения неразрешенных моделей для гостей.
4. Аппаратный запрет любых CRUD-мутаций (create, update_cell, bulk_update, delete) для роли guest.
5. Zero-Leakage в crud.schema: гость видит только разрешенные для чтения модели.
6. Сохранение и извлечение прав гостя через permissions.save / permissions.get.
"""

import pytest
from unittest.mock import MagicMock
from sqlalchemy import Integer, String, Boolean, select
from sqlalchemy.orm import Mapped, mapped_column

from pyferro.core.session import (
    JsonRpcSession,
    RPCError,
    GUEST_ALLOWED_CRUD_MODELS,
    GUEST_ALLOWED_RPC_METHODS,
    is_guest_rpc_allowed
)
from pyferro.core.constants import GUEST_ROLE, ADMIN_ROLE
from pyferro.auth.models import Role, RolePermission, RpcPermission
from pyferro.auth.discovery import sync_rpc_permissions, reload_guest_permissions_cache
from pyferro.auth.permission_handlers import (
    handle_permissions_get,
    handle_permissions_save
)
from pyferro.plugins.crud import (
    ModelRegistry,
    handle_crud_schema,
    handle_crud_list,
    handle_crud_get,
    handle_crud_create,
    handle_crud_update_cell,
    handle_crud_delete,
    handle_crud_bulk_update
)
from pyferro.db import Base, async_session, engine, system_bypass


class CatalogItem(Base):
    __tablename__ = "test_guest_catalog_items"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    price: Mapped[int] = mapped_column(Integer, default=100)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    creator_id: Mapped[int] = mapped_column(Integer, nullable=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=True)

    class Crud:
        verbose_name = "Товар каталога"
        archivable = True


class SecretDocument(Base):
    __tablename__ = "test_guest_secret_docs"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    secret_text: Mapped[str] = mapped_column(String(100), nullable=False)
    creator_id: Mapped[int] = mapped_column(Integer, nullable=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=True)

    class Crud:
        verbose_name = "Секретный документ"


class GuestMockSession:
    def __init__(self):
        self.session_id = 1001
        self.authenticated = False
        self.data = None
        self.user_role = "guest"
        self.user_roles = ["guest"]
        self.ws = None
        self.cookies = {}


class AdminMockSession:
    def __init__(self):
        self.session_id = 1
        self.authenticated = True
        self.data = {"id": 1, "username": "admin", "is_superadmin": True}
        self.user_role = "admin"
        self.user_roles = ["admin"]
        self.ws = None
        self.cookies = {}


@pytest.mark.asyncio
async def test_guest_cqrs_lifecycle():
    # 1. Регистрация моделей
    ModelRegistry.register(CatalogItem)
    ModelRegistry.register(SecretDocument)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await sync_rpc_permissions()

    # 2. Создаем начальные тестовые данные в обход RLS
    from sqlalchemy import delete
    with system_bypass():
        async with async_session() as db:
            await db.execute(delete(CatalogItem))
            await db.execute(delete(SecretDocument))
            await db.commit()

            item1 = CatalogItem(title="Ноутбук", price=50000, is_archived=False)
            item2 = CatalogItem(title="Мышь", price=1500, is_archived=False)
            item_archived = CatalogItem(title="Старый кабель", price=100, is_archived=True)
            doc1 = SecretDocument(secret_text="TopSecret123")
            db.add_all([item1, item2, item_archived, doc1])
            await db.commit()
            item1_id = item1.id
            doc1_id = doc1.id

    admin_sess = AdminMockSession()
    guest_sess = GuestMockSession()

    # 3. Назначаем права гостю через permissions.save:
    # Разрешаем публичное чтение CatalogItem, но НЕ SecretDocument
    save_res = await handle_permissions_save(
        admin_sess,
        target_type="guest",
        target_id=0,
        crud_permissions={
            "CatalogItem": {"can_read": True},
            "SecretDocument": {"can_read": False}
        },
        rpc_permissions=["system.ping", "catalog.search"]
    )
    assert save_res["success"] is True

    # 4. Проверяем permissions.get для гостя
    g_perms = await handle_permissions_get(admin_sess, target_type="guest", target_id=0)
    assert g_perms["target_name"] == "Гости"
    assert g_perms["crud_permissions"]["CatalogItem"]["can_read"] is True
    assert "SecretDocument" not in g_perms["crud_permissions"]
    assert "system.ping" in g_perms["rpc_permissions"]
    assert "login.submit" in g_perms["rpc_permissions"]

    # 5. Проверяем Zero-Leakage в crud.schema для гостя
    guest_schema = await handle_crud_schema(guest_sess, {})
    model_keys = [m["key"] for m in guest_schema["models"]]
    assert "CatalogItem" in model_keys
    assert "SecretDocument" not in model_keys  # Секретная таблица скрыта из схемы

    # 6. Проверяем выборку crud.list для гостя (CQRS Query)
    list_res = await handle_crud_list(guest_sess, {"model": "CatalogItem"})
    assert list_res["$tabular"] is True
    assert list_res["total"] == 2  # Архивный товар отфильтрован
    rows = list_res["rows"]
    titles = [r[list_res["fields"].index("title")] for r in rows]
    assert "Ноутбук" in titles
    assert "Мышь" in titles

    # 7. Проверяем получение карточки crud.get для гостя
    get_res = await handle_crud_get(guest_sess, {"model": "CatalogItem", "id": item1_id})
    assert get_res["record"]["title"] == "Ноутбук"
    assert get_res["record"]["price"] == 50000

    # 8. Проверяем запрет чтения неразрешенной модели (SecretDocument)
    with pytest.raises(RPCError) as exc_list:
        await handle_crud_list(guest_sess, {"model": "SecretDocument"})
    assert "запрещен для гостей" in str(exc_list.value)

    with pytest.raises(RPCError) as exc_get:
        await handle_crud_get(guest_sess, {"model": "SecretDocument", "id": doc1_id})
    assert "запрещен для гостей" in str(exc_get.value)

    # 9. Проверяем абсолютный запрет любых CRUD-мутаций для гостя
    with pytest.raises(RPCError) as exc_create:
        await handle_crud_create(guest_sess, {"model": "CatalogItem", "data": {"title": "Хакерский товар"}})
    assert "Мутации в CRUD запрещены для роли Гость" in str(exc_create.value)

    with pytest.raises(RPCError) as exc_update:
        await handle_crud_update_cell(guest_sess, {"model": "CatalogItem", "id": item1_id, "field": "price", "value": 0})
    assert "Мутации в CRUD запрещены для роли Гость" in str(exc_update.value)

    with pytest.raises(RPCError) as exc_bulk:
        await handle_crud_bulk_update(guest_sess, {"model": "CatalogItem", "ids": [item1_id], "patch": {"price": 0}})
    assert "Мутации в CRUD запрещены для роли Гость" in str(exc_bulk.value)

    with pytest.raises(RPCError) as exc_delete:
        await handle_crud_delete(guest_sess, {"model": "CatalogItem", "id": item1_id})
    assert "Мутации в CRUD запрещены для роли Гость" in str(exc_delete.value)
