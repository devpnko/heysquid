"""heysquid.skills._base — abstract skill interface."""

from abc import ABC, abstractmethod


class Skill(ABC):
    """Base class for heysquid skills (workflow units)."""

    @abstractmethod
    def execute(self, **kwargs):
        ...
