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
        name_field = entry.get("name", "")
        
        if isinstance(name_field, dict):
            # Extract aliases and hidden from inside 'name' if they were accidentally nested
            aliases = name_field.pop("aliases", entry.get("aliases", []))
            is_hidden = name_field.pop("hidden", entry.get("hidden", False))
            
            canonical_name = name_field.get("en")
            if not canonical_name:
                canonical_name = str(next(iter(name_field.values()))) if name_field else ""
                
            i18n_dict = name_field
        else:
            aliases = entry.get("aliases", [])
            is_hidden = entry.get("hidden", False)
            
            canonical_name = str(name_field)
            i18n_dict = {"en": canonical_name}

        if not isinstance(aliases, list):
            aliases = []
            
        lower_aliases = [str(a).lower() for a in aliases]
        is_hidden = bool(is_hidden) or "age" in lower_aliases or "location" in lower_aliases

        tags.append(Tag(
            name=canonical_name,
            aliases=[str(a) for a in aliases],
            hidden=bool(is_hidden),
            i18n=i18n_dict
        ))
    return tags