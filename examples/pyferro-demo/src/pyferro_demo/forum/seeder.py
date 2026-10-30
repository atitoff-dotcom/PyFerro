"""
Демо-сидер для форума: наполнение разделами и сообщениями.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pyferro_demo.forum.models import Message, Topic


async def seed_forum_data(session: AsyncSession) -> dict[str, int]:
    """
    Идемпотентно заполняет базу данных темами и сообщениями, если она пуста.
    """
    res = await session.execute(select(Topic))
    if res.scalars().first() is not None:
        return {"topics": 0, "messages": 0}

    now = datetime.now(timezone.utc)

    # 1. Корневой раздел 1
    t1 = Topic(
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
    t2 = Topic(
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
    t3 = Topic(
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
    t4 = Topic(
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
    t5 = Topic(
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
    t6 = Topic(
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
    t7 = Topic(
        parent_id=t6.id,
        title="Бэкенд и базы данных",
        slug="backend-db",
        is_category=True,
        seo_title="Бэкенд на Rust RSGI и SQLAlchemy",
        seo_description="Обсуждение асинхронного движка, моделей SQLAlchemy и производительности.",
        created_at=now - timedelta(days=4),
    )
    session.add(t7)
    await session.flush()

    # 8. Топик о производительности Granian (внутри 7)
    t8 = Topic(
        parent_id=t7.id,
        title="Бенчмарки Granian RSGI против Uvicorn",
        slug="granian-vs-uvicorn",
        is_category=False,
        seo_title="Сравнение производительности Granian и Uvicorn",
        seo_description="Тесты RPS и задержек: как Rust-рантайм Granian ускоряет асинхронный Python.",
        created_at=now - timedelta(days=3),
    )
    session.add(t8)

    # 9. Топик о сжатии Tabular RPC (внутри 7)
    t9 = Topic(
        parent_id=t7.id,
        title="Сжатие данных Tabular: экономия сетевого трафика до 80%",
        slug="tabular-compression",
        is_category=False,
        seo_title="Экономия трафика с Tabular RPC",
        seo_description="Разбор протокола Tabular для передачи списков словарей через WebSocket.",
        created_at=now - timedelta(days=2),
    )
    session.add(t9)

    # 10. Топик о SEO и Dynamic Rendering (внутри 6)
    t10 = Topic(
        parent_id=t6.id,
        title="Dynamic Rendering: идеальная индексация SPA для Google и Яндекса",
        slug="dynamic-rendering-guide",
        is_category=False,
        seo_title="Руководство по Dynamic Rendering в PyFerro",
        seo_description="Практика настройки Jinja2-шаблонов, IndexNow и карты сайта sitemap.xml для SPA.",
        created_at=now - timedelta(days=1),
    )
    session.add(t10)
    await session.flush()

    # Наполняем сообщениями
    m1 = Message(
        topic_id=t3.id,
        author_name="Алексей (Архитектор)",
        content="Коллеги, рад представить PyFerro 2.0! Платформа переведена на Rust RSGI (Granian), что снизило задержки до микросекунд.",
        created_at=now - timedelta(days=8, hours=2),
    )
    m2 = Message(
        topic_id=t3.id,
        author_name="Дмитрий (DevOps)",
        content="Отличный релиз! Проверили сборку Docker-образов — вес минимальный, потребление памяти снизилось на 40%.",
        created_at=now - timedelta(days=7, hours=18),
    )
    m3 = Message(
        topic_id=t8.id,
        author_name="Иван (Senior Python)",
        content="В синтетических тестах Granian держит 45k RPS на одном ядре при нулевом дропе пакетов. Это лучший результат в Python экосистеме.",
        created_at=now - timedelta(days=3, hours=1),
    )
    m4 = Message(
        topic_id=t9.id,
        author_name="Мария (Frontend)",
        content="Tabular Data Compression сработал отлично в гридах админки: загрузка 10,000 строк теперь занимает миллисекунды.",
        created_at=now - timedelta(days=2, hours=3),
    )
    m5 = Message(
        topic_id=t10.id,
        author_name="Сергей (SEO-специалист)",
        content="Боты поисковиков видят чистый HTML с разметкой Schema.org, а живые пользователи получают реактивный SPA. Идеальный баланс!",
        created_at=now - timedelta(days=1, hours=4),
    )

    session.add_all([m1, m2, m3, m4, m5])
    await session.commit()

    return {"topics": 10, "messages": 5}
