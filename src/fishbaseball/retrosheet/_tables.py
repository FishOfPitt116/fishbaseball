"""One function per Retrosheet table, all delegating to the same load path as `load()`.
Written out explicitly, not generated at import time, so autocomplete, type checkers and
per-table docstrings work. Filters are offered only for columns that table actually has.

`load("<table>")` is still the general entry point, and the only way to reach a table
added upstream before its function exists here.

See fb.retrosheet.tables() for the full current table list."""

from __future__ import annotations

import difflib
from typing import Any

import polars as pl

from fishbaseball._core.frames import as_list
from fishbaseball.retrosheet import _finish, _load_raw

__all__ = [
    "plays",
    "game_info",
    "team_stats",
    "batting",
    "pitching",
    "fielding",
    "all_players",
]

# Retrosheet's `gametype` values (game_info, plays and every stat table carry the column).
GAME_TYPES = (
    "regular",
    "worldseries",
    "lcs",
    "divisionseries",
    "wildcard",
    "allstar",
    "exhibition",
    "playoff",
    "championship",
)

# Fielding positions by their usual abbreviation; `d_pos` holds the number.
POSITIONS = {"P": 1, "C": 2, "1B": 3, "2B": 4, "3B": 5, "SS": 6, "LF": 7, "CF": 8, "RF": 9}

_LOAD_OPTIONS = ("version", "refresh", "offline", "return_provenance")


# ---- shared machinery ---------------------------------------------------------------------


def _isin(column: str, values: Any) -> pl.Expr | None:
    return None if values is None else pl.col(column).is_in(as_list(values))


def _either(columns: tuple[str, str], values: Any) -> pl.Expr | None:
    """True where either column is one of `values` (a team on either side of a game)."""
    if values is None:
        return None
    wanted = as_list(values)
    return pl.col(columns[0]).is_in(wanted) | pl.col(columns[1]).is_in(wanted)


class _DefaultGameType:
    """The `game_type` default: `"regular"`, unless a `game_id` is given. Asking for a game by
    its id means that game, whatever kind it was, so the default must not filter out a World
    Series game; an explicitly passed `game_type` (even `"regular"`) always applies."""

    def __repr__(self) -> str:
        return "'regular' (no filter when game_id is given)"


DEFAULT_GAME_TYPE: Any = _DefaultGameType()


def _game_type(values: Any, game_id: Any = None) -> pl.Expr | None:
    if values is DEFAULT_GAME_TYPE:
        values = None if game_id is not None else "regular"
    if values is None:
        return None
    wanted = as_list(values)
    for value in wanted:
        if value not in GAME_TYPES:
            close = difflib.get_close_matches(str(value), GAME_TYPES, n=1)
            hint = f"; did you mean {close[0]!r}?" if close else ""
            raise ValueError(
                f"unknown game_type {value!r}{hint} known game types: {list(GAME_TYPES)}"
            )
    return pl.col("gametype").is_in(wanted)


def _position(values: Any) -> pl.Expr | None:
    if values is None:
        return None
    numbers = []
    for value in as_list(values):
        if isinstance(value, str):
            if value.upper() not in POSITIONS:
                raise ValueError(
                    f"unknown position {value!r}; use a number (1-9) or one of {list(POSITIONS)}"
                )
            value = POSITIONS[value.upper()]
        numbers.append(value)
    return pl.col("d_pos").is_in(numbers)


def _options(
    function: str, load_kwargs: dict[str, Any], filters: tuple[str, ...]
) -> dict[str, Any]:
    """The pass-through load options, or a `ValueError` for anything else — a keyword this
    function has no filter for, with a did-you-mean."""
    for key in load_kwargs:
        if key not in _LOAD_OPTIONS:
            known = [*filters, *_LOAD_OPTIONS]
            close = difflib.get_close_matches(key, known, n=1)
            hint = f"; did you mean {close[0]!r}?" if close else ""
            raise ValueError(
                f"{function}() has no filter {key!r}{hint} filters: {list(filters)}; "
                f"other options: {list(_LOAD_OPTIONS)}"
            )
    return load_kwargs


def _run(
    function: str,
    table: str,
    *,
    seasons: Any,
    all_seasons: bool,
    lazy: bool,
    columns: Any,
    conditions: list[pl.Expr | None],
    filters: tuple[str, ...],
    load_kwargs: dict[str, Any],
) -> Any:
    options = dict(_options(function, load_kwargs, filters))
    return_provenance = options.pop("return_provenance", False)
    loaded = _load_raw(table, seasons=seasons, all_seasons=all_seasons, lazy=lazy, **options)
    lf = loaded.lf
    for condition in conditions:
        if condition is not None:
            lf = lf.filter(condition)
    return _finish(
        loaded, table, columns=columns, lazy=lazy, return_provenance=return_provenance, lf=lf
    )


# ---- play-by-play and games ---------------------------------------------------------------


def plays(
    seasons: Any = None,
    *,
    team: Any = None,
    game_id: Any = None,
    game_type: Any = DEFAULT_GAME_TYPE,
    columns: Any = None,
    lazy: bool = False,
    all_seasons: bool = False,
    **load_kwargs: Any,
) -> Any:
    """Parsed play-by-play: one row per play (plate appearance, stolen base, substitution
    marker, ...), with the event string, the count, base/out state before and after, who
    was on the bases, the lineup and fielders, and ~160 more columns. Primary key: `gid`,
    `pn`. Season column: `season`. Published one Parquet file per season.

    `seasons` is required (one season, a list, a `range`, ...) unless you pass
    `all_seasons=True` or `lazy=True`. One modern season is about 190,000 rows by 178 columns
    (about 8 MB downloaded, about 36 MB in memory); the full history is 17 million rows, so
    for many seasons use `lazy=True` and `columns=[...]`.

    Filters (each takes one value or a list; `None` means no filter):

    * `team`: a team id such as `"PIT"`; matches plays where it is **either** the batting
      or the pitching team, i.e. every play of that team's games. For one side only,
      filter `batteam` / `pitteam` on the result.
    * `game_id`: a Retrosheet game id (`gid`) such as `"NYA195610080"`.
    * `game_type`: default `"regular"`, the regular season only, except that giving `game_id`
      switches the default off so a postseason game is found by its id (the default
      also leaves out the two 1933 games with no recorded game type);
      `None` for every game type; or one or a list of
      `"regular"`, `"worldseries"`, `"lcs"`, `"divisionseries"`, `"wildcard"`, `"allstar"`,
      `"exhibition"`, `"playoff"`, `"championship"`.
    * `columns`: keep only these columns, in this order.

    `lazy=True` returns a polars `LazyFrame`. Extra keyword arguments (`version`, `refresh`,
    `offline`, `return_provenance`) pass through to `load()`. Batter and pitcher ids are
    Retrosheet ids; Lahman's `people.retro_id` joins them to Lahman's `player_id`.

    The information used here was obtained free of charge from and is copyrighted by
    Retrosheet. Interested parties may contact Retrosheet at "www.retrosheet.org".
    """
    return _run(
        "plays",
        "plays",
        seasons=seasons,
        all_seasons=all_seasons,
        lazy=lazy,
        columns=columns,
        conditions=[
            _either(("batteam", "pitteam"), team),
            _isin("gid", game_id),
            _game_type(game_type, game_id),
        ],
        filters=("team", "game_id", "game_type"),
        load_kwargs=load_kwargs,
    )


def game_info(
    seasons: Any = None,
    *,
    team: Any = None,
    game_id: Any = None,
    game_type: Any = DEFAULT_GAME_TYPE,
    columns: Any = None,
    lazy: bool = False,
    **load_kwargs: Any,
) -> Any:
    """One row per game: teams, date, park, start time, weather, attendance, umpires, winning
    and losing pitchers, final score, and the game's `gametype`. Primary key: `gid`. Season
    column: `season`. A single file of about 226,000 rows (every game in the release, about 5
    MB), so `seasons` is optional.

    Filters (each takes one value or a list; `None` means no filter):

    * `seasons`: one season, or a list / `range`.
    * `team`: a team id such as `"PIT"`; matches games where it is **either** the visitor
      (`visteam`) or the home team (`hometeam`).
    * `game_id`: a Retrosheet game id (`gid`).
    * `game_type`: default `"regular"` (regular season only, except that giving `game_id`
      switches the default off so a postseason game is found by its id; the default also
      excludes the two 1933 games with no recorded game type);
      `None` for every game type; or one or a list of
      `"regular"`, `"worldseries"`, `"lcs"`, `"divisionseries"`, `"wildcard"`, `"allstar"`,
      `"exhibition"`, `"playoff"`, `"championship"`.
    * `columns`: keep only these columns, in this order.

    `lazy=True` returns a polars `LazyFrame`. Extra keyword arguments (`version`, `refresh`,
    `offline`, `return_provenance`) pass through to `load()`.

    The information used here was obtained free of charge from and is copyrighted by
    Retrosheet. Interested parties may contact Retrosheet at "www.retrosheet.org".
    """
    return _run(
        "game_info",
        "game_info",
        seasons=seasons,
        all_seasons=False,
        lazy=lazy,
        columns=columns,
        conditions=[
            _either(("visteam", "hometeam"), team),
            _isin("gid", game_id),
            _game_type(game_type, game_id),
        ],
        filters=("team", "game_id", "game_type"),
        load_kwargs=load_kwargs,
    )


def team_stats(
    seasons: Any = None,
    *,
    team: Any = None,
    game_id: Any = None,
    game_type: Any = DEFAULT_GAME_TYPE,
    stattype: Any = "value",
    columns: Any = None,
    lazy: bool = False,
    all_seasons: bool = False,
    **load_kwargs: Any,
) -> Any:
    """One row per team per game: runs by inning (`inn1`...), left on base, the manager, the
    team's batting, pitching and fielding totals for the game, and its starting lineup.
    Primary key: `gid`, `team`, `stattype`. Season column: `season`. Published one Parquet
    file per season (about 5,000 rows each for a modern season).

    `seasons` is required (one season, a list, a `range`, ...) unless you pass
    `all_seasons=True` or `lazy=True`.

    Filters (each takes one value or a list; `None` means no filter):

    * `team`: a team id such as `"PIT"`: that team's row in each game (the opponent is in
      `opp`).
    * `game_id`: a Retrosheet game id (`gid`).
    * `game_type`: default `"regular"` (regular season only, except that giving `game_id`
      switches the default off so a postseason game is found by its id; the default also
      excludes the two 1933 games with no recorded game type);
      `None` for every game type; or one or a list of
      `"regular"`, `"worldseries"`, `"lcs"`, `"divisionseries"`, `"wildcard"`, `"allstar"`,
      `"exhibition"`, `"playoff"`, `"championship"`.
    * `stattype`: default `"value"`, Retrosheet's best estimate of each figure; `"official"`
      for the officially recorded figure where it differs; `None` for every stattype (a
      game can then appear more than once). Summing without this filter double-counts.
    * `columns`: keep only these columns, in this order.

    `lazy=True` returns a polars `LazyFrame`. Extra keyword arguments (`version`, `refresh`,
    `offline`, `return_provenance`) pass through to `load()`.

    The information used here was obtained free of charge from and is copyrighted by
    Retrosheet. Interested parties may contact Retrosheet at "www.retrosheet.org".
    """
    return _run(
        "team_stats",
        "team_stats",
        seasons=seasons,
        all_seasons=all_seasons,
        lazy=lazy,
        columns=columns,
        conditions=[
            _isin("team", team),
            _isin("gid", game_id),
            _game_type(game_type, game_id),
            _isin("stattype", stattype),
        ],
        filters=("team", "game_id", "game_type", "stattype"),
        load_kwargs=load_kwargs,
    )


# ---- player game logs ---------------------------------------------------------------------


def batting(
    seasons: Any = None,
    *,
    player_id: Any = None,
    team: Any = None,
    game_id: Any = None,
    game_type: Any = DEFAULT_GAME_TYPE,
    stattype: Any = "value",
    columns: Any = None,
    lazy: bool = False,
    all_seasons: bool = False,
    **load_kwargs: Any,
) -> Any:
    """One row per batter per game: plate appearances, at-bats, hits, home runs, walks, and
    so on (columns prefixed `b_`), plus the batter's lineup slot and the game's date, park
    and result. Primary key: `gid`, `id`, `team`, `stattype`. Season column: `season`.
    Published one Parquet file per season (about 73,000 rows for a modern season).

    These are per-game rows. A season total is a sum over the games, for example
    `fb.retrosheet.batting(1927, player_id="ruthb101")["b_hr"].sum()` is Ruth's 60
    regular-season home runs.

    `seasons` is required (one season, a list, a `range`, ...) unless you pass
    `all_seasons=True` or `lazy=True`.

    Filters (each takes one value or a list; `None` means no filter):

    * `player_id`: a Retrosheet player id such as `"ruthb101"` (column `id`). Lahman's
      `people.retro_id` joins these to Lahman's `player_id`.
    * `team`: a team id such as `"PIT"`: the team the batter played for in that game (the
      opponent is in `opp`).
    * `game_id`: a Retrosheet game id (`gid`).
    * `game_type`: default `"regular"` (regular season only, except that giving `game_id`
      switches the default off so a postseason game is found by its id; the default also
      excludes the two 1933 games with no recorded game type);
      `None` for every game type; or one or a list of
      `"regular"`, `"worldseries"`, `"lcs"`, `"divisionseries"`, `"wildcard"`, `"allstar"`,
      `"exhibition"`, `"playoff"`, `"championship"`.
    * `stattype`: default `"value"`, Retrosheet's best estimate of each figure; `"official"`
      for the officially recorded figure where it differs; `None` for every stattype (a
      batter's game can then appear more than once, so sums double-count).
    * `columns`: keep only these columns, in this order.

    `lazy=True` returns a polars `LazyFrame`. Extra keyword arguments (`version`, `refresh`,
    `offline`, `return_provenance`) pass through to `load()`.

    The information used here was obtained free of charge from and is copyrighted by
    Retrosheet. Interested parties may contact Retrosheet at "www.retrosheet.org".
    """
    return _run(
        "batting",
        "batting",
        seasons=seasons,
        all_seasons=all_seasons,
        lazy=lazy,
        columns=columns,
        conditions=[
            _isin("id", player_id),
            _isin("team", team),
            _isin("gid", game_id),
            _game_type(game_type, game_id),
            _isin("stattype", stattype),
        ],
        filters=("player_id", "team", "game_id", "game_type", "stattype"),
        load_kwargs=load_kwargs,
    )


def pitching(
    seasons: Any = None,
    *,
    player_id: Any = None,
    team: Any = None,
    game_id: Any = None,
    game_type: Any = DEFAULT_GAME_TYPE,
    stattype: Any = "value",
    columns: Any = None,
    lazy: bool = False,
    all_seasons: bool = False,
    **load_kwargs: Any,
) -> Any:
    """One row per pitcher per game: outs recorded (`p_ipouts`, three per inning), batters
    faced, hits, runs, earned runs, walks, strikeouts, and so on (columns prefixed `p_`),
    plus win / loss / save flags and the game's date, park and result. Primary key: `gid`,
    `id`, `team`, `stattype`. Season column: `season`. Published one Parquet file per season
    (about 21,000 rows for a modern season).

    These are per-game rows; a season total is a sum over the games.

    `seasons` is required (one season, a list, a `range`, ...) unless you pass
    `all_seasons=True` or `lazy=True`.

    Filters (each takes one value or a list; `None` means no filter):

    * `player_id`: a Retrosheet player id (column `id`). Lahman's `people.retro_id` joins
      these to Lahman's `player_id`.
    * `team`: a team id such as `"PIT"`: the team the pitcher pitched for in that game.
    * `game_id`: a Retrosheet game id (`gid`).
    * `game_type`: default `"regular"` (regular season only, except that giving `game_id`
      switches the default off so a postseason game is found by its id; the default also
      excludes the two 1933 games with no recorded game type);
      `None` for every game type; or one or a list of
      `"regular"`, `"worldseries"`, `"lcs"`, `"divisionseries"`, `"wildcard"`, `"allstar"`,
      `"exhibition"`, `"playoff"`, `"championship"`.
    * `stattype`: default `"value"`, Retrosheet's best estimate of each figure; `"official"`
      for the officially recorded figure where it differs; `None` for every stattype (sums
      then double-count).
    * `columns`: keep only these columns, in this order.

    `lazy=True` returns a polars `LazyFrame`. Extra keyword arguments (`version`, `refresh`,
    `offline`, `return_provenance`) pass through to `load()`.

    The information used here was obtained free of charge from and is copyrighted by
    Retrosheet. Interested parties may contact Retrosheet at "www.retrosheet.org".
    """
    return _run(
        "pitching",
        "pitching",
        seasons=seasons,
        all_seasons=all_seasons,
        lazy=lazy,
        columns=columns,
        conditions=[
            _isin("id", player_id),
            _isin("team", team),
            _isin("gid", game_id),
            _game_type(game_type, game_id),
            _isin("stattype", stattype),
        ],
        filters=("player_id", "team", "game_id", "game_type", "stattype"),
        load_kwargs=load_kwargs,
    )


def fielding(
    seasons: Any = None,
    *,
    player_id: Any = None,
    team: Any = None,
    game_id: Any = None,
    position: Any = None,
    game_type: Any = DEFAULT_GAME_TYPE,
    stattype: Any = "value",
    columns: Any = None,
    lazy: bool = False,
    all_seasons: bool = False,
    **load_kwargs: Any,
) -> Any:
    """One row per fielder per position per game: innings in the field (`d_ifouts`, outs),
    putouts, assists, errors, double plays, and so on (columns prefixed `d_`), plus the
    game's date, park and result. A player who moves between positions in a game has a row
    for each (`d_seq` orders them). Primary key: `gid`, `id`, `team`, `d_seq`, `d_pos`,
    `stattype`. Season column: `season`. Published one Parquet file per season (about 68,000
    rows for a modern season).

    These are per-game rows; a season total is a sum over the games.

    `seasons` is required (one season, a list, a `range`, ...) unless you pass
    `all_seasons=True` or `lazy=True`.

    Filters (each takes one value or a list; `None` means no filter):

    * `player_id`: a Retrosheet player id (column `id`). Lahman's `people.retro_id` joins
      these to Lahman's `player_id`.
    * `team`: a team id such as `"PIT"`: the team the fielder played for in that game.
    * `game_id`: a Retrosheet game id (`gid`).
    * `position`: a position number 1-9 (column `d_pos`) or its abbreviation: `"P"`, `"C"`,
      `"1B"`, `"2B"`, `"3B"`, `"SS"`, `"LF"`, `"CF"`, `"RF"`.
    * `game_type`: default `"regular"` (regular season only, except that giving `game_id`
      switches the default off so a postseason game is found by its id; the default also
      excludes the two 1933 games with no recorded game type);
      `None` for every game type; or one or a list of
      `"regular"`, `"worldseries"`, `"lcs"`, `"divisionseries"`, `"wildcard"`, `"allstar"`,
      `"exhibition"`, `"playoff"`, `"championship"`.
    * `stattype`: default `"value"`, Retrosheet's best estimate of each figure; `"official"`
      for the officially recorded figure where it differs; `None` for every stattype (sums
      then double-count).
    * `columns`: keep only these columns, in this order.

    `lazy=True` returns a polars `LazyFrame`. Extra keyword arguments (`version`, `refresh`,
    `offline`, `return_provenance`) pass through to `load()`.

    The information used here was obtained free of charge from and is copyrighted by
    Retrosheet. Interested parties may contact Retrosheet at "www.retrosheet.org".
    """
    return _run(
        "fielding",
        "fielding",
        seasons=seasons,
        all_seasons=all_seasons,
        lazy=lazy,
        columns=columns,
        conditions=[
            _isin("id", player_id),
            _isin("team", team),
            _isin("gid", game_id),
            _position(position),
            _game_type(game_type, game_id),
            _isin("stattype", stattype),
        ],
        filters=("player_id", "team", "game_id", "position", "game_type", "stattype"),
        load_kwargs=load_kwargs,
    )


# ---- players ------------------------------------------------------------------------------


def all_players(
    seasons: Any = None,
    *,
    player_id: Any = None,
    team: Any = None,
    columns: Any = None,
    lazy: bool = False,
    **load_kwargs: Any,
) -> Any:
    """One row per player per team per season: name, batting and throwing hand, and games
    played overall and at each position (`g`, `g_p`, `g_c`, `g_ss`, ...), with the dates of
    the first and last game. Primary key: `id`, `team`, `season`. Season column: `season`.
    A single file of about 131,000 rows (about 2 MB), so `seasons` is optional.

    Filters (each takes one value or a list; `None` means no filter):

    * `seasons`: one season, or a list / `range`.
    * `player_id`: a Retrosheet player id such as `"ruthb101"` (column `id`). Lahman's
      `people.retro_id` joins these to Lahman's `player_id`.
    * `team`: a team id such as `"PIT"`.
    * `columns`: keep only these columns, in this order.

    `lazy=True` returns a polars `LazyFrame`. Extra keyword arguments (`version`, `refresh`,
    `offline`, `return_provenance`) pass through to `load()`.

    The information used here was obtained free of charge from and is copyrighted by
    Retrosheet. Interested parties may contact Retrosheet at "www.retrosheet.org".
    """
    return _run(
        "all_players",
        "all_players",
        seasons=seasons,
        all_seasons=False,
        lazy=lazy,
        columns=columns,
        conditions=[_isin("id", player_id), _isin("team", team)],
        filters=("player_id", "team"),
        load_kwargs=load_kwargs,
    )
