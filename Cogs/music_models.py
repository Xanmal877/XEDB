"""Music track and repeat-mode types."""

from dataclasses import dataclass
from enum import Enum

import discord


class RepeatMode(Enum):
    NONE = 0
    TRACK = 1
    QUEUE = 2


@dataclass
class Track:
    source: str
    title: str
    url: str
    requester: discord.Member

