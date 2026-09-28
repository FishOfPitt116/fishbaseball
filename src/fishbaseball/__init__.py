"""fishbaseball: baseball data for Python (Lahman now; Retrosheet and Statcast planned).

Built up incrementally: `lahman`, `cache` and `sources()` are exposed here as each lands.
"""

from fishbaseball import config
from fishbaseball._version import __version__

__all__ = ["__version__", "config"]
