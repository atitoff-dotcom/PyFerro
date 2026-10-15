# -*- coding: utf-8 -*-
"""
Declarative models for the Showcase demonstration application.
Uses official framework database module: pyferro.db.Base
and declarative mapping for pyferro.plugins.crud (class Crud:).
"""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from pyferro.db import Base
from pyferro.auth import RowSecureModel


class Task(RowSecureModel):
    __tablename__ = "showcase_tasks"

    title = Column(String(255), nullable=False)
    completed = Column(Boolean, default=False, nullable=False)
    priority = Column(String(20), default="normal", nullable=False)
    # id, creator_id, owner_id, team_id, created_at, updated_at inherit from RowSecureModel!

    class Crud:
        verbose_name = "Task"
        verbose_name_plural = "Tasks"
        readonly = {"created_at", "updated_at", "creator_id"}
        protected = {"creator_id"}

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "completed": self.completed,
            "priority": self.priority,
            "creator_id": self.creator_id,
            "owner_id": self.owner_id,
            "team_id": self.team_id,
            "created_at": self.created_at.strftime("%H:%M:%S") if self.created_at else "",
        }


class Document(Base):
    __tablename__ = "showcase_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    category = Column(String(50), default="general", nullable=False)
    views = Column(Integer, default=0, nullable=False)
    content = Column(Text, default="", nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    class Crud:
        verbose_name = "Document"
        verbose_name_plural = "Documents"
        readonly = {"updated_at"}

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "views": self.views,
            "content": self.content,
            "updated_at": self.updated_at.strftime("%H:%M:%S") if self.updated_at else "",
        }
