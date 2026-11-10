"""
Интеграционные тесты подсистемы автоматического кеширования, ETag, авто-инвалидации SQLAlchemy
и идемпотентности оффлайн-очереди в PyFerro 2.0 (`tests/cache/test_cache_and_offline.py`).
"""

from pathlib import Path
from typing import Any
import orjson
import pytest
from sqlalchemy import String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from pyferro2.auth import ensure_admin_user, seed_system_roles
from pyferro2.auth.seeder import load_guest_session_data
from pyferro2.core import Session, USER_ROLE
from pyferro2.db import Base, Database
from pyferro2.rpc import RpcRouter
from pyferro2.server import (
    MockRSGIScope,
    MockRSGIWebsocketProtocol,
    PyFerroApp,
    make_ws_close,
    make_ws_message,
)


class CatalogCrop(Base):
    __tablename__ = "test_catalog_crops"

    title: Mapped[str] = mapped_column(String(120), nullable=False)
    image_url: Mapped[str] = mapped_column(String(255), default="", nullable=False)


@pytest.fixture
async def cache_app(tmp_path: Path) -> tuple[PyFerroApp, dict[str, int]]:
    db = Database("sqlite+aiosqlite:///:memory:")
    router = RpcRouter()
    call_counter = {"get_crops": 0, "create_crop": 0}

    class Catalog:
        @router.rpc_method(public=True)
        async def get_crops(db: AsyncSession) -> list[dict[str, Any]]:
            call_counter["get_crops"] += 1
            rows = (await db.execute(select(CatalogCrop).order_by(CatalogCrop.id))).scalars().all()
            return [{"id": r.id, "title": r.title, "image_url": r.image_url} for r in rows]

        @router.rpc_method(public=True)
        async def add_crop(db: AsyncSession, title: str, image_url: str = "") -> dict[str, Any]:
            call_counter["create_crop"] += 1
            crop = CatalogCrop(title=title, image_url=image_url)
            db.add(crop)
            await db.commit()
            await db.refresh(crop)
            return {"id": crop.id, "title": crop.title, "image_url": crop.image_url}

    app = PyFerroApp(db=db, router=router)
    app.crud.register(CatalogCrop)
    await app.startup()

    async with db.session() as session:
        await ensure_admin_user(session, "admin", "AdminPass123!")
        roles = await seed_system_roles(session)
        roles["guest"].add_permission("CatalogCrop.read")
        roles[USER_ROLE].add_permission("CatalogCrop.read")
        roles[USER_ROLE].add_permission("CatalogCrop.create")
        await session.commit()
        app.guest_session_data = await load_guest_session_data(session)

    yield app, call_counter
    await app.shutdown()


class TestCacheAndOfflineEngine:
    async def test_admin_settings_and_manifest(self, cache_app: tuple[PyFerroApp, dict[str, int]]) -> None:
        """Проверка настройки правил кеша через `cache.get_settings` / `cache.save_settings` и манифеста."""
        app, _ = cache_app
        async with app.db.session() as db_sess:
            admin_user = await ensure_admin_user(db_sess, "admin", "AdminPass123!")
            admin_sd = admin_user.to_session_data()

        admin_session = Session(session_id="test-adm", data=admin_sd)

        settings = await app.router.call("cache.get_settings", admin_session, {}, db=app.db)
        assert settings["config"]["enabled"] is True
        method_names = [m["name"] for m in settings["methods"]]
        assert "Catalog.get_crops" in method_names
        assert "Catalog.add_crop" in method_names
        assert "CatalogCrop.read" in method_names

        save_res = await app.router.call(
            "cache.save_settings",
            admin_session,
            {
                "config": {
                    "enabled": True,
                    "liefi_timeout_ms": 2000,
                    "max_media_mb": 300,
                    "max_rpc_entries": 1500,
                },
                "rules": [
                    {
                        "method_name": "Catalog.get_crops",
                        "cache_enabled": True,
                        "strategy": "auto",
                        "ttl_sec": 600,
                        "prefetch_media": True,
                        "preload_on_boot": True,
                        "offline_outbox": False,
                    },
                    {
                        "method_name": "Catalog.add_crop",
                        "cache_enabled": False,
                        "strategy": "auto",
                        "ttl_sec": 300,
                        "prefetch_media": False,
                        "preload_on_boot": False,
                        "offline_outbox": True,
                    },
                ],
            },
            db=app.db,
        )
        assert save_res["status"] == "saved"

        manifest = await app.router.call("cache.get_manifest", admin_session, {}, db=app.db)
        assert manifest["liefi_timeout_ms"] == 2000
        assert manifest["max_media_mb"] == 300
        assert "Catalog.get_crops" in manifest["rules"]
        assert manifest["rules"]["Catalog.get_crops"]["c"] == 1
        assert manifest["rules"]["Catalog.get_crops"]["m"] == 1
        assert manifest["rules"]["Catalog.get_crops"]["p"] == 1
        assert manifest["rules"]["Catalog.add_crop"]["o"] == 1

    async def test_l1_cache_etag_and_auto_sqlalchemy_invalidation(
        self, cache_app: tuple[PyFerroApp, dict[str, int]]
    ) -> None:
        """
        Проверка полного цикла:
        1. Сохранение правила кеширования для `Catalog.get_crops`.
        2. Первый вызов идет в БД, возвращает `$cache.etag`.
        3. Второй вызов берется из L1-кеша без вызова Python-хендлера.
        4. Третий вызов с `$if_none_match` возвращает `{"$not_modified": True}`.
        5. Вызов `Catalog.add_crop` делает `db.commit()`, что автоматически сбрасывает L1-кеш
           и рассылает по WebSocket уведомление `$cache.invalidate`.
        """
        app, counter = cache_app
        async with app.db.session() as db_sess:
            admin_user = await ensure_admin_user(db_sess, "admin", "AdminPass123!")
            admin_sd = admin_user.to_session_data()

        admin_session = Session(session_id="test-adm", data=admin_sd)
        await app.router.call(
            "cache.save_settings",
            admin_session,
            {
                "config": {"enabled": True, "liefi_timeout_ms": 2500, "max_media_mb": 250, "max_rpc_entries": 2000},
                "rules": [
                    {
                        "method_name": "Catalog.get_crops",
                        "cache_enabled": True,
                        "strategy": "auto",
                        "ttl_sec": 600,
                        "prefetch_media": True,
                    }
                ],
            },
            db=app.db,
        )

        guest_session = Session(session_id="guest-1", data=app.guest_session_data)

        # Добавим одну культуру до первого чтения
        await app.router.call(
            "Catalog.add_crop",
            guest_session,
            {"title": "Перец сладкий", "image_url": "/files/abc123/1.webp"},
            db=app.db,
        )
        assert counter["get_crops"] == 0

        # 1. Первый запрос чтения -> промах кеша, выполнение SQL
        raw1 = await app.router.handle_packet(
            {"jsonrpc": "2.0", "id": 1, "method": "Catalog.get_crops", "params": {}},
            guest_session,
            db=app.db,
        )
        assert raw1 is not None
        pkt1 = orjson.loads(raw1)
        assert len(pkt1["result"]) == 1
        assert pkt1["result"][0]["title"] == "Перец сладкий"
        assert "$cache" in pkt1
        etag1 = pkt1["$cache"]["etag"]
        assert pkt1["$cache"]["scope"] == "public"
        assert pkt1["$cache"]["prefetch_media"] is True
        assert counter["get_crops"] == 1

        # 2. Второй запрос чтения -> попадание в L1-кеш (счетчик вызовов хендлера НЕ растет)
        raw2 = await app.router.handle_packet(
            {"jsonrpc": "2.0", "id": 2, "method": "Catalog.get_crops", "params": {}},
            guest_session,
            db=app.db,
        )
        assert raw2 is not None
        pkt2 = orjson.loads(raw2)
        assert len(pkt2["result"]) == 1
        assert pkt2["$cache"]["etag"] == etag1
        assert counter["get_crops"] == 1

        # 3. Запрос с $if_none_match == etag1 -> мгновенный ответ $not_modified
        raw3 = await app.router.handle_packet(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "Catalog.get_crops",
                "params": {},
                "$if_none_match": etag1,
            },
            guest_session,
            db=app.db,
        )
        assert raw3 is not None
        pkt3 = orjson.loads(raw3)
        assert pkt3["result"] == {"$not_modified": True}
        assert counter["get_crops"] == 1

        # 4. Подключим WebSocket-клиент и проверим, что при записи в таблицу test_catalog_crops
        # сервер сам инвалидирует кеш и пришлет уведомление $cache.invalidate
        ws_scope = MockRSGIScope(proto="ws", path="/ws")
        ws_proto = MockRSGIWebsocketProtocol([
            make_ws_message(
                orjson.dumps({
                    "jsonrpc": "2.0",
                    "id": 10,
                    "method": "Catalog.add_crop",
                    "params": {"title": "Голубика высокорослая", "image_url": "/files/def456/2.webp"},
                }).decode("utf-8")
            ),
            make_ws_close(),
        ])
        await app(ws_scope, ws_proto)

        sent_frames = [orjson.loads(f) for f in ws_proto.transport.sent_messages]
        invalidate_frames = [f for f in sent_frames if f.get("method") == "$cache.invalidate"]
        assert len(invalidate_frames) >= 1
        assert "Catalog.get_crops" in invalidate_frames[0]["params"]["methods"]

        # 5. Теперь запрос с прежним etag1 возвращает уже свежие данные (2 культуры) и новый etag2!
        raw4 = await app.router.handle_packet(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "Catalog.get_crops",
                "params": {},
                "$if_none_match": etag1,
            },
            guest_session,
            db=app.db,
        )
        assert raw4 is not None
        pkt4 = orjson.loads(raw4)
        assert isinstance(pkt4["result"], list)
        assert len(pkt4["result"]) == 2
        assert pkt4["$cache"]["etag"] != etag1
        assert counter["get_crops"] == 2

    async def test_idempotency_key_prevents_duplicate_offline_mutations(
        self, cache_app: tuple[PyFerroApp, dict[str, int]]
    ) -> None:
        """Проверка защиты от дублирования при отправке мутаций из `rpc_outbox` с `$idempotency_key`."""
        app, counter = cache_app
        guest_session = Session(session_id="guest-idem", data=app.guest_session_data)
        idem_key = "outbox-tx-99887766"

        raw1 = await app.router.handle_packet(
            {
                "jsonrpc": "2.0",
                "id": 101,
                "method": "Catalog.add_crop",
                "params": {"title": "Огурец партенокарпический"},
                "$idempotency_key": idem_key,
            },
            guest_session,
            db=app.db,
        )
        assert raw1 is not None
        res1 = orjson.loads(raw1)["result"]
        assert res1["title"] == "Огурец партенокарпический"
        assert counter["create_crop"] == 1

        # Повторная отправка того же пакета (например, после обрыва связи) с тем же $idempotency_key
        raw2 = await app.router.handle_packet(
            {
                "jsonrpc": "2.0",
                "id": 102,
                "method": "Catalog.add_crop",
                "params": {"title": "Огурец партенокарпический"},
                "$idempotency_key": idem_key,
            },
            guest_session,
            db=app.db,
        )
        assert raw2 is not None
        res2 = orjson.loads(raw2)["result"]
        assert res2["id"] == res1["id"]
        assert counter["create_crop"] == 1
