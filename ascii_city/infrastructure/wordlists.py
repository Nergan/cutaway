"""Word lists for server-issued nicknames.

Kept short on purpose: an adjective of at most nine characters plus a noun of at
most eight plus a five-character numeric suffix always lands inside the 6 to 24
character window the specification requires.
"""

from __future__ import annotations

ADJECTIVES: tuple[str, ...] = (
    "Quiet", "Amber", "Neon", "Velvet", "Hollow", "Crimson", "Silent", "Lucid",
    "Static", "Copper", "Frayed", "Glossy", "Muted", "Rusted", "Solar", "Vivid",
    "Chrome", "Dusty", "Ember", "Frozen", "Gilded", "Hazy", "Idle", "Jaded",
    "Keen", "Lunar", "Mellow", "Nimble", "Opal", "Pale", "Quartz", "Restless",
    "Sable", "Tidal", "Umber", "Vagrant", "Wired", "Xenon", "Yonder", "Zealous",
    "Bitter", "Cobalt", "Dapper", "Errant", "Feral", "Grim", "Husky", "Inky",
    "Jolted", "Kindred", "Lofty", "Mirrored", "Nocturne", "Ochre", "Prism", "Quill",
    "Raw", "Slate", "Tacit", "Uneven", "Violet", "Woven", "Yielding", "Zinc",
)

NOUNS: tuple[str, ...] = (
    "Fox", "Ghost", "Otter", "Heron", "Lynx", "Moth", "Raven", "Shark",
    "Toad", "Viper", "Wren", "Yak", "Bison", "Crane", "Drake", "Eel",
    "Falcon", "Gecko", "Hawk", "Ibis", "Jackal", "Kite", "Lark", "Marten",
    "Newt", "Osprey", "Puffin", "Quail", "Rook", "Stoat", "Tapir", "Urchin",
    "Vole", "Walrus", "Xerus", "Yeti", "Zebu", "Anchor", "Beacon", "Cinder",
    "Dial", "Echo", "Filament", "Grid", "Halo", "Ingot", "Jetty", "Kiosk",
    "Lantern", "Marquee", "Nomad", "Obelisk", "Pylon", "Quarry", "Relay", "Signal",
    "Turbine", "Usher", "Vault", "Wharf", "Xylem", "Yardarm", "Zephyr", "Alley",
)

assert all(len(word) <= 9 for word in ADJECTIVES)
assert all(len(word) <= 8 for word in NOUNS)
