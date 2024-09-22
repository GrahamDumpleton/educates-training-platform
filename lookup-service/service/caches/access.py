"""Configuration for remote access config."""

from dataclasses import dataclass
from typing import List


@dataclass
class AccessConfig:
    """Configuration object for remote access config."""

    name: str
    allowed_origins: List[str]
