"""
Модуль форума: модели, RPC и генераторы SEO.
"""

from pyferro_demo.forum.models import ForumBase, Topic, Message
from pyferro_demo.forum.rpc import register_forum_rpc
from pyferro_demo.forum.seeder import seed_forum_data

__all__ = [
    "ForumBase",
    "Topic",
    "Message",
    "register_forum_rpc",
    "seed_forum_data",
]
