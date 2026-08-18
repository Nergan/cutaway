import os
import hashlib
from typing import List
from netlazy.domain.models import Tag
from netlazy.domain.repository import TagRepository, TagLoaderPort

class TagService:
    def __init__(self, tag_repo: TagRepository, tag_loader: TagLoaderPort):
        self._tag_repo = tag_repo
        self._tag_loader = tag_loader

    async def sync_from_yaml(self, yaml_path: str) -> int:
        file_hash = None
        if os.path.exists(yaml_path):
            with open(yaml_path, 'rb') as f:
                file_hash = hashlib.md5(f.read()).hexdigest()

        tags = self._tag_loader.load_tags(yaml_path)
        
        # FIX: Directly invoke the standard interface without brittle reflection heuristics (Issue 12)
        await self._tag_repo.sync(tags, file_hash=file_hash)
            
        return len(tags)

    async def browse(self) -> List[Tag]:
        return await self._tag_repo.get_all_tags()

    async def search(self, query: str) -> List[Tag]:
        return await self._tag_repo.search(query)