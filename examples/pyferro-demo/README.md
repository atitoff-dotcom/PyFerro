# 🚀 PyFerro Showcase & Demo Application

Официальное демонстрационное и обучающее приложение на реактивном фреймворке **PyFerro**.
Служит образцом архитектуры, живым примером использования и E2E-тестером ядра.

---

## 💡 Особенности

- **Изолированная база данных:** Приложение по умолчанию создает и использует локальную базу данных `demo.db` (SQLite). Ваша корпоративная БД остается в полной безопасности.
- **Полнофункциональный SEO-форум:**
  - Древовидная структура разделов и веток (`Topic`, `Message`).
  - Микроразметка Schema.org (`BreadcrumbList`, `DiscussionForumPosting` в JSON-LD).
  - Динамический рендеринг страниц для поисковых ботов (Jinja2).
- **Симметричный JSON-RPC 2.0:** Примеры декларации методов с контролем ролей (RBAC).
- **Готовые сид-данные:** Автоматическое наполнение 10 темами и ветками обсуждений при первом запуске.

---

## ⚡ Быстрый старт

### 1. Установка из PyPI:
```bash
pip install pyferro-demo
```

### 2. Запуск приложения:
```bash
pyferro-demo run
```
или без предварительной установки:
```bash
pipx run pyferro-demo
```

Приложение запустится на Rust-сервере Granian:
- **Админка PyFerro:** [http://localhost:8080/pyferro_admin/](http://localhost:8080/pyferro_admin/) (логин: `admin`, пароль: `admin`)
- **JSON-RPC эндпоинт:** `ws://localhost:8080/wsrpc`
- **Sitemap XML:** [http://localhost:8080/sitemap.xml](http://localhost:8080/sitemap.xml)

---

## 📂 Структура проекта

```text
pyferro_demo/
├── cli.py             # Точка входа консольной команды pyferro-demo
├── app.py             # Фабрика приложения PyFerroApp и регистрация модулей
├── forum/
│   ├── models.py      # SQLAlchemy-модели топиков и сообщений
│   ├── rpc.py         # JSON-RPC 2.0 методы (forum.list_topics, forum.get_topic и т.д.)
│   ├── seeder.py      # Идемпотентный сидинг демонстрационных данных
│   └── seo.py         # Генерация JSON-LD микроразметки и хлебных крошек
└── templates/
    └── forum_topic.html # Шаблон Jinja2 для Dynamic Rendering
```

---

## 🧪 Запуск тестов

```bash
pytest
```
