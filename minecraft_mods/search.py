"""Filter the mod catalog the same way a reader scans the cards."""

from __future__ import annotations

from dataclasses import asdict

from minecraft_mods.catalog import ModEntry, loader_panels


def select_mods(
    mods: list[ModEntry],
    *,
    q: str = "",
    loader: str = "",
    minecraft: str = "",
    license_name: str = "",
) -> list[ModEntry]:
    tokens = [part.casefold() for part in q.split() if part.strip()]
    wanted_loader = loader.strip().casefold()
    wanted_game = minecraft.strip().casefold()
    wanted_license = license_name.strip().casefold()
    chosen = []
    for mod in mods:
        if wanted_loader and wanted_loader not in _loaders(mod):
            continue
        if wanted_game and wanted_game not in (mod.minecraft or "").casefold():
            continue
        if wanted_license and wanted_license not in _license_text(mod):
            continue
        if tokens and not all(token in _haystack(mod) for token in tokens):
            continue
        chosen.append(mod)
    return sorted(chosen, key=lambda item: item.name.casefold())


def mod_document(mod: ModEntry) -> dict:
    document = asdict(mod)
    document["loader_tabs"] = [
        {
            "loader": name,
            "mod_jars": [asdict(jar) for jar in own],
            "dependency_jars": [asdict(jar) for jar in deps],
            "download": f"/mods/{mod.repo}/jars.zip?loader={name.casefold()}",
        }
        for name, own, deps in loader_panels(mod)
    ]
    document["download"] = f"/mods/{mod.repo}/jars.zip"
    return document


def _loaders(mod: ModEntry) -> set[str]:
    names = {loader.casefold() for loader in mod.loaders}
    for jar in (*mod.mod_jars, *mod.dependency_jars):
        names.update(loader.casefold() for loader in jar.loaders)
    return names


def _license_text(mod: ModEntry) -> str:
    return " ".join((mod.license_id or "", mod.license_name or "")).casefold()


def _haystack(mod: ModEntry) -> str:
    jars = [jar.name for jar in (*mod.mod_jars, *mod.dependency_jars)]
    parts = [
        mod.repo,
        mod.name,
        mod.description_en,
        mod.description_ru,
        mod.license_id,
        mod.license_name,
        mod.version,
        mod.minecraft,
        mod.modrinth_url,
        mod.modrinth_state,
        " ".join(mod.loaders),
        " ".join(jars),
    ]
    return " ".join(part for part in parts if part).casefold()
