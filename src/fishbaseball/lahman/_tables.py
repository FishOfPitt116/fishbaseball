"""One thin wrapper per Lahman table, all delegating to the same load path as `load()`.
Written out explicitly, not generated at import time, so autocomplete, type checkers and
per-table docstrings work. Filters are offered only for columns that table actually has.

`load("<table>")` is still the general entry point, and the only way to reach a table
added upstream before its wrapper exists here.

See fb.lahman.tables() for the full current table list."""

from __future__ import annotations

from typing import Any

from fishbaseball._core.frames import filter_values
from fishbaseball.lahman import _finish, _load_raw


def allstar_full(
    seasons: Any = None,
    *,
    player_id: Any = None,
    team_id: Any = None,
    lg_id: Any = None,
    **load_kwargs: Any,
) -> Any:
    """Allstar full. Primary key: player_id, year_id, game_num, game_id, team_id, lg_id. Season
    column: year_id.

    `seasons`, `player_id`, `team_id`, `lg_id` filter to one value or a list of values, if
    given. Extra keyword arguments (`version`, `refresh`, `offline`, `return_provenance`)
    pass through to `load()`.
    """
    return_provenance = load_kwargs.pop("return_provenance", False)
    df, manifest, acquired = _load_raw("allstar_full", seasons=seasons, **load_kwargs)
    df = filter_values(df, "player_id", player_id)
    df = filter_values(df, "team_id", team_id)
    df = filter_values(df, "lg_id", lg_id)
    return _finish(df, "allstar_full", manifest, acquired, return_provenance)


def appearances(
    seasons: Any = None,
    *,
    player_id: Any = None,
    team_id: Any = None,
    lg_id: Any = None,
    **load_kwargs: Any,
) -> Any:
    """Appearances. Primary key: year_id, team_id, player_id. Season column: year_id.

    `seasons`, `player_id`, `team_id`, `lg_id` filter to one value or a list of values, if
    given. Extra keyword arguments (`version`, `refresh`, `offline`, `return_provenance`)
    pass through to `load()`.
    """
    return_provenance = load_kwargs.pop("return_provenance", False)
    df, manifest, acquired = _load_raw("appearances", seasons=seasons, **load_kwargs)
    df = filter_values(df, "player_id", player_id)
    df = filter_values(df, "team_id", team_id)
    df = filter_values(df, "lg_id", lg_id)
    return _finish(df, "appearances", manifest, acquired, return_provenance)


def awards_managers(
    seasons: Any = None, *, player_id: Any = None, lg_id: Any = None, **load_kwargs: Any
) -> Any:
    """Awards managers. Primary key: year_id, award_id, lg_id, player_id. Season column:
    year_id.

    `seasons`, `player_id`, `lg_id` filter to one value or a list of values, if given. Extra
    keyword arguments (`version`, `refresh`, `offline`, `return_provenance`) pass through to
    `load()`.
    """
    return_provenance = load_kwargs.pop("return_provenance", False)
    df, manifest, acquired = _load_raw("awards_managers", seasons=seasons, **load_kwargs)
    df = filter_values(df, "player_id", player_id)
    df = filter_values(df, "lg_id", lg_id)
    return _finish(df, "awards_managers", manifest, acquired, return_provenance)


def awards_players(
    seasons: Any = None, *, player_id: Any = None, lg_id: Any = None, **load_kwargs: Any
) -> Any:
    """Awards players. Primary key: year_id, award_id, lg_id, player_id, notes. Season column:
    year_id.

    `seasons`, `player_id`, `lg_id` filter to one value or a list of values, if given. Extra
    keyword arguments (`version`, `refresh`, `offline`, `return_provenance`) pass through to
    `load()`.
    """
    return_provenance = load_kwargs.pop("return_provenance", False)
    df, manifest, acquired = _load_raw("awards_players", seasons=seasons, **load_kwargs)
    df = filter_values(df, "player_id", player_id)
    df = filter_values(df, "lg_id", lg_id)
    return _finish(df, "awards_players", manifest, acquired, return_provenance)


def awards_share_managers(
    seasons: Any = None, *, player_id: Any = None, lg_id: Any = None, **load_kwargs: Any
) -> Any:
    """Awards share managers. Primary key: award_id, year_id, lg_id, player_id. Season column:
    year_id.

    `seasons`, `player_id`, `lg_id` filter to one value or a list of values, if given. Extra
    keyword arguments (`version`, `refresh`, `offline`, `return_provenance`) pass through to
    `load()`.
    """
    return_provenance = load_kwargs.pop("return_provenance", False)
    df, manifest, acquired = _load_raw("awards_share_managers", seasons=seasons, **load_kwargs)
    df = filter_values(df, "player_id", player_id)
    df = filter_values(df, "lg_id", lg_id)
    return _finish(df, "awards_share_managers", manifest, acquired, return_provenance)


def awards_share_players(
    seasons: Any = None, *, player_id: Any = None, lg_id: Any = None, **load_kwargs: Any
) -> Any:
    """Awards share players. Primary key: award_id, year_id, lg_id, player_id. Season column:
    year_id.

    `seasons`, `player_id`, `lg_id` filter to one value or a list of values, if given. Extra
    keyword arguments (`version`, `refresh`, `offline`, `return_provenance`) pass through to
    `load()`.
    """
    return_provenance = load_kwargs.pop("return_provenance", False)
    df, manifest, acquired = _load_raw("awards_share_players", seasons=seasons, **load_kwargs)
    df = filter_values(df, "player_id", player_id)
    df = filter_values(df, "lg_id", lg_id)
    return _finish(df, "awards_share_players", manifest, acquired, return_provenance)


def batting(
    seasons: Any = None,
    *,
    player_id: Any = None,
    team_id: Any = None,
    lg_id: Any = None,
    **load_kwargs: Any,
) -> Any:
    """Batting. Primary key: player_id, year_id, stint. Season column: year_id.

    `seasons`, `player_id`, `team_id`, `lg_id` filter to one value or a list of values, if
    given. Extra keyword arguments (`version`, `refresh`, `offline`, `return_provenance`)
    pass through to `load()`.
    """
    return_provenance = load_kwargs.pop("return_provenance", False)
    df, manifest, acquired = _load_raw("batting", seasons=seasons, **load_kwargs)
    df = filter_values(df, "player_id", player_id)
    df = filter_values(df, "team_id", team_id)
    df = filter_values(df, "lg_id", lg_id)
    return _finish(df, "batting", manifest, acquired, return_provenance)


def batting_post(
    seasons: Any = None,
    *,
    player_id: Any = None,
    team_id: Any = None,
    lg_id: Any = None,
    **load_kwargs: Any,
) -> Any:
    """Batting post. Primary key: year_id, round, player_id. Season column: year_id.

    `seasons`, `player_id`, `team_id`, `lg_id` filter to one value or a list of values, if
    given. Extra keyword arguments (`version`, `refresh`, `offline`, `return_provenance`)
    pass through to `load()`.
    """
    return_provenance = load_kwargs.pop("return_provenance", False)
    df, manifest, acquired = _load_raw("batting_post", seasons=seasons, **load_kwargs)
    df = filter_values(df, "player_id", player_id)
    df = filter_values(df, "team_id", team_id)
    df = filter_values(df, "lg_id", lg_id)
    return _finish(df, "batting_post", manifest, acquired, return_provenance)


def college_playing(seasons: Any = None, *, player_id: Any = None, **load_kwargs: Any) -> Any:
    """College playing. Primary key: player_id, school_id, year_id. Season column: year_id.

    `seasons`, `player_id` filter to one value or a list of values, if given. Extra keyword
    arguments (`version`, `refresh`, `offline`, `return_provenance`) pass through to
    `load()`.
    """
    return_provenance = load_kwargs.pop("return_provenance", False)
    df, manifest, acquired = _load_raw("college_playing", seasons=seasons, **load_kwargs)
    df = filter_values(df, "player_id", player_id)
    return _finish(df, "college_playing", manifest, acquired, return_provenance)


def fielding(
    seasons: Any = None,
    *,
    player_id: Any = None,
    team_id: Any = None,
    lg_id: Any = None,
    **load_kwargs: Any,
) -> Any:
    """Fielding. Primary key: player_id, year_id, stint, pos. Season column: year_id.

    `seasons`, `player_id`, `team_id`, `lg_id` filter to one value or a list of values, if
    given. Extra keyword arguments (`version`, `refresh`, `offline`, `return_provenance`)
    pass through to `load()`.
    """
    return_provenance = load_kwargs.pop("return_provenance", False)
    df, manifest, acquired = _load_raw("fielding", seasons=seasons, **load_kwargs)
    df = filter_values(df, "player_id", player_id)
    df = filter_values(df, "team_id", team_id)
    df = filter_values(df, "lg_id", lg_id)
    return _finish(df, "fielding", manifest, acquired, return_provenance)


def fielding_of(seasons: Any = None, *, player_id: Any = None, **load_kwargs: Any) -> Any:
    """Fielding of. Primary key: player_id, year_id, stint. Season column: year_id.

    `seasons`, `player_id` filter to one value or a list of values, if given. Extra keyword
    arguments (`version`, `refresh`, `offline`, `return_provenance`) pass through to
    `load()`.
    """
    return_provenance = load_kwargs.pop("return_provenance", False)
    df, manifest, acquired = _load_raw("fielding_of", seasons=seasons, **load_kwargs)
    df = filter_values(df, "player_id", player_id)
    return _finish(df, "fielding_of", manifest, acquired, return_provenance)


def fielding_of_split(
    seasons: Any = None,
    *,
    player_id: Any = None,
    team_id: Any = None,
    lg_id: Any = None,
    **load_kwargs: Any,
) -> Any:
    """Fielding of split. Primary key: player_id, year_id, stint, pos. Season column: year_id.

    `seasons`, `player_id`, `team_id`, `lg_id` filter to one value or a list of values, if
    given. Extra keyword arguments (`version`, `refresh`, `offline`, `return_provenance`)
    pass through to `load()`.
    """
    return_provenance = load_kwargs.pop("return_provenance", False)
    df, manifest, acquired = _load_raw("fielding_of_split", seasons=seasons, **load_kwargs)
    df = filter_values(df, "player_id", player_id)
    df = filter_values(df, "team_id", team_id)
    df = filter_values(df, "lg_id", lg_id)
    return _finish(df, "fielding_of_split", manifest, acquired, return_provenance)


def fielding_post(
    seasons: Any = None,
    *,
    player_id: Any = None,
    team_id: Any = None,
    lg_id: Any = None,
    **load_kwargs: Any,
) -> Any:
    """Fielding post. Primary key: player_id, year_id, round, pos. Season column: year_id.

    `seasons`, `player_id`, `team_id`, `lg_id` filter to one value or a list of values, if
    given. Extra keyword arguments (`version`, `refresh`, `offline`, `return_provenance`)
    pass through to `load()`.
    """
    return_provenance = load_kwargs.pop("return_provenance", False)
    df, manifest, acquired = _load_raw("fielding_post", seasons=seasons, **load_kwargs)
    df = filter_values(df, "player_id", player_id)
    df = filter_values(df, "team_id", team_id)
    df = filter_values(df, "lg_id", lg_id)
    return _finish(df, "fielding_post", manifest, acquired, return_provenance)


def hall_of_fame(seasons: Any = None, *, player_id: Any = None, **load_kwargs: Any) -> Any:
    """Hall of fame. Primary key: player_id, year_id, voted_by, category. Season column:
    year_id.

    `seasons`, `player_id` filter to one value or a list of values, if given. Extra keyword
    arguments (`version`, `refresh`, `offline`, `return_provenance`) pass through to
    `load()`.
    """
    return_provenance = load_kwargs.pop("return_provenance", False)
    df, manifest, acquired = _load_raw("hall_of_fame", seasons=seasons, **load_kwargs)
    df = filter_values(df, "player_id", player_id)
    return _finish(df, "hall_of_fame", manifest, acquired, return_provenance)


def home_games(seasons: Any = None, **load_kwargs: Any) -> Any:
    """Home games. Primary key: year_key, league_key, team_key, park_key. Season column:
    year_key.

    `seasons` filter to one value or a list of values, if given. Extra keyword arguments
    (`version`, `refresh`, `offline`, `return_provenance`) pass through to `load()`.
    """
    return_provenance = load_kwargs.pop("return_provenance", False)
    df, manifest, acquired = _load_raw("home_games", seasons=seasons, **load_kwargs)
    return _finish(df, "home_games", manifest, acquired, return_provenance)


def managers(
    seasons: Any = None,
    *,
    player_id: Any = None,
    team_id: Any = None,
    lg_id: Any = None,
    **load_kwargs: Any,
) -> Any:
    """Managers. Primary key: year_id, team_id, inseason. Season column: year_id.

    `seasons`, `player_id`, `team_id`, `lg_id` filter to one value or a list of values, if
    given. Extra keyword arguments (`version`, `refresh`, `offline`, `return_provenance`)
    pass through to `load()`.
    """
    return_provenance = load_kwargs.pop("return_provenance", False)
    df, manifest, acquired = _load_raw("managers", seasons=seasons, **load_kwargs)
    df = filter_values(df, "player_id", player_id)
    df = filter_values(df, "team_id", team_id)
    df = filter_values(df, "lg_id", lg_id)
    return _finish(df, "managers", manifest, acquired, return_provenance)


def managers_half(
    seasons: Any = None,
    *,
    player_id: Any = None,
    team_id: Any = None,
    lg_id: Any = None,
    **load_kwargs: Any,
) -> Any:
    """Managers half. Primary key: player_id, year_id, team_id, half. Season column: year_id.

    `seasons`, `player_id`, `team_id`, `lg_id` filter to one value or a list of values, if
    given. Extra keyword arguments (`version`, `refresh`, `offline`, `return_provenance`)
    pass through to `load()`.
    """
    return_provenance = load_kwargs.pop("return_provenance", False)
    df, manifest, acquired = _load_raw("managers_half", seasons=seasons, **load_kwargs)
    df = filter_values(df, "player_id", player_id)
    df = filter_values(df, "team_id", team_id)
    df = filter_values(df, "lg_id", lg_id)
    return _finish(df, "managers_half", manifest, acquired, return_provenance)


def parks(**load_kwargs: Any) -> Any:
    """Parks. Primary key: id. Has no season column.

    Takes no filters of its own. Extra keyword arguments (`version`, `refresh`, `offline`,
    `return_provenance`) pass through to `load()`.
    """
    return_provenance = load_kwargs.pop("return_provenance", False)
    df, manifest, acquired = _load_raw("parks", **load_kwargs)
    return _finish(df, "parks", manifest, acquired, return_provenance)


def people(*, player_id: Any = None, **load_kwargs: Any) -> Any:
    """People. Primary key: player_id. Has no season column.

    `player_id` filter to one value or a list of values, if given. Extra keyword arguments
    (`version`, `refresh`, `offline`, `return_provenance`) pass through to `load()`.
    """
    return_provenance = load_kwargs.pop("return_provenance", False)
    df, manifest, acquired = _load_raw("people", **load_kwargs)
    df = filter_values(df, "player_id", player_id)
    return _finish(df, "people", manifest, acquired, return_provenance)


def pitching(
    seasons: Any = None,
    *,
    player_id: Any = None,
    team_id: Any = None,
    lg_id: Any = None,
    **load_kwargs: Any,
) -> Any:
    """Pitching. Primary key: player_id, year_id, stint. Season column: year_id.

    `seasons`, `player_id`, `team_id`, `lg_id` filter to one value or a list of values, if
    given. Extra keyword arguments (`version`, `refresh`, `offline`, `return_provenance`)
    pass through to `load()`.
    """
    return_provenance = load_kwargs.pop("return_provenance", False)
    df, manifest, acquired = _load_raw("pitching", seasons=seasons, **load_kwargs)
    df = filter_values(df, "player_id", player_id)
    df = filter_values(df, "team_id", team_id)
    df = filter_values(df, "lg_id", lg_id)
    return _finish(df, "pitching", manifest, acquired, return_provenance)


def pitching_post(
    seasons: Any = None,
    *,
    player_id: Any = None,
    team_id: Any = None,
    lg_id: Any = None,
    **load_kwargs: Any,
) -> Any:
    """Pitching post. Primary key: player_id, year_id, round. Season column: year_id.

    `seasons`, `player_id`, `team_id`, `lg_id` filter to one value or a list of values, if
    given. Extra keyword arguments (`version`, `refresh`, `offline`, `return_provenance`)
    pass through to `load()`.
    """
    return_provenance = load_kwargs.pop("return_provenance", False)
    df, manifest, acquired = _load_raw("pitching_post", seasons=seasons, **load_kwargs)
    df = filter_values(df, "player_id", player_id)
    df = filter_values(df, "team_id", team_id)
    df = filter_values(df, "lg_id", lg_id)
    return _finish(df, "pitching_post", manifest, acquired, return_provenance)


def salaries(
    seasons: Any = None,
    *,
    player_id: Any = None,
    team_id: Any = None,
    lg_id: Any = None,
    **load_kwargs: Any,
) -> Any:
    """Salaries. Primary key: year_id, team_id, player_id. Season column: year_id.

    `seasons`, `player_id`, `team_id`, `lg_id` filter to one value or a list of values, if
    given. Extra keyword arguments (`version`, `refresh`, `offline`, `return_provenance`)
    pass through to `load()`.
    """
    return_provenance = load_kwargs.pop("return_provenance", False)
    df, manifest, acquired = _load_raw("salaries", seasons=seasons, **load_kwargs)
    df = filter_values(df, "player_id", player_id)
    df = filter_values(df, "team_id", team_id)
    df = filter_values(df, "lg_id", lg_id)
    return _finish(df, "salaries", manifest, acquired, return_provenance)


def schools(**load_kwargs: Any) -> Any:
    """Schools. Primary key: school_id. Has no season column.

    Takes no filters of its own. Extra keyword arguments (`version`, `refresh`, `offline`,
    `return_provenance`) pass through to `load()`.
    """
    return_provenance = load_kwargs.pop("return_provenance", False)
    df, manifest, acquired = _load_raw("schools", **load_kwargs)
    return _finish(df, "schools", manifest, acquired, return_provenance)


def series_post(seasons: Any = None, **load_kwargs: Any) -> Any:
    """Series post. Primary key: year_id, round. Season column: year_id.

    `seasons` filter to one value or a list of values, if given. Extra keyword arguments
    (`version`, `refresh`, `offline`, `return_provenance`) pass through to `load()`.
    """
    return_provenance = load_kwargs.pop("return_provenance", False)
    df, manifest, acquired = _load_raw("series_post", seasons=seasons, **load_kwargs)
    return _finish(df, "series_post", manifest, acquired, return_provenance)


def teams(
    seasons: Any = None, *, team_id: Any = None, lg_id: Any = None, **load_kwargs: Any
) -> Any:
    """Teams. Primary key: year_id, team_id. Season column: year_id.

    `seasons`, `team_id`, `lg_id` filter to one value or a list of values, if given. Extra
    keyword arguments (`version`, `refresh`, `offline`, `return_provenance`) pass through to
    `load()`.
    """
    return_provenance = load_kwargs.pop("return_provenance", False)
    df, manifest, acquired = _load_raw("teams", seasons=seasons, **load_kwargs)
    df = filter_values(df, "team_id", team_id)
    df = filter_values(df, "lg_id", lg_id)
    return _finish(df, "teams", manifest, acquired, return_provenance)


def teams_franchises(**load_kwargs: Any) -> Any:
    """Teams franchises. Primary key: franch_id. Has no season column.

    Takes no filters of its own. Extra keyword arguments (`version`, `refresh`, `offline`,
    `return_provenance`) pass through to `load()`.
    """
    return_provenance = load_kwargs.pop("return_provenance", False)
    df, manifest, acquired = _load_raw("teams_franchises", **load_kwargs)
    return _finish(df, "teams_franchises", manifest, acquired, return_provenance)


def teams_half(
    seasons: Any = None, *, team_id: Any = None, lg_id: Any = None, **load_kwargs: Any
) -> Any:
    """Teams half. Primary key: year_id, team_id, half. Season column: year_id.

    `seasons`, `team_id`, `lg_id` filter to one value or a list of values, if given. Extra
    keyword arguments (`version`, `refresh`, `offline`, `return_provenance`) pass through to
    `load()`.
    """
    return_provenance = load_kwargs.pop("return_provenance", False)
    df, manifest, acquired = _load_raw("teams_half", seasons=seasons, **load_kwargs)
    df = filter_values(df, "team_id", team_id)
    df = filter_values(df, "lg_id", lg_id)
    return _finish(df, "teams_half", manifest, acquired, return_provenance)


__all__ = [
    "allstar_full",
    "appearances",
    "awards_managers",
    "awards_players",
    "awards_share_managers",
    "awards_share_players",
    "batting",
    "batting_post",
    "college_playing",
    "fielding",
    "fielding_of",
    "fielding_of_split",
    "fielding_post",
    "hall_of_fame",
    "home_games",
    "managers",
    "managers_half",
    "parks",
    "people",
    "pitching",
    "pitching_post",
    "salaries",
    "schools",
    "series_post",
    "teams",
    "teams_franchises",
    "teams_half",
]
