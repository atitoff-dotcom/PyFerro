# -*- coding: utf-8 -*-
"""
Тест-сьют: Гранулярная матрица CRUD-прав (C R U D: Запрет / Свои / Все) и Делегирование (Замещение).
"""

import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import select

from pyferro import system_db_session
from pyferro.auth.models import User, Role, RolePermission, UserDelegation
from pyferro.auth.security import _check_cud_action
from pyferro.auth.core import RowSecureModel


class SampleArticle(RowSecureModel):
    __tablename__ = "test_sample_articles"
    # Наследует id, creator_id, owner_id, team_id, created_at, updated_at


@pytest.mark.asyncio
async def test_granular_crud_scopes():
    """
    Проверяет сценарий:
    Чтение: Все записи (read_global=True)
    Изменение: Только свои записи (update_global=False)
    """
    # 1. Создаем контекст пользователя
    user_alice = type("UserContext", (), {
        "user_id": 101,
        "team_ids": [],
        "delegated_user_ids": [],
        "is_superadmin": False,
        "perms_dict": {
            "SampleArticle": {
                "can_read": True,
                "read_global": True,        # Читает ВСЕ записи
                "can_update": True,
                "update_global": False,      # Изменяет ТОЛЬКО СВОИ записи
                "can_delete": False,
                "delete_global": False,
                "can_create": True,
            }
        }
    })()

    # Запись, созданная Бобом (чужая для Алисы)
    bob_article = SampleArticle()
    bob_article.id = 1
    bob_article.creator_id = 202
    bob_article.owner_id = 202

    # Запись, созданная Алисой
    alice_article = SampleArticle()
    alice_article.id = 2
    alice_article.creator_id = 101
    alice_article.owner_id = 101

    # Алиса может изменять свою запись
    _check_cud_action(user_alice, alice_article, "update")

    # Алиса НЕ может изменять чужую запись (bob_article) -> PermissionError
    with pytest.raises(PermissionError) as exc_info:
        _check_cud_action(user_alice, bob_article, "update")
    assert "Нет прав на update чужой записи" in str(exc_info.value)


@pytest.mark.asyncio
async def test_delegation_substitution():
    """
    Проверяет механизм делегирования:
    Алиса замещает Боба -> получает право редактировать записи Боба.
    """
    # Алиса замещает Боба (delegated_user_ids=[202])
    user_alice_substitute = type("UserContext", (), {
        "user_id": 101,
        "team_ids": [],
        "delegated_user_ids": [202],        # Активно замещает Боба!
        "is_superadmin": False,
        "perms_dict": {
            "SampleArticle": {
                "can_read": True,
                "read_global": False,       # Только свои
                "can_update": True,
                "update_global": False,     # Только свои
                "can_delete": False,
                "delete_global": False,
                "can_create": True,
            }
        }
    })()

    bob_article = SampleArticle()
    bob_article.id = 1
    bob_article.creator_id = 202
    bob_article.owner_id = 202

    # Теперь Алиса МОЖЕТ редактировать статью Боба, так как Боб в её активных замещениях
    _check_cud_action(user_alice_substitute, bob_article, "update")

    # Но Алиса НЕ может редактировать статью Чарли (303)
    charlie_article = SampleArticle()
    charlie_article.id = 3
    charlie_article.creator_id = 303
    charlie_article.owner_id = 303

    with pytest.raises(PermissionError):
        _check_cud_action(user_alice_substitute, charlie_article, "update")


@pytest.mark.asyncio
async def test_user_delegation_active_window():
    """
    Проверяет метод get_delegated_user_ids с учетом временного окна.
    """
    now = datetime.now(timezone.utc)
    user = User(name="Alice", login="alice_del")

    # 1. Активное замещение
    d1 = UserDelegation(
        from_user_id=202,
        to_user_id=101,
        valid_from=now - timedelta(days=1),
        valid_to=now + timedelta(days=1),
        is_active=True
    )

    # 2. Истекшее замещение (вчера)
    d2 = UserDelegation(
        from_user_id=303,
        to_user_id=101,
        valid_from=now - timedelta(days=5),
        valid_to=now - timedelta(days=1),
        is_active=True
    )

    # 3. Будущее замещение (со следующей недели)
    d3 = UserDelegation(
        from_user_id=404,
        to_user_id=101,
        valid_from=now + timedelta(days=2),
        valid_to=now + timedelta(days=5),
        is_active=True
    )

    user.delegations_received = [d1, d2, d3]
    active_ids = user.get_delegated_user_ids()

    assert active_ids == [202], f"Ожидался только активный ID 202, получено {active_ids}"
