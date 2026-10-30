"""
Демо-сидер для стартера SEO-форума (tst_topics, tst_messages).
Заливает 10 тем с глубокой древовидной вложенностью и реалистичными обсуждениями.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from pyferro2.starters.models import TstMessage, TstTopic


async def seed_forum_data(session: AsyncSession) -> dict[str, int]:
    """
    Заполняет базу данных 10 темами разной вложенности и цепочками сообщений.
    Возвращает статистику: {"topics": count, "messages": count}.
    """
    now = datetime.now(timezone.utc)

    # 1. Корневой раздел 1
    t1 = TstTopic(
        title="Общие дискуссии",
        slug="general",
        is_category=True,
        seo_title="Общие темы и новости сообщества PyFerro",
        seo_description="Корневой раздел общих обсуждений, анонсов и правил проекта PyFerro.",
        created_at=now - timedelta(days=10),
    )
    session.add(t1)
    await session.flush()

    # 2. Подраздел новостей (внутри 1)
    t2 = TstTopic(
        parent_id=t1.id,
        title="Новости и анонсы",
        slug="news",
        is_category=True,
        seo_title="Официальные новости и релизы",
        seo_description="Все официальные новости фреймворка, релиз-ноты и важные изменения.",
        created_at=now - timedelta(days=9),
    )
    session.add(t2)
    await session.flush()

    # 3. Ветка обсуждения релиза (внутри 2)
    t3 = TstTopic(
        parent_id=t2.id,
        title="Релиз PyFerro 2.0: архитектура и возможности",
        slug="pyferro-2-0-release",
        is_category=False,
        seo_title="Обсуждение релиза PyFerro 2.0",
        seo_description="Подробный разбор архитектуры PyFerro 2.0: Rust-сервер Granian, RSGI, JSON-RPC и Svelte 5.",
        created_at=now - timedelta(days=8),
    )
    session.add(t3)

    # 4. Ветка дорожной карты (внутри 2)
    t4 = TstTopic(
        parent_id=t2.id,
        title="Дорожная карта развития на 2026 год",
        slug="roadmap-2026",
        is_category=False,
        seo_title="Roadmap PyFerro 2026",
        seo_description="Планы развития платформы: поддержка новых протоколов, плагины и масштабирование.",
        created_at=now - timedelta(days=7),
    )
    session.add(t4)

    # 5. Тема правил (внутри 1)
    t5 = TstTopic(
        parent_id=t1.id,
        title="Правила форума и оформления кода",
        slug="rules",
        is_category=False,
        seo_title="Правила сообщества PyFerro",
        seo_description="Рекомендации по созданию веток, культуре общения и форматированию сниппетов кода.",
        created_at=now - timedelta(days=6),
    )
    session.add(t5)
    await session.flush()

    # 6. Корневой раздел 2: Разработка
    t6 = TstTopic(
        title="Разработка и архитектура",
        slug="development",
        is_category=True,
        seo_title="Разработка бэкенда и интерфейсов",
        seo_description="Технический раздел: архитектура сервисов, базы данных, API и фронтенд.",
        created_at=now - timedelta(days=5),
    )
    session.add(t6)
    await session.flush()

    # 7. Подраздел бэкенда (внутри 6)
    t7 = TstTopic(
        parent_id=t6.id,
        title="Бэкенд и базы данных",
        slug="backend-db",
        is_category=True,
        seo_title="Архитектура бэкенда и хранилищ данных",
        seo_description="Вопросы производительности SQLite WAL, асинхронного SQLAlchemy и пулов соединений.",
        created_at=now - timedelta(days=4),
    )
    session.add(t7)
    await session.flush()

    # 8. Ветка SQLite WAL (внутри 7)
    t8 = TstTopic(
        parent_id=t7.id,
        title="Асинхронный SQLAlchemy и WAL-режим SQLite",
        slug="async-sqlalchemy-sqlite-wal",
        is_category=False,
        seo_title="Настройка SQLite WAL в асинхронном Python",
        seo_description="Практические советы по устранению блокировок 'database is locked' при параллельных чтениях.",
        created_at=now - timedelta(days=3),
    )
    session.add(t8)

    # 9. Ветка RPC vs REST (внутри 7)
    t9 = TstTopic(
        parent_id=t7.id,
        title="JSON-RPC 2.0 против REST: бенчмарки и опыт",
        slug="json-rpc-vs-rest-benchmarks",
        is_category=False,
        seo_title="Сравнение производительности JSON-RPC и REST",
        seo_description="Почему бинарные контракты и пакетные JSON-RPC вызовы экономят трафик и ускоряют клиент.",
        created_at=now - timedelta(days=2),
    )
    session.add(t9)

    # 10. Ветка фронтенда (внутри 6)
    t10 = TstTopic(
        parent_id=t6.id,
        title="Svelte 5 Runes в панели управления",
        slug="svelte-5-runes-admin",
        is_category=False,
        seo_title="Использование Svelte 5 Runes в админке",
        seo_description="Опыт миграции на руны $state, $derived и $effect в интерфейсах администрирования.",
        created_at=now - timedelta(days=1),
    )
    session.add(t10)
    await session.flush()

    # Создаем реалистичные цепочки сообщений
    messages = [
        # Для темы 3 (Релиз 2.0)
        TstMessage(
            topic_id=t3.id,
            author_name="Алексей (Maintainer)",
            content="Рад представить PyFerro 2.0! Главный акцент сделан на скорости, строгой типизации и чистом SEO.",
            created_at=now - timedelta(days=8, hours=2),
        ),
        TstMessage(
            topic_id=t3.id,
            author_name="Елена",
            content="Поздравляю с релизом! Как в новой версии строится карта сайта sitemap.xml?",
            created_at=now - timedelta(days=7, hours=10),
        ),
        TstMessage(
            topic_id=t3.id,
            author_name="Алексей (Maintainer)",
            content="Sitemap строится динамически с рекурсивным обходом дерева и вычислением lastmod по свежим постам.",
            created_at=now - timedelta(days=7, hours=8),
        ),
        # Для темы 4 (Roadmap)
        TstMessage(
            topic_id=t4.id,
            author_name="Дмитрий",
            content="В планах на 2026 год — расширение каталога готовых стартеров и визуальный редактор разметки.",
            created_at=now - timedelta(days=6),
        ),
        # Для темы 5 (Правила)
        TstMessage(
            topic_id=t5.id,
            author_name="Модератор",
            content="Правило №1: Пожалуйста, форматируйте код в тройных обратных кавычках и будьте вежливы.",
            created_at=now - timedelta(days=5),
        ),
        # Для темы 8 (SQLite WAL)
        TstMessage(
            topic_id=t8.id,
            author_name="Сергей",
            content="Почему важно включать synchronous=NORMAL при WAL-режиме в SQLite?",
            created_at=now - timedelta(days=3),
        ),
        TstMessage(
            topic_id=t8.id,
            author_name="Алексей (Maintainer)",
            content="Это дает огромный прирост скорости записи без риска повреждения базы при сбоях процессов ОС.",
            created_at=now - timedelta(days=2, hours=14),
        ),
        # Для темы 9 (JSON-RPC)
        TstMessage(
            topic_id=t9.id,
            author_name="Михаил",
            content="За счет отсутствия избыточных заголовков JSON-RPC в WebSocket работает существенно быстрее REST.",
            created_at=now - timedelta(days=2),
        ),
        # Для темы 10 (Svelte 5)
        TstMessage(
            topic_id=t10.id,
            author_name="Ольга",
            content="С рунами $state и $effect код компонентов админки стал на 30% чище и избавился от сторов.",
            created_at=now - timedelta(hours=12),
        ),
    ]

    for m in messages:
        session.add(m)

    await session.commit()
    return {"topics": 10, "messages": len(messages)}
