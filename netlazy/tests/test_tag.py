from pathlib import Path

import pytest
from unittest.mock import AsyncMock, MagicMock
from netlazy.application.tag_service import TagService
from netlazy.domain.models import Tag
from netlazy.domain.tag_text import label_hits
from netlazy.infrastructure.yaml_loader import YamlTagLoader


@pytest.fixture
def tag_deps():
    return {
        "tag_repo": AsyncMock(),
        "tag_loader": MagicMock()
    }


@pytest.fixture
def tag_service(tag_deps):
    return TagService(**tag_deps)


@pytest.mark.asyncio
async def test_tag_service_sync_and_search(tag_service, tag_deps):
    mock_tags = [
        Tag(name="python", aliases=["py", "django"], hidden=False, i18n={"ru": "питон"}),
        Tag(name="music", aliases=["rock"], hidden=False, i18n={"en": "music"})
    ]
    tag_deps["tag_loader"].load_tags.return_value = mock_tags
    tag_deps["tag_repo"].search.return_value = [mock_tags[0]]

    # Test sync delegation
    count = await tag_service.sync_from_yaml("tags.yaml")
    assert count == 2
    tag_deps["tag_repo"].sync.assert_called_once()

    # Test search delegation
    results = await tag_service.search("py")
    assert len(results) == 1
    assert results[0].name == "python"
    tag_deps["tag_repo"].search.assert_called_once_with("py")


def test_added_tags_are_localized_and_visible():
    path = Path(__file__).resolve().parents[1] / "tags.yaml"
    tags = {tag.name: tag for tag in YamlTagLoader().load_tags(str(path))}
    expected = {
        "photography": "фотография",
        "hiking": "походы",
        "cats": "кошки",
        "dogs": "собаки",
        "coffee": "кофе",
        "cycling": "велосипед",
        "swimming": "плавание",
        "yoga": "йога",
        "job": "работа",
        "startapp": "стартап",
        "hr": "эйчар",
        "ai": "ии",
        "employer": "работодатель",
        "candidate": "кандидат",
        "unpaid": "без оплаты",
        "free": "бесплатно",
    }
    for name, russian in expected.items():
        tag = tags[name]
        assert tag.hidden is False
        assert tag.i18n["ru"] == russian
        assert tag.i18n["en"] == name
        assert tag.i18n["pt"]
        assert tag.i18n["zh"]
        assert tag.i18n["ja"]
        assert tag.i18n["ko"]
        assert len(tag.aliases) >= 3
        assert tag.desc["en"]
        assert tag.desc["ru"]


def test_compound_aliases_and_search_only_facets():
    path = Path(__file__).resolve().parents[1] / "tags.yaml"
    loaded = YamlTagLoader().load_tags(str(path))
    names = [tag.name for tag in loaded]
    assert len(names) == len(set(names))
    tags = {tag.name: tag for tag in loaded}

    def names_for(query):
        found = []
        for term in query.split():
            for tag in tags.values():
                labels = [tag.name, *tag.aliases, *tag.i18n.values()]
                if any(label_hits(label, term) for label in labels) and tag.name not in found:
                    found.append(tag.name)
        return found

    assert tags["cute"].hidden is False
    assert tags["switch"].hidden is True
    assert "fetish" in {alias.lower() for alias in tags["switch"].aliases}
    assert "location" in {alias.lower() for alias in tags["moscow"].aliases}
    assert tags["moscow"].hidden is True
    assert tags["18 years old"].hidden is True
    fetish = names_for("fetish")
    assert "submissive" in fetish
    assert "foot fetish" in fetish
    assert "mommy fetish" in fetish
    assert "daddy fetish" in fetish
    assert "roleplay (fetish)" in fetish
    assert len(fetish) <= 40
    assert tags["foot fetish"].hidden is True
    assert tags["foot fetish"].i18n["ru"] == "футфетиш"
    assert "dild" not in {alias.lower() for alias in tags["daddy fetish"].aliases}
    assert "femdom" in {alias.lower() for alias in tags["girl"].aliases}
    assert "femdom" in {alias.lower() for alias in tags["dominant"].aliases}
    assert "kitten" in {alias.lower() for alias in tags["cats"].aliases}
    assert "angel" in {alias.lower() for alias in tags["cute"].aliases}
    princess = names_for("princess kitten angel")
    assert "girl" in princess
    assert "cats" in princess
    assert "cute" in princess
    assert "los angeles" not in princess
    assert label_hits("femdom", "fem")
    assert label_hits("soft femdom", "femdom") is False
    assert label_hits("los angeles", "angel") is False
    femdom = names_for("femdom")
    assert "girl" in femdom and "dominant" in femdom and "soft" not in femdom
    assert tags["krasnoyarsk"].desc["ru"] == "находится в красноярке"
    assert tags["24 years old"].desc["ru"] == "24 года"
    assert tags["21 years old"].desc["ru"] == "21 год"
    assert tags["22 years old"].desc["ru"] == "22 года"
    assert tags["25 years old"].desc["ru"] == "25 лет"
    assert tags["3d modeling"].desc["ru"] == "интересуется 3d моделированием"
    assert tags["authentic germanic myths"].desc["ru"] == "нравятся германские мифы"
    assert tags["belly inflation"].desc["ru"] == "есть фетиш на наполнение живота"
    assert tags["english (native/fluent)"].desc["ru"] == "говорит на английском"
    for tag in tags.values():
        ru = tag.desc["ru"]
        en = tag.desc["en"]
        assert ru and en
        assert ru == ru.lower() and en == en.lower()
        assert not ru.endswith(".") and not en.endswith(".")
        assert "облако" not in ru and "tag cloud" not in en