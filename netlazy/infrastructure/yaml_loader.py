from pathlib import Path
from typing import List
import yaml
from netlazy.domain.models import Tag
from netlazy.domain.repository import TagLoaderPort

class YamlTagLoader(TagLoaderPort):
    def load_tags(self, path: str) -> List[Tag]:
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
                desc = name_field.pop("desc", entry.get("desc", {}))
                
                canonical_name = name_field.get("en")
                if not canonical_name:
                    canonical_name = str(next(iter(name_field.values()))) if name_field else ""
                    
                i18n_dict = name_field
            else:
                aliases = entry.get("aliases", [])
                is_hidden = entry.get("hidden", False)
                desc = entry.get("desc", {})
                
                canonical_name = str(name_field)
                i18n_dict = {"en": canonical_name}

            if not isinstance(aliases, list):
                aliases = []
            if not isinstance(desc, dict):
                desc = {"en": str(desc)} if desc else {}
                
            lower_aliases = [str(a).lower() for a in aliases]
            # These three words are sentinels, not ordinary synonyms. A tag that
            # carries one stays out of the cloud and is found only by search.
            is_hidden = bool(is_hidden) or bool({"age", "location", "fetish"} & set(lower_aliases))

            tags.append(Tag(
                name=canonical_name,
                aliases=[str(a) for a in aliases],
                hidden=bool(is_hidden),
                i18n=i18n_dict,
                desc={str(k): str(v) for k, v in desc.items() if v},
            ))
        return tags