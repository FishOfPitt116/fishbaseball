"""fishbaseball: baseball data for Python (Lahman now; Retrosheet and Statcast planned).

    import fishbaseball as fb

    fb.lahman.tables()                              # every table name
    fb.lahman.load("batting")                       # -> DataFrame, the whole table
    fb.lahman.batting(1927, player_id="ruthba01")    # -> Ruth's 1927 season

Every table has both `load("<table>")` and a dedicated function (`fb.lahman.people(...)`,
`fb.lahman.teams(...)`, ...) with filters for whichever of `seasons`/`player_id`/`team_id`/
`lg_id` that table actually has — see each function's own docstring, or `help(fb.lahman)`.

Also see:
    `fb.config` — global settings: backend, cache_dir, offline, strict, ttl.
    `fb.cache`  — inspect (`info`), clear (`purge`) or pre-warm (`prefetch`) the local cache.
    `fb.sources()` — a status view: what's cached, what's published, when last checked.

Data is mirrored, validated and published by github.com/FishOfPitt116/fishbaseball-data; see
that repo's README for the pipeline and full license text.
"""

from fishbaseball import cache, config, lahman
from fishbaseball._version import __version__
from fishbaseball.sources import sources

__all__ = ["__version__", "config", "cache", "lahman", "sources"]
