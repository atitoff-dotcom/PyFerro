"""
Модульные тесты Этапа 2: база данных (`pyferro2/db/`) и модели авторизации (`pyferro2/auth/`).
"""

import pytest
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from pyferro2.auth import (
    Role,
    User,
    ensure_admin_user,
    hash_password,
    load_guest_session_data,
    seed_system_roles,
    verify_password,
)
from pyferro2.core import GUEST_SESSION_DATA, SYSTEM_ROLES, USER_ROLE, admRole
from pyferro2.db import Database, RowSecureModel


class SampleArticle(RowSecureModel):
    """Тестовая прикладная модель для проверки RowSecureModel."""

    __tablename__ = "pf_test_article"

    title: Mapped[str] = mapped_column(String(120), nullable=False)


@pytest.fixture
async def db() -> Database:
    """Создает изолированную in-memory SQLite базу для каждого теста."""
    database = Database("sqlite+aiosqlite:///:memory:")
    await database.create_tables()
    yield database
    await database.close()


class TestPasswords:
    """Проверка криптографического хэширования паролей (`hashlib.scrypt`)."""

    def test_hash_and_verify_password(self) -> None:
        h1 = hash_password("MySecret123!")
        h2 = hash_password("MySecret123!")
        # Соль всегда случайная, поэтому хэши одного пароля отличаются
        assert h1 != h2
        assert h1.startswith("scrypt$")
        assert verify_password("MySecret123!", h1) is True
        assert verify_password("WrongPassword", h1) is False

    def test_invalid_password_inputs(self) -> None:
        with pytest.raises(ValueError):
            hash_password("")
        assert verify_password("", "scrypt$aa$bb") is False
        assert verify_password("pass", "") is False
        assert verify_password("pass", "invalid_format") is False
        assert verify_password("pass", "scrypt$not_hex$bb") is False


class TestDatabaseAndModels:
    """Проверка схемы БД, сидинга, связок User-Role-Permission и защиты системных ролей."""

    def test_clean_schema_no_legacy_columns(self) -> None:
        user_cols = set(User.__table__.columns.keys())
        assert user_cols == {"id", "username", "password_hash", "email", "full_name", "is_active"}
        # Никаких легаси-полей в таблице пользователя
        assert "login" not in user_cols
        assert "is_admin" not in user_cols
        assert "is_superadmin" not in user_cols
        assert "admin_roles" not in user_cols

        article_cols = set(SampleArticle.__table__.columns.keys())
        assert article_cols == {"id", "creator_id", "created_at", "updated_at", "title"}
        assert "team_id" not in article_cols
        assert "owner_id" not in article_cols

    @pytest.mark.asyncio
    async def test_row_secure_model_persistence(self, db: Database) -> None:
        async with db.session() as session:
            article = SampleArticle(title="Hello PyFerro 2", creator_id=5)
            session.add(article)
            await session.commit()

            assert article.id == 1
            assert article.creator_id == 5
            assert article.created_at is not None
            assert article.updated_at is not None

    @pytest.mark.asyncio
    async def test_boot_seeder_idempotency(self, db: Database) -> None:
        async with db.session() as session:
            roles_first = await seed_system_roles(session)
            assert set(roles_first.keys()) == SYSTEM_ROLES
            assert all(r.is_system is True for r in roles_first.values())

            # Повторный запуск не создает дубликатов
            roles_second = await seed_system_roles(session)
            assert len(roles_second) == len(SYSTEM_ROLES)

    @pytest.mark.asyncio
    async def test_system_role_protection_against_delete_and_rename(self, db: Database) -> None:
        async with db.session() as session:
            roles = await seed_system_roles(session)
            admin_role = roles[admRole.admin.value]

            # 1. Запрет удаления системной роли
            await session.delete(admin_role)
            with pytest.raises(ValueError, match="Запрещено удалять системную роль"):
                await session.commit()
            await session.rollback()

        async with db.session() as session:
            roles = await seed_system_roles(session)
            crud_role = roles[admRole.adm_crud.value]

            # 2. Запрет переименования системной роли
            crud_role.name = "hacked_crud"
            with pytest.raises(ValueError, match="Запрещено переименовывать системную роль"):
                await session.commit()
            await session.rollback()

        async with db.session() as session:
            roles = await seed_system_roles(session)
            guest_role = roles["guest"]

            # 3. Запрет снятия флага is_system
            guest_role.is_system = False
            with pytest.raises(ValueError, match="Запрещено снимать флаг is_system"):
                await session.commit()
            await session.rollback()

        async with db.session() as session:
            roles = await seed_system_roles(session)
            guest_role = roles["guest"]

            # При этом менять описание или добавлять разрешения системной роли разрешено
            guest_role.description = "Обновленное описание гостя"
            guest_role.add_permission("catalog.public_list")
            await session.commit()

            guest_data = await load_guest_session_data(session)
            assert guest_data.is_guest is True
            assert guest_data.has_permission("catalog.public_list") is True

    @pytest.mark.asyncio
    async def test_custom_role_lifecycle_and_user_session_data(self, db: Database) -> None:
        async with db.session() as session:
            roles = await seed_system_roles(session)

            # Создаем кастомную бизнес-роль
            manager_role = Role(name="manager", description="Менеджер заказов", is_system=False)
            manager_role.add_permission("orders.dispatch")
            manager_role.add_permission("Order:read")
            manager_role.add_permission("Order:update")
            # Повторное добавление того же права игнорируется
            manager_role.add_permission("Order:read")
            session.add(manager_role)

            user_role = roles[USER_ROLE]
            user_role.add_permission("profile.view")

            user = User(
                username="elena",
                password_hash=hash_password("SecretPass!"),
                email="elena@example.com",
                full_name="Елена Смирнова",
                roles=[user_role, manager_role, roles[admRole.adm_crud.value]],
            )
            session.add(user)
            await session.commit()

            assert user.check_password("SecretPass!") is True
            assert user.check_password("wrong") is False

            # Превращаем пользователя в неизменяемый SessionData (как при логине)
            session_data = user.to_session_data()
            assert session_data.user_id == user.id
            assert session_data.username == "elena"
            assert session_data.is_admin is False
            assert session_data.roles == frozenset({"user", "manager", "adm_crud"})
            assert session_data.permissions == frozenset(
                {"profile.view", "orders.dispatch", "Order:read", "Order:update"}
            )
            assert session_data.has_permission("orders.dispatch") is True
            assert session_data.has_permission("Order:delete") is False
            assert session_data.has_admin_access("crud") is True
            assert session_data.has_admin_access("users") is False

            # Удаляем одно право у роли manager
            manager_role.remove_permission("Order:update")
            await session.commit()
            assert manager_role.get_permissions() == frozenset({"orders.dispatch", "Order:read"})

            # Несистемную роль можно переименовать и удалить
            manager_role.name = "senior_manager"
            await session.commit()
            await session.delete(manager_role)
            await session.commit()

    @pytest.mark.asyncio
    async def test_ensure_admin_user(self, db: Database) -> None:
        async with db.session() as session:
            # До сидинга гость возвращает базовый синглтон
            initial_guest = await load_guest_session_data(session)
            assert initial_guest is GUEST_SESSION_DATA

            admin = await ensure_admin_user(session, username="root", password="RootPassword1!")
            assert admin.username == "root"
            assert admin.check_password("RootPassword1!") is True

            admin_sd = admin.to_session_data()
            assert admin_sd.is_admin is True
            assert admin_sd.has_permission("anything") is True
            assert admin_sd.has_admin_access("roles") is True
