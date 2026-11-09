"""Biome names from a Xaero palette, and lookups over the published spots."""

from __future__ import annotations

LABELS = {
    "minecraft:plains": ("Plains", "Равнины"),
    "minecraft:sunflower_plains": ("Sunflower Plains", "Подсолнуховая равнина"),
    "minecraft:snowy_plains": ("Snowy Plains", "Заснеженные равнины"),
    "minecraft:ice_spikes": ("Ice Spikes", "Ледяные шипы"),
    "minecraft:desert": ("Desert", "Пустыня"),
    "minecraft:swamp": ("Swamp", "Болото"),
    "minecraft:mangrove_swamp": ("Mangrove Swamp", "Мангровое болото"),
    "minecraft:forest": ("Forest", "Лес"),
    "minecraft:flower_forest": ("Flower Forest", "Цветочный лес"),
    "minecraft:birch_forest": ("Birch Forest", "Берёзовый лес"),
    "minecraft:dark_forest": ("Dark Forest", "Тёмный лес"),
    "minecraft:old_growth_birch_forest": ("Old Growth Birch Forest", "Старовозрастный берёзовый лес"),
    "minecraft:old_growth_pine_taiga": ("Old Growth Pine Taiga", "Старовозрастная сосновая тайга"),
    "minecraft:old_growth_spruce_taiga": ("Old Growth Spruce Taiga", "Старовозрастная еловая тайга"),
    "minecraft:taiga": ("Taiga", "Тайга"),
    "minecraft:snowy_taiga": ("Snowy Taiga", "Заснеженная тайга"),
    "minecraft:savanna": ("Savanna", "Саванна"),
    "minecraft:savanna_plateau": ("Savanna Plateau", "Плато саванны"),
    "minecraft:windswept_hills": ("Windswept Hills", "Выветренные холмы"),
    "minecraft:windswept_gravelly_hills": ("Windswept Gravelly Hills", "Выветренные гравийные холмы"),
    "minecraft:windswept_forest": ("Windswept Forest", "Выветренный лес"),
    "minecraft:windswept_savanna": ("Windswept Savanna", "Выветренная саванна"),
    "minecraft:jungle": ("Jungle", "Джунгли"),
    "minecraft:sparse_jungle": ("Sparse Jungle", "Разреженные джунгли"),
    "minecraft:bamboo_jungle": ("Bamboo Jungle", "Бамбуковые джунгли"),
    "minecraft:badlands": ("Badlands", "Пустошь"),
    "minecraft:eroded_badlands": ("Eroded Badlands", "Выветренная пустошь"),
    "minecraft:wooded_badlands": ("Wooded Badlands", "Лесистая пустошь"),
    "minecraft:meadow": ("Meadow", "Луг"),
    "minecraft:cherry_grove": ("Cherry Grove", "Вишнёвая роща"),
    "minecraft:grove": ("Grove", "Роща"),
    "minecraft:snowy_slopes": ("Snowy Slopes", "Заснеженные склоны"),
    "minecraft:frozen_peaks": ("Frozen Peaks", "Замёрзшие пики"),
    "minecraft:jagged_peaks": ("Jagged Peaks", "Острые пики"),
    "minecraft:stony_peaks": ("Stony Peaks", "Каменистые пики"),
    "minecraft:river": ("River", "Река"),
    "minecraft:frozen_river": ("Frozen River", "Замёрзшая река"),
    "minecraft:beach": ("Beach", "Пляж"),
    "minecraft:snowy_beach": ("Snowy Beach", "Снежный пляж"),
    "minecraft:stony_shore": ("Stony Shore", "Каменистый берег"),
    "minecraft:ocean": ("Ocean", "Океан"),
    "minecraft:deep_ocean": ("Deep Ocean", "Глубокий океан"),
    "minecraft:warm_ocean": ("Warm Ocean", "Тёплый океан"),
    "minecraft:lukewarm_ocean": ("Lukewarm Ocean", "Тепловатый океан"),
    "minecraft:deep_lukewarm_ocean": ("Deep Lukewarm Ocean", "Глубокий тепловатый океан"),
    "minecraft:cold_ocean": ("Cold Ocean", "Холодный океан"),
    "minecraft:deep_cold_ocean": ("Deep Cold Ocean", "Глубокий холодный океан"),
    "minecraft:frozen_ocean": ("Frozen Ocean", "Замёрзший океан"),
    "minecraft:deep_frozen_ocean": ("Deep Frozen Ocean", "Глубокий замёрзший океан"),
    "minecraft:mushroom_fields": ("Mushroom Fields", "Грибные поля"),
    "minecraft:dripstone_caves": ("Dripstone Caves", "Пещеры капельника"),
    "minecraft:lush_caves": ("Lush Caves", "Пышные пещеры"),
    "minecraft:deep_dark": ("Deep Dark", "Древние недра"),
    "minecraft:pale_garden": ("Pale Garden", "Бледный сад"),
    "minecraft:nether_wastes": ("Nether Wastes", "Пустоши Незера"),
    "minecraft:soul_sand_valley": ("Soul Sand Valley", "Долина песка душ"),
    "minecraft:crimson_forest": ("Crimson Forest", "Багровый лес"),
    "minecraft:warped_forest": ("Warped Forest", "Искажённый лес"),
    "minecraft:basalt_deltas": ("Basalt Deltas", "Базальтовые дельты"),
    "minecraft:the_end": ("The End", "Край"),
    "minecraft:end_highlands": ("End Highlands", "Высоты Края"),
    "minecraft:end_midlands": ("End Midlands", "Средние земли Края"),
    "minecraft:end_barrens": ("End Barrens", "Пустоши Края"),
    "minecraft:small_end_islands": ("Small End Islands", "Малые острова Края"),
    "minecraft:the_void": ("The Void", "Пустота"),
}


def biome_labels(biome_id: str) -> tuple[str, str]:
    known = LABELS.get(biome_id)
    if known:
        return known
    pretty = biome_id.split(":")[-1].replace("_", " ").strip().title() or biome_id
    return pretty, pretty


def spread_spots(points: list[dict], cap: int = 8, gap: int = 2048) -> list[dict]:
    ordered = sorted(points, key=lambda item: (item["x"], item["z"], item["id"]))
    kept: list[dict] = []
    gap2 = gap * gap
    for point in ordered:
        if all((point["x"] - old["x"]) ** 2 + (point["z"] - old["z"]) ** 2 >= gap2 for old in kept):
            kept.append(point)
        if len(kept) >= cap:
            break
    return kept or ordered[:1]


def biome_matches(biome_id: str, needle: str) -> bool:
    if not needle:
        return True
    english, russian = biome_labels(biome_id)
    haystack = f"{biome_id} {english} {russian}".casefold()
    return needle.casefold() in haystack


def filter_biomes(dimensions: list[dict], *, dimension: str, query: str, limit: int) -> list[dict]:
    found = []
    for item in dimensions:
        if dimension and item.get("id") != dimension:
            continue
        for spot in item.get("biomes") or []:
            biome_id = spot.get("id") or ""
            if not biome_matches(biome_id, query):
                continue
            english, russian = biome_labels(biome_id)
            found.append(
                {
                    "dimension": item.get("id") or "",
                    "id": biome_id,
                    "en": english,
                    "ru": russian,
                    "x": spot["x"],
                    "z": spot["z"],
                }
            )
            if len(found) >= limit:
                return found
    return found


def sample_grid(names: list[str], grid: bytes, x: int, z: int, rx: int, rz: int) -> str:
    if len(grid) != 256 * 256:
        return ""
    local_x = x - rx * 512
    local_z = z - rz * 512
    if not (0 <= local_x < 512 and 0 <= local_z < 512):
        return ""
    value = grid[(local_z // 2) * 256 + (local_x // 2)]
    if not value or value > len(names):
        return ""
    return names[value - 1]
