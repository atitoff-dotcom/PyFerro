# -*- coding: utf-8 -*-
"""Исключения подсистемы миграций PyFerro."""


class MigrationError(Exception):
    """Базовое исключение подсистемы миграций PyFerro."""
    pass


class LegacyDatabaseError(MigrationError):
    """Исключение при обнаружении базы данных устаревшей структуры (pre-v0.7.0)."""
    pass


class MigrationVerificationError(MigrationError):
    """Исключение при сбое предварительной проверки (pre_check) миграции."""
    pass