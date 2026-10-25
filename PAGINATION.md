# ⚡ Табличная пагинация в PyFerro 2.0 (`paginate_tabular` + JS Paginator)

Система пагинации PyFerro 2.0 спроектирована по главному принципу фреймворка: **минимум кода для разработчика на бэкенде и фронтенде при максимальной скорости выполнения**.

---

## 🚀 1. Быстрый старт: Бэкенд за 1 строчку

Вам больше не нужно вручную считать `count(*)`, высчитывать `offset` и форматировать словари.

### Вариант А: Передача модели (Zero-SQL)
```python
from pyferro2.db import paginate_tabular
from pyferro2.rpc import rpc_method
from sqlalchemy.ext.asyncio import AsyncSession


class Book(RowSecureModel):
    __tablename__ = "books"
    title: Mapped[str]
    author: Mapped[str]
    genre: Mapped[str]
    price: Mapped[int]

    @rpc_method
    async def list(db: AsyncSession, **params) -> dict:
        """Метод Book.list с авто-поиском, авто-фильтрами и пагинацией."""
        return await paginate_tabular(db, Book, **params)
```

### Вариант Б: Кастомный `select(...)`
Если нужна кастомная бизнес-логика (например, `where`, `join`):
```python
@rpc_method
async def my_catalog(db: AsyncSession, **params) -> dict:
    query = select(Book).where(Book.price > 0)
    return await paginate_tabular(db, query, **params)
```

---

## 🧰 2. Возможности бэкенда (`paginate_tabular`)

### Сигнатура функции:
```python
await paginate_tabular(
    db: AsyncSession,
    target: type[Base] | Select,
    *,
    page: int | None = 1,          # Номер страницы (1-indexed)
    limit: int = 20,               # Строк на страницу
    cursor: str | None = None,     # Курсор для Keyset-пагинации
    search: str | None = None,     # Поисковая подстрока (ILIKE)
    search_fields: list[str] = None, # Поля для поиска (по дефолту — все строковые)
    filters: dict = None,          # Фильтры точного совпадения {"genre": "fiction"}
    sort_by: str = None,           # Поле для сортировки
    order: str = "desc",           # "asc" или "desc"
    fields: list[str] = None,      # Желаемые колонки для вывода
    count: bool = True,            # Вычислять ли точный total
    max_limit: int = 500,          # Защитный лимит на размер страницы
    **extra_params,                # Игнорирует лишние параметры RPC
)
```

### 1. Два режима пагинации «под капотом»:
- **Offset (по страницам):** если передан `page=1`. Сам делает `SELECT count(*)` (автоматически удаляя `ORDER BY` из подзапроса подсчета, чтобы база не тратила время на сортировку) и `OFFSET / LIMIT`.
- **Keyset / Cursor ($O(1)$ без `count`):** если передан `cursor="..."`. Мгновенно фильтрует по индексу `WHERE id < :cursor LIMIT 21`. Идеально для бесконечного скролла на миллионах строк.
- **Гибрид:** в режиме `page` хелпер **также генерирует `next_cursor`**, позволяя клиенту бесшовно переключиться на курсорную навигацию.

### 2. Авто-трансляция фильтров и поиска в SQL:
Хелпер сам проверяет наличие колонок у модели и защищает от SQL-инъекций:
- `search="Гарри"` $\to$ автоматически добавляет `WHERE (title ILIKE '%Гарри%' OR author ILIKE '%Гарри%')`.
- `filters={"genre": "fantasy", "price": [100, 200]}` $\to$ транслирует в `WHERE genre = 'fantasy' AND price IN (100, 200)`.

### 3. Оптимизация Zero-Hydration:
Для формирования пакета `$tabular` не создаются тяжелые ORM-инстансы `Book` и не тратятся ресурсы Unit-of-Work. Даты (`datetime`), UUID, Decimal и Enum автоматически приводятся к JSON-типам.

---

## 🎨 3. Быстрый старт: Фронтенд (JS / Svelte)

На клиенте вам доступны контроллер [`createPaginator`](file:///c:/Users/user/Hobby/PyFerro/PyFerro2/frontend/src/rpc.js) и готовый визуальный компонент [`Pagination.svelte`](file:///c:/Users/user/Hobby/PyFerro/PyFerro2/frontend/src/Pagination.svelte).

### Пример таблицы в Svelte-компоненте:
```svelte
<script>
  import { onMount } from "svelte";
  import { createPaginator } from "./rpc.js";
  import Pagination from "./Pagination.svelte";

  // 1. Создаем контроллер метода RPC
  const books = createPaginator("Book.list", { limit: 20 });

  onMount(() => {
    books.load();
  });
</script>

<div class="card">
  <!-- Живой поиск с автоматическим debounce -->
  <input
    placeholder="Поиск по книгам..."
    value={books.searchQuery}
    oninput={(e) => books.search(e.target.value)}
  />

  {#if books.loading}
    <p>Загрузка данных...</p>
  {:else if books.error}
    <p class="error">{books.error}</p>
  {:else}
    <table>
      <thead>
        <tr>
          <th>ID</th>
          <th>Название</th>
          <th>Автор</th>
          <th>Цена</th>
        </tr>
      </thead>
      <tbody>
        {#each books.items as book}
          <tr>
            <td>{book.id}</td>
            <td>{book.title}</td>
            <td>{book.author}</td>
            <td>{book.price} ₽</td>
          </tr>
        {/each}
      </tbody>
    </table>

    <!-- 2. Готовая панель со всеми номерами страниц, стрелками и счетчиком -->
    <Pagination paginator={books} />
  {/if}
</div>
```

---

## 🛠️ 4. Методы и свойства `createPaginator`

| Метод / Свойство | Тип | Описание |
| :--- | :--- | :--- |
| `items` | `Array` | Распакованные строки текущей страницы |
| `page` | `number` | Текущий номер страницы (начиная с 1) |
| `pages` | `number` | Общее количество страниц |
| `total` | `number` | Всего записей в базе данных |
| `limit` | `number` | Количество записей на странице |
| `loading` | `boolean` | Флаг выполнения запроса |
| `hasNext` / `hasPrev` | `boolean` | Доступность следующей / предыдущей страницы |
| `pageNumbers` | `Array` | Массив страниц для рендера, например `[1, '...', 4, 5, 6, '...', 25]` |
| `load()` | `async function` | Загрузить текущую страницу |
| `next()` / `prev()` | `async function` | Переход вперед / назад |
| `goTo(page)` | `async function` | Переход на указанную страницу |
| `search(query, [ms=250])` | `function` | Поиск с авто-debounce и сбросом на 1-ю страницу |
| `setFilter(key, val)` | `async function` | Установка точного фильтра и перезагрузка |
| `setSorting(col, order)` | `async function` | Установка сортировки (`"asc"` / `"desc"`) |
| `setLimit(limit)` | `async function` | Изменение лимита (10, 20, 50, 100) и перезагрузка |
| `refresh()` | `async function` | Повторить запрос текущей страницы |

---

## 📦 5. Сетевой формат `$tabular`

По проводу WebSocket/HTTP передается сверхкомпактная структура:
```json
{
  "$tabular": true,
  "fields": ["id", "title", "author", "price"],
  "rows": [
    [101, "Чистая архитектура", "Р. Мартин", 1200],
    [102, "Совершенный код", "С. Макконнелл", 1500]
  ],
  "page": 1,
  "limit": 20,
  "total": 142,
  "pages": 8,
  "has_next": true,
  "has_prev": false,
  "next_cursor": "eyJ2IjoxMDIsImMiOiJpZCIsImQiOiJkZXNjIn0="
}
```

Клиентский `unpackTabular()` автоматически восстанавливает массив объектов `items` в JavaScript, экономя до 70% трафика и разгружая процессор.
