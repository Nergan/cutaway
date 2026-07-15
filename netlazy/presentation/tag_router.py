from typing import List
from fastapi import APIRouter, Query
from pydantic import BaseModel
from netlazy.presentation.dependencies import tag_service

router = APIRouter(prefix="/tags", tags=["Tags"])

class TagResponse(BaseModel):
    name: str
    aliases: List[str] = []
    hidden: bool = False
    i18n: dict = {}

@router.get("/search", response_model=List[TagResponse])
async def search_tags(
    q: str = Query("", description="Search text.")
):
    if q.strip() == "":
        tags = await tag_service.browse()
    else:
        tags = await tag_service.search(q)
    return [TagResponse(name=t.name, aliases=t.aliases, hidden=t.hidden, i18n=t.i18n) for t in tags]