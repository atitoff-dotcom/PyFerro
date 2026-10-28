# 🎨 PyFerro GUI & Design System Guidelines

Документ фиксирует правила верстки, цветовую модель и требования доступности (A11y) для всех компонентов интерфейса PyFerro.  
**Правила обязательны для соблюдения разработчиками и AI-агентами.**

---

## 🏛️ 5 Ключевых Правил Архитектуры GUI

### 1. Zero Hardcoded Colors (Только токены системы)
* ❌ **Категорически запрещено:**
  * Использовать дефолтные палитры Tailwind (`bg-gray-800`, `text-zinc-900`, `border-neutral-700`, `text-white`, `text-black`).
  * Прописывать прямые значения цветов в стилях или инлайн-классах (`bg-[#1a1a1a]`, `text-[#ffffff]`, `style="color: black"`).
* ✅ **Обязательно:**
  * Использовать только зарегистрированные семантические токены (`bg-bg`, `bg-panel`, `bg-panel-alt`, `border-border`, `border-border-subtle`, `text-text`, `text-text-bright`, `text-muted`, `bg-accent`, `bg-danger`, `bg-success`).
  * Для низкоуровневых градиентов или шкал допускаются прямые токены ступеней (`bg-step-0` ... `bg-step-15`).

---

### 2. Theme Invariant (Запрет утилиты `dark:`)
* ❌ **Категорически запрещено:**
  * Дублировать классы через префикс `dark:` в разметке:
    ```html
    <!-- ТАК ДЕЛАТЬ НЕЛЬЗЯ -->
    <div class="bg-white dark:bg-zinc-900 text-black dark:text-white border-gray-200 dark:border-gray-800">
    ```
* ✅ **Обязательно:**
  * Разметка пишется **один раз** с использованием семантических токенов:
    ```html
    <!-- ПРАВИЛЬНО -->
    <div class="bg-panel text-text border-border-subtle">
    ```
  * Тема (`dark` или `light`) переключается исключительно на уровне корневого контейнера через селектор `[data-theme="dark|light"]`. Значения CSS-переменных адаптируются автоматически.

---

### 3. Фотометрическая эргономика (Защита зрения)
* 🌑 **Dark Mode (JetBrains Darcula Cosine Model):**
  * **Запрещен чистый белый текст `#FFFFFF` (100% яркости).** Интенсивный белый на темном фоне вызывает спазм аккомодации и паразитный ореол свечения (эффект иррадиации / halo effect).
  * Основной текст ограничен токеном `text-text` (`#CFD1D4` / ~82% L), заголовки и акценты — токеном `text-text-bright` (`#E2E3E5` / ~89% L).
* ☀️ **Light Mode (Warm Stone Model):**
  * **Запрещен чистый черный текст `#000000` (0% яркости).** Текст ограничен токеном `text-text` (`#2E2F30`) или `text-text-bright` (`#1B1C1D`).
  * Фон базового холста (`bg-bg`) — теплый мягкий камень `step-0` (`#FAFAFA`), исключающий холодный «ослепляющий» мониторный белый.

---

### 4. Закон эшелонирования слоев (Elevation Law)
Глубина интерфейса формируется строго по ступеням 16-шаговой S-кривой от дальнего плана к ближнему. Запрещено перескакивать через слои (например, класть всплывающий элемент сразу на холст без промежуточного слоя).

| Уровень глубины | Роль элемента | S-Ступень | Семантический класс |
|---|---|---|---|
| **Слой 0 (Canvas)** | Фоновая подложка окна, главный вьюпорт | `step-0` | `bg-bg` |
| **Слой 1 (Structural)** | Сайдбары, тулбары, шапки, статус-бары | `step-1` | `bg-panel` |
| **Слой 2 (Surface / Card)** | Карточки, блоки таблиц, списки элементов | `step-2` | `bg-panel-alt` |
| **Слой 3 (Interactive)** | Ховер-состояния панелей и строк таблиц | `step-4` | `hover:bg-panel-hover` |
| **Слой 4 (Overlays / Modals)** | Выпадающие меню, поповеры, модальные окна | `step-3` / `step-4` | `bg-panel-alt shadow-md` |

*Взаимодействие:* Ховер и активные состояния задаются семантическими модификаторами относительно слоя элемента (`hover:bg-panel-hover`, `hover:bg-accent-hover`, `active:scale-[0.98]`).

---

### 5. Эргономика Fitts & A11y (Доступность и сенсорика)
* **Минимальный размер клика (Fitts's Law):**
  * Высота любого кликабельного контрола (кнопки, инпуты, селекты, вкладки, элементы меню) — **не менее 32px** (`min-h-8` или `h-8`).
* **4 обязательных интерактивных состояния:**
  Каждый контрол обязан явно описывать 4 фазы жизни:
  1. `default`: базовый стиль (например, `bg-accent text-accent-fg`);
  2. `hover`: реакция на курсор (`hover:bg-accent-hover`);
  3. `active`: подтверждение нажатия (`active:opacity-90 active:scale-[0.99]`);
  4. `disabled`: неактивное состояние (`disabled:opacity-50 disabled:pointer-events-none disabled:cursor-not-allowed`).
* **Клавиатурная навигация:**
  * Сохранение четкого, различимого фокуса: `focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent`.

---

## 📋 Таблица Токенов (Source of Truth: `frontend/src/app.css`)

### 1. Поверхности и фоны
| Семантический токен | Класс Tailwind | Назначение |
|---|---|---|
| `--bg` | `bg-bg` | Базовый холст приложения |
| `--panel` | `bg-panel` | Сайдбары, заголовки секций |
| `--panel-alt` | `bg-panel-alt` | Карточки, списки, контейнеры |
| `--panel-hover` | `hover:bg-panel-hover` | Ховер строк, карточек и кнопок |

### 2. Границы и разделители
| Семантический токен | Класс Tailwind | Назначение |
|---|---|---|
| `--border` | `border-border` | Контрастные границы, разделители панелей |
| `--border-subtle` | `border-border-subtle` | Тонкие границы карточек, ячеек таблиц |

### 3. Типографика
| Семантический токен | Класс Tailwind | Назначение |
|---|---|---|
| `--text` | `text-text` | Основной текст интерфейса |
| `--text-bright` | `text-text-bright` | Заголовки, акцентированный текст |
| `--muted` | `text-muted` | Подписи, плейсхолдеры, вторичный текст |
| `--muted-light` | `text-muted-light` | Деактивированный текст, иконки |

### 4. Статусы и Акценты
| Семантический токен | Фоновый класс | Текстовый класс | Назначение |
|---|---|---|---|
| `--accent` | `bg-accent` (`hover:bg-accent-hover`) | `text-accent` | Главный акцент (Sapphire/Darcula blue) |
| `--accent-fg` | - | `text-accent-fg` | Текст поверх заливки акцента (#FFF) |
| `--accent-subtle` | `bg-accent-subtle` | - | Полупрозрачная подложка бейджей |
| `--danger` | `bg-danger` (`hover:bg-danger-hover`) | `text-danger` | Ошибки, деструктивные действия |
| `--success` | `bg-success` | `text-success` | Успех, статус «online», сохранено |
| `--warning` | `bg-warning` | `text-warning` | Предупреждения, внимание |

---

## 🛠️ Примеры (Do's and Don'ts)

### Кнопка действия (Action Button)

❌ **Плохо (хардкод, префиксы dark, мелкий размер):**
```html
<button class="bg-blue-600 dark:bg-blue-500 hover:bg-blue-700 text-white px-2 py-1 text-xs">
  Сохранить
</button>
```

✅ **Хорошо (семантические токены, 32px min-height, все 4 состояния, A11y):**
```html
<button class="min-h-8 px-3 py-1.5 rounded text-sm font-medium bg-accent text-accent-fg hover:bg-accent-hover active:opacity-90 disabled:opacity-50 disabled:pointer-events-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent transition-colors">
  Сохранить
</button>
```

---

### Карточка контента (Content Card)

❌ **Плохо:**
```html
<div class="bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 p-4">
  <h3 class="text-black dark:text-white font-bold">Заголовок</h3>
  <p class="text-gray-500">Описание</p>
</div>
```

✅ **Хорошо:**
```html
<div class="bg-panel-alt border border-border-subtle rounded-md p-4">
  <h3 class="text-text-bright font-semibold">Заголовок</h3>
  <p class="text-muted text-sm">Описание</p>
</div>
```

---

### Строка таблицы / Списка с ховером

✅ **Хорошо:**
```html
<div class="min-h-8 flex items-center px-3 py-1.5 border-b border-border-subtle hover:bg-panel-hover transition-colors text-text">
  <span>Элемент списка</span>
</div>
```
