from pathlib import Path
from typing import List
import yaml
from netlazy.domain.models import Tag

def load_tags_from_yaml(path: str) -> List[Tag]:
    file_path = Path(path)
    if not file_path.exists():
        return []

    with open(file_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    tags = []
    for entry in raw.get("tags", []):
        aliases = entry.get("aliases", [])
        is_hidden = entry.get("hidden", False) or "age" in aliases or "location" in aliases
        tags.append(Tag(
            name=entry["name"],
            aliases=aliases,
            hidden=is_hidden,
        ))
    return tags