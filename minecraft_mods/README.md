# mods

A list of Minecraft mods published as separate GitHub repositories under [Nergan](https://github.com/Nergan). The page is served at `/mods`.

A repository is included when its name ends with `mod`. For each one the page shows the readme summary, license, GitHub link, Modrinth link, the mod jar from the latest GitHub release, and the companion jars from that same release.

`MODRINTH_TOKEN` is optional. With it, projects that exist on Modrinth but are still in review are marked as such. Without it, a declared Modrinth project that has no public page is reported as not public yet.

Readme and license files are read from raw.githubusercontent.com. The latest release still comes from the GitHub API. `GITHUB_TOKEN` is optional and raises that API limit when the Space address is being throttled.
