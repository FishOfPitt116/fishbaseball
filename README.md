# fishbaseball

Baseball data for Python. `pip install fishbaseball` and get validated, versioned tables as
[Polars](https://pola.rs) (or pandas) DataFrames, cached locally and refreshed automatically.

Right now it ships the **Lahman Baseball Database**: 27 tables of batting, pitching, fielding,
teams, people, awards and more, 1871 to the latest season, including Negro Leagues data.
Retrosheet and Statcast are planned.

The data itself is mirrored, validated and published by a companion repo,
[`fishbaseball-data`](https://github.com/FishOfPitt116/fishbaseball-data) — see its README for
the pipeline, the release format, and the full table/column list. This package is the client:
it downloads, caches and verifies what that pipeline publishes.

## Quickstart

```python
import fishbaseball as fb

fb.lahman.tables()                              # every table name
fb.lahman.load("batting")                       # -> polars DataFrame, the whole table
fb.lahman.batting(1927, player_id="ruthba01")    # -> Ruth's 1927 season (60 HR)
```

Every table also has its own function (`fb.lahman.people(...)`, `fb.lahman.teams(...)`, ...),
each offering `seasons` and whichever of `player_id` / `team_id` / `lg_id` that table actually
has as columns. `load(table, ...)` is the general form and always works, including for a table
added upstream before a dedicated function exists for it.

```python
fb.lahman.pitching(2001, team_id="SFN")
fb.lahman.people(player_id=["ruthba01", "bondsba01"])
fb.lahman.hall_of_fame()
```

### Provenance

```python
df, prov = fb.lahman.load("batting", return_provenance=True)
prov.version        # the release tag actually served, e.g. "lahman-2026-09-28"
prov.from_cache      # True if this didn't hit the network
prov.attribution     # for citing the data
```

### Pinning a version

```python
fb.lahman.load("teams", version="2026-09-28")   # an exact release
fb.lahman.load("teams", version="2025")         # the newest release of SABR's "2025" version
fb.lahman.version()                             # the tag load() would currently use
fb.lahman.releases()                            # every known release, as a DataFrame
```

### Caching and offline use

Tables are downloaded once per release and cached under a per-OS user cache directory
(`platformdirs.user_cache_dir("fishbaseball")` unless overridden). Every call after the first
for a given table and release reads from disk; the release pointer itself is rechecked at most
once a week (configurable) unless you ask for a refresh.

```python
fb.cache.info()                 # what's cached, and how big
fb.cache.prefetch("lahman")     # download everything once, e.g. before going offline
fb.cache.purge()                # clear it (add source=/version= to be selective)

fb.lahman.load("batting", refresh=True)   # force a check for a newer release
fb.lahman.load("batting", offline=True)   # never touch the network; cache or raise
```

If a release can't be fetched or fails verification, fishbaseball falls back to the newest
still-good cached release and issues a `StaleDataWarning` rather than failing outright — set
`fb.config.set(strict=True)` to raise instead.

### Configuration

```python
fb.config.set(
    backend="pandas",   # or "polars" (default)
    cache_dir="...",    # override the default cache location
    offline=False,      # default for every call unless overridden per-call
    strict=False,       # raise instead of warning on a stale fallback
    ttl=7 * 24 * 3600,  # seconds before the release pointer is rechecked
)
```

### Status

```python
fb.sources()   # one row per source: what you have cached, what's published, when last checked
```

`sources()` only reads the local cache — it never makes a network call.

## How it stays correct

Every release fishbaseball reads has passed the `fishbaseball-data` pipeline's validation
(structural checks, referential integrity, stat logic, golden values against known career
totals) and is verified again here by SHA-256 on download and a column/dtype check against the
release's manifest before it's trusted. A `schema_version` on each release lets this package
refuse (or a future one support) upstream changes it doesn't yet understand, without ever
serving data it can't vouch for.

## Contributing

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[pandas]" -r requirements.txt
.venv/bin/pytest tests/unit          # fast, no network
.venv/bin/pytest tests/integration   # hits the live published release
.venv/bin/ruff check . && .venv/bin/pyright
```

## License

Code: MIT (see `LICENSE`). The Lahman data itself is CC BY-SA 3.0 (© SABR, via Sean Lahman);
`fb.lahman.load(..., return_provenance=True)` gives you the exact attribution string to cite,
and see [`fishbaseball-data`](https://github.com/FishOfPitt116/fishbaseball-data) for the full
license text and the Negro Leagues data's Seamheads.com attribution.
