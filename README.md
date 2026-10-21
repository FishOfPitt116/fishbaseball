# fishbaseball

Baseball data for Python. `pip install fishbaseball` and get validated, versioned tables as
[Polars](https://pola.rs) (or pandas) DataFrames, cached locally and refreshed automatically.

Right now it ships two sources:

- the **Lahman Baseball Database**: 27 tables of batting, pitching, fielding, teams, people,
  awards and more, 1871 to the latest season, including Negro Leagues data;
- **Retrosheet**: parsed play-by-play (every play since 1897, 17 million rows) with per-game
  batting, pitching, fielding and team box scores, 1897 to the latest season.

Statcast is planned.

The data itself is mirrored, validated and published by a companion repo,
[`fishbaseball-data`](https://github.com/FishOfPitt116/fishbaseball-data) — see its README for
the pipeline, the release format, and the full table/column list. This package is the client:
it downloads, caches and verifies what that pipeline publishes.

## Quickstart

```python
import fishbaseball as fb

fb.lahman.tables()  # every table name
fb.lahman.load("batting")  # -> polars DataFrame, the whole table
fb.lahman.batting(1927, player_id="ruthba01")  # -> Ruth's 1927 season (60 HR)
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
prov.version  # the release tag actually served, e.g. "lahman-2026-09-28"
prov.from_cache  # True if this didn't hit the network
prov.attribution  # for citing the data
```

### Pinning a version

```python
fb.lahman.load("teams", version="2026-09-28")  # an exact release
fb.lahman.load("teams", version="2025")  # the newest release of SABR's "2025" version
fb.lahman.version()  # the tag load() would currently use
fb.lahman.releases()  # every known release, as a DataFrame
```

### Caching and offline use

Tables are downloaded once per release and cached under a per-OS user cache directory
(`platformdirs.user_cache_dir("fishbaseball")` unless overridden). Every call after the first
for a given table and release reads from disk; the release pointer itself is rechecked at most
once a week (configurable) unless you ask for a refresh.

```python
fb.cache.info()  # what's cached, and how big
fb.cache.prefetch("lahman")  # download everything once, e.g. before going offline
fb.cache.purge()  # clear it (add source=/version= to be selective)

fb.lahman.load("batting", refresh=True)  # force a check for a newer release
fb.lahman.load("batting", offline=True)  # never touch the network; cache or raise
```

If a release can't be fetched or fails verification, fishbaseball falls back to the newest
still-good cached release and issues a `StaleDataWarning` rather than failing outright — set
`fb.config.set(strict=True)` to raise instead.

### Configuration

```python
fb.config.set(
    backend="pandas",  # or "polars" (default)
    cache_dir="...",  # override the default cache location
    offline=False,  # default for every call unless overridden per-call
    strict=False,  # raise instead of warning on a stale fallback
    ttl=7 * 24 * 3600,  # seconds before the release pointer is rechecked
)
```

## Retrosheet

```python
import polars as pl
import fishbaseball as fb

fb.retrosheet.plays(2024, team="PIT")  # every play of the Pirates' 2024 games
fb.retrosheet.plays(1956, game_id="NYA195610080", game_type=None)  # Larsen's perfect game
fb.retrosheet.batting(1927, player_id="ruthb101")["b_hr"].sum()  # 60: sum the per-game rows
```

Seven tables: `plays`, `game_info`, `batting`, `pitching`, `fielding`, `team_stats` and
`all_players`, each with its own function (`fb.retrosheet.plays(...)`, ...) and the general
`fb.retrosheet.load(table, ...)`. `plays` is one row per play, with the event, count, base/out
state before and after, runners, lineup and fielders. The stat tables are **per game**: one row
per player (or team) per game, so a season total is a sum.

```python
games = fb.retrosheet.game_info(2024, team="PIT")  # one row per game
runs = fb.retrosheet.team_stats(2024, team="PIT")  # one row per game: innings, LOB, totals
hrs = (
    fb.retrosheet.batting(2024, team="PIT")  # season totals by summing games
    .group_by("id")
    .agg(pl.col("b_hr").sum())
    .sort("b_hr", descending=True)
)
```

### Seasons, `lazy` and memory

The five large tables (`plays`, `batting`, `pitching`, `fielding`, `team_stats`) are published
as one Parquet file per season, and fishbaseball downloads only the seasons you ask for. They
therefore **require `seasons`** (one year, a list, a `range`, ...). One season of `plays` is
about 190,000 rows by 178 columns (about 8 MB to download, about 36 MB in memory); all of
history is 17 million rows, so there are two ways to ask for many seasons:

```python
fb.retrosheet.plays(all_seasons=True)  # everything, eagerly: you probably don't want this

lf = fb.retrosheet.plays(range(2015, 2025), lazy=True, columns=["gid", "batter", "event", "hr"])
lf.group_by("batter").agg(pl.col("hr").sum()).sort("hr", descending=True).head(10).collect()
```

`lazy=True` returns a polars `LazyFrame` over the cached files, so only the columns and rows a
query needs are ever read (it needs the polars backend). `columns=[...]` projects on any call.
`game_info` and `all_players` are single small files, so `seasons` is optional for them.

### `game_type` and `stattype`

- `game_type` defaults to `"regular"`, the regular season only. Pass `None` for every game, or
  one or a list of `"regular"`, `"worldseries"`, `"lcs"`, `"divisionseries"`, `"wildcard"`,
  `"allstar"`, `"exhibition"`, `"playoff"`, `"championship"`. (Two 1933 games have no recorded
  game type, so the default leaves them out.)
- `stattype` (the stat tables) defaults to `"value"`, Retrosheet's best estimate of each figure.
  `"official"` gives the officially recorded figure where it differs, and `None` returns every
  row, in which case sums double-count.
- `team=` on `plays` and `game_info` matches either side of a game (batting or pitching team;
  visitor or home). On the stat tables it is that player's or team's own team.

### Joining to Lahman

Player ids are Retrosheet's (`ruthb101`) and returned as-is. Lahman's `people.retro_id` maps
them to Lahman's `player_id`:

```python
people = fb.lahman.people().select("player_id", "retro_id", "name_first", "name_last")
fb.retrosheet.batting(2001, team="SFN").join(people, left_on="id", right_on="retro_id")
```

Provenance, pinning, offline use and the cache work as above. A multi-season call returns one
`Provenance` whose `partitions` lists each season used, the release it came from, and whether it
was a cache hit. Partition files are stored once, by checksum, however many releases reference
them, so a new release that re-publishes one season re-downloads only that season. Pre-load
what you need with `fb.cache.prefetch("retrosheet", tables=["plays"], seasons=range(2015, 2025))`
(with no arguments it takes everything, about 1 GB), and `fb.cache.info()` shows how many of a
table's seasons are cached.

> The information used here was obtained free of charge from and is copyrighted by Retrosheet.
> Interested parties may contact Retrosheet at "www.retrosheet.org".

### Status

```python
fb.sources()  # one row per source: what you have cached, what's published, when last checked
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
the Retrosheet data is © Retrosheet and carries Retrosheet's own notice, quoted above.
`return_provenance=True` on either source gives you the exact attribution string to cite,
and see [`fishbaseball-data`](https://github.com/FishOfPitt116/fishbaseball-data) for the full
license text and the Negro Leagues data's Seamheads.com attribution.
