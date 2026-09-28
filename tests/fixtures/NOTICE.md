# Test fixture notice

Files under `lahman/` are a trimmed copy of `fishbaseball-data`'s `lahman-2026-09-28` release:
the real `manifest.json` and `latest.json` (URLs for the four tables below rewritten to
`https://fixtures.test/...` so tests never touch the network without `respx` mocking it), and
four of its 27 tables trimmed to a few hundred rows or fewer (`batting`, `people`, `teams`,
`salaries`), keeping Babe Ruth's 1927 season, Barry Bonds's 2001 season and salary, Hank
Aaron's full career, and the 2025 Teams rows.

The other 23 tables in `manifest.json` still point at the real GitHub release and have no
fixture bytes on disk; a test that tries to download one is a mistake, not a fixture gap.

Underlying data: Lahman Baseball Database, © SABR via Sean Lahman, CC BY-SA 3.0
(http://creativecommons.org/licenses/by-sa/3.0/). Negro Leagues data licensed to SABR by
Seamheads.com.
