# mods

A list of Minecraft mods published as separate GitHub repositories under [Nergan](https://github.com/Nergan). The page is served at `/mods`.

A repository is included when its name ends with `mod`. For each one the page shows the readme summary, license, GitHub link, and Modrinth link. Releases are one Minecraft version and one loader, tagged `minecraft-<version>-<loader>`. The card has a tab for each of those releases. Each release ships its jars and a prebuilt `all-jars.zip`; download all follows that zip. A repository that still has only an older `v*` release keeps a single jar list, and a release that mixed several loaders in one note still splits them into loader tabs.

`MODRINTH_TOKEN` is optional. With it, projects that exist on Modrinth but are still in review are marked as such. Without it, a declared Modrinth project that has no public page is reported as not public yet.

Readme and license files are read from raw.githubusercontent.com. Releases come from the GitHub API. `GITHUB_TOKEN` is optional and raises that API limit when the Space address is being throttled.

## API

`GET /mods/api` names the query fields. `GET /mods/api/mods` returns every card: name, both descriptions, repository, license, Minecraft version, loaders, jars, Modrinth link and state, and the readme text.

Filters combine. `q` keeps a card when every word occurs in the name, descriptions, repository, license, version, loaders, or jar names. `loader` keeps one loader (`Fabric`, `NeoForge`, `Forge`, or `Quilt`). `minecraft` matches the version text. `license` matches the license id or name. The list stays sorted by name.

`GET /mods/?download={repo}&minecraft={version}&loader={fabric|neoforge|forge|quilt}` redirects to that release's `all-jars.zip`. Without a prebuilt zip, the same address returns a zip built from the jars. The address stays on `/mods/`, the same page as the list.
