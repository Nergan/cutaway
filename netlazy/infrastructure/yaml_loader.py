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
        
        name_field = entry.get("name", "")
        if isinstance(name_field, dict):
            canonical_name = name_field.get("en", str(name_field))
            i18n_dict = name_field
        else:
            canonical_name = str(name_field)
            i18n_dict = {"en": canonical_name}

        tags.append(Tag(
            name=canonical_name,
            aliases=aliases,
            hidden=is_hidden,
            i18n=i18n_dict
        ))
    return tags