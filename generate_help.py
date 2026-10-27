#!/usr/bin/env python3
"""
generate_help.py — Автономный генератор справочной документации PyFerro.

Компилирует файлы Markdown из docs/help/ в предскомпилированный JSON-бандл (help/help_data.json)
вместе с поисковым индексом (по статьям, подразделам, тексту и коду).
Используется только на этапе сборки/разработки (build-time).
Не входит в рантайм PyPI, что исключает тяжелые зависимости (markdown-it-py, pygments) из дистрибутива.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any

try:
    from markdown_it import MarkdownIt
    from pygments import highlight
    from pygments.formatters import HtmlFormatter
    from pygments.lexers import TextLexer, get_lexer_by_name
except ImportError as err:
    print(
        f"❌ Ошибка импорта: {err}\n"
        "Для работы генератора справки требуются markdown-it-py и pygments:\n"
        "  pip install markdown-it-py pygments",
        file=sys.stderr,
    )
    sys.exit(1)


_FILENAME_RE = re.compile(r"^(?:(\d+)[_-])?(.+?)\.md$", re.IGNORECASE)


def _file_to_slug_and_order(filename: str) -> tuple[str, int]:
    """Извлекает числовой порядок и slug из имени файла (например, 01_getting_started.md)."""
    match = _FILENAME_RE.match(filename)
    if not match:
        clean = filename.removesuffix(".md")
        return clean.replace("_", "-").lower(), 999

    order_str, base_name = match.groups()
    order = int(order_str) if order_str is not None else 999
    slug = base_name.replace("_", "-").lower()
    return slug, order


def _highlight_code(code: str, lang: str, _attrs: Any) -> str:
    """Подсветка синтаксиса через Pygments с безопасным фолбэком на plain text."""
    try:
        lexer = get_lexer_by_name(lang) if lang else TextLexer()
    except Exception:
        lexer = TextLexer()
    formatter = HtmlFormatter(nowrap=True, cssclass="highlight")
    return highlight(code, lexer, formatter)


def _parse_widget_props(raw_content: str) -> dict[str, Any]:
    """Парсит свойства виджета из JSON или простого YAML-подобного key: value."""
    text = raw_content.strip()
    if not text:
        return {}

    if text.startswith("{"):
        try:
            return json.loads(text)
        except Exception:
            pass

    props: dict[str, Any] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, val = line.split(":", 1)
            key = key.strip()
            val = val.strip()

            if val.lower() == "true":
                props[key] = True
            elif val.lower() == "false":
                props[key] = False
            elif val.isdigit():
                props[key] = int(val)
            else:
                try:
                    props[key] = float(val)
                except ValueError:
                    if (val.startswith('"') and val.endswith('"')) or (
                        val.startswith("'") and val.endswith("'")
                    ):
                        val = val[1:-1]
                    props[key] = val
    return props


def _slugify(text: str) -> str:
    """Превращает заголовок в чистый HTML id anchor."""
    s = text.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    return s.strip("-")


class HelpDocParser:
    """Парсер Markdown-документов с поддержкой встроенных интерактивных виджетов."""

    def __init__(self) -> None:
        self.md = MarkdownIt("commonmark", {"highlight": _highlight_code})

    def parse(self, markdown_text: str, default_title: str = "Документация") -> dict[str, Any]:
        """
        Компилирует markdown_text в структуру:
        {
            "title": str,
            "toc": [{"id": str, "text": str, "level": int}, ...],
            "blocks": [
                {"type": "html", "html": "..."},
                {"type": "widget", "widget": "PaginationDemo", "props": {...}},
                ...
            ]
        }
        """
        tokens = self.md.parse(markdown_text)
        blocks: list[dict[str, Any]] = []
        current_tokens: list[Any] = []
        title: str | None = None
        toc: list[dict[str, Any]] = []

        for idx, token in enumerate(tokens):
            if token.type == "heading_open":
                level = int(token.tag[1:])
                if idx + 1 < len(tokens) and tokens[idx + 1].type == "inline":
                    heading_text = tokens[idx + 1].content.strip()
                    if level == 1 and title is None:
                        title = heading_text
                    h_id = _slugify(heading_text) or f"section-{len(toc) + 1}"
                    token.attrSet("id", h_id)
                    toc.append({"id": h_id, "text": heading_text, "level": level})

            if token.type == "fence" and token.info.startswith("widget:"):
                # Сбрасываем накопленные токены в HTML блок
                if current_tokens:
                    html_chunk = self.md.renderer.render(current_tokens, self.md.options, {})
                    if html_chunk.strip():
                        blocks.append({"type": "html", "html": html_chunk})
                    current_tokens = []

                widget_name = token.info.split(":", 1)[1].strip()
                widget_props = _parse_widget_props(token.content)
                blocks.append({
                    "type": "widget",
                    "widget": widget_name,
                    "props": widget_props,
                })
            else:
                current_tokens.append(token)

        if current_tokens:
            html_chunk = self.md.renderer.render(current_tokens, self.md.options, {})
            if html_chunk.strip():
                blocks.append({"type": "html", "html": html_chunk})

        return {
            "title": title or default_title,
            "toc": toc,
            "blocks": blocks,
        }

    def extract_search_sections(
        self, markdown_text: str, slug: str, article_title: str
    ) -> list[dict[str, Any]]:
        """
        Извлекает структурированные поисковые записи для полнотекстового поиска
        по заголовкам, тексту параграфов и блокам кода.
        """
        tokens = self.md.parse(markdown_text)
        sections: list[dict[str, Any]] = []

        curr_title = article_title
        curr_id = ""
        curr_texts: list[str] = []
        curr_codes: list[str] = []

        def flush_section() -> None:
            nonlocal curr_texts, curr_codes
            clean_text = " ".join(curr_texts).strip()
            clean_code = "\n".join(curr_codes).strip()
            if clean_text or clean_code or curr_id:
                sections.append({
                    "slug": slug,
                    "article_title": article_title,
                    "section_title": curr_title,
                    "section_id": curr_id,
                    "text": clean_text,
                    "code": clean_code,
                })
            curr_texts = []
            curr_codes = []

        for idx, token in enumerate(tokens):
            if token.type == "heading_open":
                flush_section()
                heading_text = ""
                if idx + 1 < len(tokens) and tokens[idx + 1].type == "inline":
                    heading_text = tokens[idx + 1].content.strip()
                curr_title = heading_text or article_title
                curr_id = _slugify(heading_text) if heading_text else ""
            elif token.type == "fence":
                if not token.info.startswith("widget:"):
                    code_body = token.content.strip()
                    if code_body:
                        curr_codes.append(code_body)
            elif token.type == "inline":
                content = token.content.strip()
                if content:
                    curr_texts.append(content)
                if token.children:
                    for child in token.children:
                        if child.type == "code_inline" and child.content.strip():
                            curr_codes.append(child.content.strip())

        flush_section()
        return sections


_DEFAULT_PARSER = HelpDocParser()


def parse_markdown_doc(text: str, default_title: str = "Документация") -> dict[str, Any]:
    return _DEFAULT_PARSER.parse(text, default_title=default_title)


def build_help_bundle(
    docs_dir: Path | str = "docs/help",
    output_file: Path | str | None = None,
) -> dict[str, Any]:
    """
    Сканирует docs_dir, парсит все *.md файлы и генерирует единый JSON-бандл с поисковым индексом.
    """
    base_dir = Path(docs_dir).resolve()
    tree: list[dict[str, Any]] = []
    articles: dict[str, dict[str, Any]] = {}
    search_index: list[dict[str, Any]] = []

    if base_dir.is_dir():
        parser = HelpDocParser()
        md_files = sorted(base_dir.glob("*.md"))

        for path in md_files:
            slug, order = _file_to_slug_and_order(path.name)
            fallback_title = slug.replace("-", " ").title()
            content = path.read_text(encoding="utf-8")
            parsed = parser.parse(content, default_title=fallback_title)

            article_title = parsed["title"]
            tree.append({
                "slug": slug,
                "title": article_title,
                "order": order,
                "filename": path.name,
            })
            articles[slug] = {
                "slug": slug,
                "title": article_title,
                "order": order,
                "toc": parsed["toc"],
                "blocks": parsed["blocks"],
            }

            # Извлечение записей для встроенного поиска
            sections = parser.extract_search_sections(content, slug, article_title)
            search_index.extend(sections)

    tree.sort(key=lambda item: (item["order"], item["slug"]))

    bundle = {
        "version": 1,
        "tree": tree,
        "articles": articles,
        "search_index": search_index,
    }

    if output_file is not None:
        out_path = Path(output_file).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")

    return bundle


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Компиляция документации Markdown в статичный JSON-бандл PyFerro Help System."
    )
    parser.add_argument(
        "--docs-dir",
        type=str,
        default="docs/help",
        help="Путь к папке со статьями Markdown (по умолчанию: docs/help)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="src/pyferro2/help/help_data.json",
        help="Путь к итоговому файлу JSON (по умолчанию: src/pyferro2/help/help_data.json)",
    )
    parser.add_argument(
        "--frontend-dist",
        action="store_true",
        help="Также скопировать скомпилированный help.json в frontend/dist/help.json, если папка dist существует",
    )
    args = parser.parse_args()

    docs_path = Path(args.docs_dir)
    out_path = Path(args.output)

    print(f"📚 Сборка документации из '{docs_path}' -> '{out_path}'...")
    bundle = build_help_bundle(docs_path, output_file=out_path)
    count = len(bundle["tree"])
    search_count = len(bundle["search_index"])
    print(f"  ✓ Скомпилировано статей: {count}, поисковых записей: {search_count}")

    if args.frontend_dist:
        dist_dir = Path("frontend/dist")
        if dist_dir.is_dir():
            dist_file = dist_dir / "help.json"
            dist_file.write_text(
                json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"  ✓ Скопировано в frontend dist: '{dist_file}'")


if __name__ == "__main__":
    main()
