# 🤖 ИИ-Промт обновления приложения: PyFerro v0.5.13 ➔ v0.5.14

> **Инструкция для разработчика:**  
> Скопируйте текст в блоке ниже и отправьте его вашему ИИ-ассистенту (Cursor, Antigravity, Claude Code, Windsurf, Copilot) в корне вашего проекта. ИИ выполнит аудит, резервное копирование, миграцию схемы БД и адаптацию кода моделей.

---

```markdown
Ты — ведущий инженер по миграции приложения на PyFerro v0.5.14.
Твоя задача — безопасно обновить этот проект, схему базы данных и прикладной код до актуальных контрактов v0.5.14 без потери данных и без простоя.

Контекст изменений v0.5.14:
1. Гранулярные скоупы CRUD-прав: в системных таблицах прав `auth_role_permissions` и `auth_user_permissions` добавлены колонки `read_global`, `update_global`, `delete_global` (вместо единого флага `row_level_only`).
2. Разделение автора и владельца в Row-Level Security: базовый класс `RowSecureModel` получил колонку `owner_id` (текущий ответственный/владелец). Поле `creator_id` теперь зафиксировано как неизменяемый аудит создания (Immutable).
3. Новая подсистема делегирования полномочий: добавлена таблица `auth_user_delegation`.

Выполни миграцию строго по следующим шагам:

### ШАГ 1. Аудит проекта и моделей (Read-Only)
1. Найди файл зависимостей (`requirements.txt`, `pyproject.toml` или `Pipfile`) и обнови версию `pyferro` до `^0.5.14`.
2. Найди все модели SQLAlchemy в проекте, которые наследуются от `RowSecureModel` (или имеют поле `creator_id`).
3. Зафиксируй имена таблиц этих моделей (например: `tasks`, `documents`, `orders` и т.д.).

### ШАГ 2. Резервное копирование БД (Zero-Data-Loss)
Перед выполнением любых DDL/DML запросов создай резервную копию базы данных:
- Для SQLite: выполни `VACUUM INTO 'backup_pre_v0514.db'` или скопируй файл базы.
- Для PostgreSQL: убедись в наличии транзакционного блока или сделай быстрый дамп.

### ШАГ 3. Миграция базы данных (DDL & DML)
Выполни следующие SQL-миграции (через встроенный скрипт или Alembic):

1. **Обновление системных таблиц прав (`auth_role_permissions` и `auth_user_permissions`):**
   - Добавь колонки:
     - `read_global BOOLEAN NOT NULL DEFAULT 0`
     - `update_global BOOLEAN NOT NULL DEFAULT 0`
     - `delete_global BOOLEAN NOT NULL DEFAULT 0`
   - Перенеси старые разрешения (DML):
     ```sql
     -- Если ранее было разрешено всё (row_level_only = 0), даем глобальные права
     UPDATE auth_role_permissions 
     SET read_global = 1, update_global = 1, delete_global = 1 
     WHERE row_level_only = 0 OR row_level_only IS NULL;

     UPDATE auth_user_permissions 
     SET read_global = 1, update_global = 1, delete_global = 1 
     WHERE row_level_only = 0 OR row_level_only IS NULL;
     ```

2. **Создание таблицы делегирования полномочий (`auth_user_delegation`):**
   ```sql
   CREATE TABLE IF NOT EXISTS auth_user_delegation (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       from_user_id INTEGER NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
       to_user_id INTEGER NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
       model_name VARCHAR(100),
       valid_from DATETIME,
       valid_to DATETIME,
       is_active BOOLEAN NOT NULL DEFAULT 1,
       created_at DATETIME DEFAULT CURRENT_TIMESTAMP
   );
   CREATE INDEX IF NOT EXISTS ix_auth_delegation_lookup 
   ON auth_user_delegation (to_user_id, is_active);
   ```

3. **Обновление прикладных таблиц (`RowSecureModel`):**
   Для каждой пользовательской таблицы с `RowSecureModel` (найденной на Шаге 1):
   - Добавь колонку `owner_id`:
     ```sql
     ALTER TABLE <table_name> ADD COLUMN owner_id INTEGER REFERENCES auth_users(id);
     CREATE INDEX IF NOT EXISTS ix_<table_name>_owner_id ON <table_name> (owner_id);
     ```
   - Заполни `owner_id` значением автора для всех существующих записей:
     ```sql
     UPDATE <table_name> SET owner_id = creator_id WHERE owner_id IS NULL;
     ```

### ШАГ 4. Адаптация прикладного кода (Python)
1. Проверь код хендлеров и бизнес-логики:
   - Если где-то происходила передача записи другому пользователю через изменение `item.creator_id = new_user_id`, замени это на `item.owner_id = new_user_id` (поле `creator_id` трогать больше нельзя).
   - Если в коде были прямые проверки `perm.row_level_only`, замени их на гранулярные `perm.read_global`, `perm.update_global` или `perm.delete_global`.
2. Убедись, что все RPC-методы `@app.rpc` имеют docstring (первая строка — краткое описание действия для матрицы прав).

### ШАГ 5. Верификация
1. Запусти тесты проекта (`pytest`).
2. Запусти сервер приложения:
   - Проверь вход под администратором в `/crud`.
   - Открой матрицу прав ролей и убедись, что отображаются новые селекторы прав: `Запрещено` | `Только свои 👤` | `Все 🌐`.
   - Убедись в консоли, что нет предупреждений об отсутствующих колонках `owner_id` или таблице `auth_user_delegation`.
```
