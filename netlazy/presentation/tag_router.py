from typing import List
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from netlazy.presentation.dependencies import tag_service

router = APIRouter(prefix="/tags", tags=["Tags"])

class TagResponse(BaseModel):
    name: str
    aliases: List[str] = Field(default_factory=list)
    hidden: bool = False
    i18n: dict = Field(default_factory=dict)

@router.get("/search", response_model=List[TagResponse])
async def search_tags(
    q: str = Query("", description="Search text.")
):
    if q.strip() == "":
        tags = await tag_service.browse()
    else:
        tags = await tag_service.search(q)
    return [TagResponse(name=t.name, aliases=t.aliases, hidden=t.hidden, i18n=t.i18n) for t in tags]