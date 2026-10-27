# CRUD Engine и спецификации моделей

Движок CRUD в PyFerro позволяет автоматически генерировать формы, валидаторы и списки для любых моделей SQLAlchemy.

## Определение модели

Модели данных наследуются от `RowSecureModel` и объявляют внутренний класс `Crud`:

```python
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Integer
from pyferro2.core.session_data import SessionData

class Article(RowSecureModel):
    __tablename__ = "articles"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    author_id: Mapped[int] = mapped_column(Integer)
    
    class Crud:
        readable_fields = ["id", "title", "author_id"]
        writable_fields = ["title"]
```

## Интерактивный пример

Попробуйте интерактивную демонстрацию пагинации для набора из 500 записей:

```widget:PaginationDemo
total: 500
pageSize: 25
currentPage: 1
```

## Автоматическая валидация

При отправке изменений движок проверяет типы данных, ограничения длины строк и права пользователя на редактирование строк (`readable_fields`, `writable_fields`).
