"""
Тесты справочной системы PyFerro Help System (Docs-as-Code с живыми виджетами).
"""

from pathlib import Path
import pytest

from generate_help import HelpDocParser, build_help_bundle, parse_markdown_doc
from pyferro2.core.constants import admRole
from pyferro2.core.session import Session
from pyferro2.core.session_data import SessionData
from pyferro2.help.rpc import register_help_rpc
from pyferro2.rpc.errors import ForbiddenError, RpcError, UnauthorizedError
from pyferro2.rpc.router import RpcRouter


class TestHelpDocParser:
    def test_parse_markdown_with_widgets_and_code(self):
        md_text = """# Заголовок Руководства

Текст первого параграфа с **жирным** шрифтом.

```python
x = 42
print(x)
```

## Раздел с виджетом

```widget:PaginationDemo
total: 300
pageSize: 15
isLive: true
```

Заключение статьи.
"""
        doc = parse_markdown_doc(md_text)

        assert doc["title"] == "Заголовок Руководства"
        assert len(doc["toc"]) == 2
        assert doc["toc"][0]["text"] == "Заголовок Руководства"
        assert doc["toc"][1]["text"] == "Раздел с виджетом"

        blocks = doc["blocks"]
        assert len(blocks) == 3

        # Первый блок - HTML с текстом и подсвеченным кодом
        assert blocks[0]["type"] == "html"
        assert "language-python" in blocks[0]["html"]
        assert "x" in blocks[0]["html"]

        # Второй блок - виджет
        assert blocks[1]["type"] == "widget"
        assert blocks[1]["widget"] == "PaginationDemo"
        assert blocks[1]["props"]["total"] == 300
        assert blocks[1]["props"]["pageSize"] == 15
        assert blocks[1]["props"]["isLive"] is True

        # Третий блок - заключительный HTML
        assert blocks[2]["type"] == "html"
        assert "Заключение статьи" in blocks[2]["html"]

    def test_json_props_in_widget(self):
        md_text = """# Статья
```widget:CustomChart
{"points": [1, 2, 3], "animate": false}
```
"""
        doc = parse_markdown_doc(md_text)
        assert len(doc["blocks"]) == 2
        assert doc["blocks"][0]["type"] == "html"
        assert doc["blocks"][1]["type"] == "widget"
        assert doc["blocks"][1]["widget"] == "CustomChart"
        assert doc["blocks"][1]["props"] == {"points": [1, 2, 3], "animate": False}


class TestHelpRpcIntegration:
    @pytest.fixture
    def router_and_docs(self, tmp_path: Path):
        docs_dir = tmp_path / "docs" / "help"
        docs_dir.mkdir(parents=True)

        (docs_dir / "01_intro.md").write_text("# Введение\nПервая статья с кодом `@router.rpc_method`.", encoding="utf-8")
        (docs_dir / "02_crud_guide.md").write_text(
            "# Руководство по CRUD\n\n```widget:DemoCrud\nmodel: Book\n```",
            encoding="utf-8",
        )
        (docs_dir / "10_advanced.md").write_text("# Продвинутый уровень\nФинал.", encoding="utf-8")

        bundle_path = tmp_path / "help_data.json"
        build_help_bundle(docs_dir=docs_dir, output_file=bundle_path)

        router = RpcRouter()
        register_help_rpc(router, help_source=bundle_path)
        return router

    @pytest.mark.asyncio
    async def test_get_tree_sorting_and_content(self, router_and_docs):
        router = router_and_docs
        admin_session = Session(
            session_id="s-admin",
            data=SessionData(
                user_id=1,
                username="admin",
                roles=frozenset([admRole.admin.value]),
                permissions=frozenset(),
            ),
        )

        tree = await router.call("help.get_tree", admin_session)
        assert len(tree) == 3
        assert tree[0]["slug"] == "intro"
        assert tree[0]["title"] == "Введение"
        assert tree[0]["order"] == 1

        assert tree[1]["slug"] == "crud-guide"
        assert tree[1]["title"] == "Руководство по CRUD"
        assert tree[1]["order"] == 2

        assert tree[2]["slug"] == "advanced"
        assert tree[2]["order"] == 10

    @pytest.mark.asyncio
    async def test_get_article_by_slug(self, router_and_docs):
        router = router_and_docs
        help_user_session = Session(
            session_id="s-help",
            data=SessionData(
                user_id=2,
                username="tech_writer",
                roles=frozenset([admRole.adm_help.value]),
                permissions=frozenset(),
            ),
        )

        article = await router.call("help.get_article", help_user_session, {"slug": "crud-guide"})
        assert article["slug"] == "crud-guide"
        assert article["title"] == "Руководство по CRUD"
        assert len(article["blocks"]) == 2
        assert article["blocks"][1]["type"] == "widget"
        assert article["blocks"][1]["widget"] == "DemoCrud"

    @pytest.mark.asyncio
    async def test_get_search_index(self, router_and_docs):
        router = router_and_docs
        admin_session = Session(
            session_id="s-admin",
            data=SessionData(
                user_id=1,
                username="admin",
                roles=frozenset([admRole.admin.value]),
                permissions=frozenset(),
            ),
        )

        search_index = await router.call("help.get_search_index", admin_session)
        assert len(search_index) >= 3
        intro_sec = next(s for s in search_index if s["slug"] == "intro")
        assert intro_sec["section_title"] == "Введение"
        assert "@router.rpc_method" in intro_sec["code"] or "@router.rpc_method" in intro_sec["text"]

    @pytest.mark.asyncio
    async def test_article_not_found_returns_error(self, router_and_docs):
        router = router_and_docs
        admin_session = Session(
            session_id="s-admin",
            data=SessionData(
                user_id=1,
                username="admin",
                roles=frozenset([admRole.admin.value]),
                permissions=frozenset(),
            ),
        )

        with pytest.raises(RpcError) as exc_info:
            await router.call("help.get_article", admin_session, {"slug": "unknown-article"})
        assert exc_info.value.code == 404

    @pytest.mark.asyncio
    async def test_permission_protection_denies_guest_and_plain_user(self, router_and_docs):
        router = router_and_docs
        guest_session = Session(session_id="s-guest")
        plain_user_session = Session(
            session_id="s-user",
            data=SessionData(
                user_id=10,
                username="bob",
                roles=frozenset(["user"]),
                permissions=frozenset(),
            ),
        )

        # Гость получает UnauthorizedError
        with pytest.raises((UnauthorizedError, ForbiddenError)):
            await router.call("help.get_tree", guest_session)

        # Обычный пользователь без adm_help получает ForbiddenError
        with pytest.raises(ForbiddenError):
            await router.call("help.get_tree", plain_user_session)
