import os
import hashlib
import inspect
from typing import List
from netlazy.domain.models import Tag
from netlazy.domain.repository import TagRepository
from netlazy.infrastructure.yaml_loader import load_tags_from_yaml

class TagService:
    def __init__(self, tag_repo: TagRepository):
        self._tag_repo = tag_repo

    async def sync_from_yaml(self, yaml_path: str) -> int:
        file_hash = None
        if os.path.exists(yaml_path):
            with open(yaml_path, 'rb') as f:
                file_hash = hashlib.md5(f.read()).hexdigest()

        tags = load_tags_from_yaml(yaml_path)
        
        # Dynamically check if the repository supports the optimized file_hash check
        sig = inspect.signature(self._tag_repo.sync)
        if 'file_hash' in sig.parameters:
            await self._tag_repo.sync(tags, file_hash=file_hash)
        else:
            await self._tag_repo.sync(tags)
            
        return len(tags)

    async def browse(self) -> List[Tag]:
        return await self._tag_repo.get_all_tags()

    async def search(self, query: str) -> List[Tag]:
        return await self._tag_repo.search(query)