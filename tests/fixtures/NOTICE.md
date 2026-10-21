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

Files under `retrosheet/` are a trimmed copy of `fishbaseball-data`'s `retrosheet-2026-10-20`
release: the real `manifest.json` and `latest.json` (partition and table URLs rewritten to
`https://fixtures.test/...`, `upstream_seen` and each table's partitions cut down to the three
seasons below, checksums/row counts recomputed), and all seven tables trimmed. Seasons 1927,
1956 and 2001 only. Per season, every row for ~10 games (the first eight Pirates regular-season
games plus a couple of World Series games; 1956 includes Larsen's perfect game `NYA195610080`).
`batting` additionally keeps every row for Babe Ruth (`ruthb101`, 1927) and Barry Bonds
(`bondb001`, 2001) so their season totals (60 and 73 regular-season home runs) can be checked;
those rows reference games not present in the other tables. `all_players` keeps rows for PIT,
NYA, SFN and BRO in those seasons.

Retrosheet notice: The information used here was obtained free of charge from and is copyrighted
by Retrosheet. Interested parties may contact Retrosheet at "www.retrosheet.org".
