from typing import List
from netlazy.domain.models import Tag
from netlazy.domain.repository import TagRepository
from netlazy.infrastructure.yaml_loader import load_tags_from_yaml

class TagService:
    def __init__(self, tag_repo: TagRepository):
        self._tag_repo = tag_repo

    async def sync_from_yaml(self, yaml_path: str) -> int:
        tags = load_tags_from_yaml(yaml_path)
        if tags:
            await self._tag_repo.sync(tags)
        return len(tags)

    async def browse(self) -> List[Tag]:
        return await self._tag_repo.get_all_tags()

    async def search(self, query: str) -> List[Tag]:
        return await self._tag_repo.search(query)