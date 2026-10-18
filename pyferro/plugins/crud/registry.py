# -*- coding: utf-8 -*-
"""
Реестр метаданных моделей для CRUD-плагина PyFerro.
"""

from __future__ import annotations
from typing import Dict, Optional, Type, Set, Any
from .meta import ModelMeta, build_model_meta


# Служебные таблицы, исключаемые из админки по умолчанию
DEFAULT_SYSTEM_BLACKLIST: Set[str] = {
    "CacheTagVersion",
    "RefreshToken",
    "ActiveSession",
    "OAuthAccount",
}


class ModelRegistry:
    """
    Реестр метаданных моделей CRUD.
    Собирает ModelMeta один раз на этапе инициализации приложения.
    """
    _models: Dict[str, ModelMeta] = {}
    _expose_all: bool = True
    _blacklist: Set[str] = set(DEFAULT_SYSTEM_BLACKLIST)

    @classmethod
    def configure(cls, expose_all: bool = True, blacklist: Optional[Set[str]] = None) -> None:
        cls._expose_all = expose_all
        if blacklist is not None:
            cls._blacklist = set(blacklist)

    @classmethod
    def register(cls, model_class: Type[Any]) -> ModelMeta:
        """Регистрирует отдельную модель в реестре."""
        meta = build_model_meta(model_class)
        cls._models[meta.key] = meta
        return meta

    @classmethod
    def get(cls, model_name: str) -> Optional[ModelMeta]:
        """Возвращает метаданные модели по имени ключа или имени таблицы."""
        meta = cls._models.get(model_name)
        if meta:
            return meta
        # Поиск по имени таблицы или историческому имени без системного префикса
        for m in cls._models.values():
            if m.table_name == model_name:
                return m
            # Если запрос без префикса pf_ (например, auth_role -> pf_auth_role)
            if m.table_name.startswith("pf_") and m.table_name[3:] == model_name:
                return m
            # Если запрос с префиксом pf_, а таблица без него (или наоборот)
            if model_name.startswith("pf_") and m.table_name == model_name[3:]:
                return m
        return None

    @classmethod
    def all(cls) -> Dict[str, ModelMeta]:
        """Возвращает все зарегистрированные модели."""
        return cls._models

    @classmethod
    def register_auth_models(cls) -> None:
        """Регистрирует стандартные модели безопасности (User, Role, RpcPermission, UserDelegation) в CRUD."""
        try:
            from pyferro.auth import User, Role, RpcPermission, UserDelegation
            cls.register(User)
            cls.register(Role)
            cls.register(RpcPermission)
            cls.register(UserDelegation)
        except Exception:
            pass

    @classmethod
    def auto_discover(cls, base_cls: Type[Any]) -> None:
        """
        Автоматически находит все mapped-модели в DeclarativeBase SQLAlchemy
        и строит для них ModelMeta.
        """
        registry = getattr(base_cls, "registry", None)
        if not registry:
            return

        for mapper in registry.mappers:
            m_cls = mapper.class_
            name = m_cls.__name__

            if name in cls._blacklist:
                continue

            # Если включен строгий opt-in (expose_all == False), публикуем только с class Crud
            if not cls._expose_all and not hasattr(m_cls, "Crud"):
                continue

            cls.register(m_cls)

    @classmethod
    def clear(cls) -> None:
        """Сброс реестра (для тестов)."""
        cls._models.clear()
