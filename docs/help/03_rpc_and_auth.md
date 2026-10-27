# RPC-маршрутизация и права доступа

Каждый метод API регистрируется через декоратор роутера с указанием необходимых системных ролей.

## Регистрация метода

```python
from pyferro2.core.constants import admRole
from pyferro2.core.session_data import SessionData

# доступно в соответствии с CRUD в админке
@router.rpc_method()
async def get_system_status_all(session: SessionData) -> dict:
    return {"status": "ok", "user": session.username}

# доступно только ролям admin и adm_help, CRUD в админке уже не работает
@router.rpc_method(role=[admRole.adm_help])
async def get_system_status(session: SessionData) -> dict:
    return {"status": "ok", "user": session.username}

# доступно только ролям admin, CRUD в админке уже не работает
@router.rpc_method(role=[admRole.admin])
async def get_system_status_admin(session: SessionData) -> dict:
    return {"status": "ok", "user": session.username}
```

## Системные роли `adm_*`

* `admin` — суперпользователь, имеет доступ ко всем методам и разделам.
* `adm_help` — доступ к разделу «Руководство для разработчиков» (`/pyferro_admin/help`).
* `adm_crud` — доступ к просмотру и редактированию таблиц.
* `adm_roles` — управление матрицей прав и ролей.
* `adm_users` — управление учетными записями.
* `adm_seo` — управление SEO-правилами и sitemap.
