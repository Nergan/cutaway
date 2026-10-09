"""Conversion graph and the path chosen for a requested format.

Speech hops sit in the same graph as ordinary conversions. Their weight matches
one normal hop: a heavier speech hop would lose to a long detour through a
picture (video → image → pdf → text), and a lighter one would replace a direct
media conversion with a transcript that is read aloud again.
"""

from __future__ import annotations

import heapq

TRANSCRIBE_SOURCES = frozenset({"mp3", "wav", "ogg", "mp4", "webm"})
SPEAK_TARGETS = ("mp3", "wav", "ogg")
MEDIA = frozenset({"mp3", "wav", "ogg", "mp4", "webm", "gif"})

DIRECT_EDGES = {
    "docx": ["pdf", "html", "txt", "md"],
    "doc": ["pdf", "docx"],
    "pptx": ["pdf"],
    "rtf": ["pdf", "docx", "html", "txt", "md"],
    "odt": ["pdf", "docx"],
    "txt": ["pdf", "html", "md", "docx", "json"],
    "html": ["pdf", "md", "txt", "docx"],
    "md": ["html", "txt", "docx"],
    "epub": ["html", "txt", "md"],
    "pdf": ["html", "txt"],
    "djvu": ["pdf"],
    "csv": ["pdf"],
    "xlsx": ["csv", "pdf"],
    "svg": ["png", "pdf"],
    "jpg": ["png", "webp", "pdf"],
    "png": ["jpg", "webp", "pdf"],
    "webp": ["jpg", "png", "pdf"],
    "gif": ["png", "mp4"],
    "mp4": ["webm", "gif", "mp3", "ogg"],
    "webm": ["mp4", "gif", "mp3", "ogg"],
    "mp3": ["wav", "ogg", "mp4", "webm"],
    "wav": ["mp3", "ogg", "mp4", "webm"],
    "ogg": ["mp3", "wav", "mp4", "webm"],
    "zip": ["7z", "tar", "gz"],
    "rar": ["zip", "7z", "tar", "gz"],
    "7z": ["zip", "tar", "gz"],
    "tar": ["zip", "7z", "gz"],
    "gz": ["zip", "7z", "tar"],
    "json": ["yaml", "toml", "xml", "txt"],
    "yaml": ["json", "toml", "xml", "txt"],
    "toml": ["json", "yaml", "xml", "txt"],
    "xml": ["json", "yaml", "toml", "txt"],
}

# What the page already offered before speech was added to the path search.
BASE_TARGETS = {
    "docx": ["pdf", "html", "txt", "md"],
    "doc": ["pdf", "html", "txt", "md"],
    "pptx": ["pdf", "html", "txt", "md", "xml"],
    "pdf": ["html", "txt", "md"],
    "html": ["pdf", "md", "txt", "xml"],
    "md": ["pdf", "html", "txt"],
    "txt": ["pdf", "html", "md", "json", "yaml", "toml", "xml", "mp3", "wav", "ogg"],
    "rtf": ["pdf", "html", "txt", "md"],
    "odt": ["pdf", "html", "txt", "md"],
    "epub": ["pdf", "html", "txt", "md"],
    "djvu": ["pdf", "html", "txt", "md"],
    "json": ["yaml", "toml", "xml", "md", "txt", "html", "pdf"],
    "yaml": ["json", "toml", "xml", "md", "txt", "html", "pdf"],
    "toml": ["json", "yaml", "xml", "md", "txt", "html", "pdf"],
    "xml": ["json", "yaml", "toml", "md", "txt", "html", "pdf"],
    "jpg": ["jpg", "png", "webp", "pdf"],
    "png": ["png", "jpg", "webp", "pdf"],
    "webp": ["webp", "jpg", "png", "pdf"],
    "svg": ["png", "jpg", "pdf"],
    "gif": ["gif", "mp4", "png"],
    "mp3": ["mp3", "wav", "ogg", "mp4", "webm", "txt"],
    "wav": ["wav", "mp3", "ogg", "mp4", "webm", "txt"],
    "ogg": ["ogg", "mp3", "wav", "mp4", "webm", "txt"],
    "mp4": ["mp4", "webm", "gif", "mp3", "ogg", "txt"],
    "webm": ["webm", "mp4", "gif", "mp3", "ogg", "txt"],
    "csv": ["pdf"],
    "xlsx": ["csv", "pdf"],
    "zip": ["7z", "tar", "gz"],
    "rar": ["zip", "7z", "tar", "gz"],
    "7z": ["zip", "tar", "gz"],
    "tar": ["zip", "7z", "gz"],
    "gz": ["zip", "7z", "tar"],
}


def hop_kind(source: str, target: str) -> str | None:
    """Atomic speech hop. Ordinary edges stay in DIRECT_EDGES and are not speech."""
    direct = DIRECT_EDGES.get(source, ())
    if source in TRANSCRIBE_SOURCES and target == "txt" and target not in direct:
        return "transcribe"
    if source == "txt" and target in SPEAK_TARGETS and target not in direct:
        return "speak"
    return None


def _neighbors(node: str, *, speak: bool, transcribe: bool):
    for target in DIRECT_EDGES.get(node, ()):
        yield target, 1, None
    if transcribe and node in TRANSCRIBE_SOURCES and "txt" not in DIRECT_EDGES.get(node, ()):
        yield "txt", 1, "transcribe"
    if speak and node == "txt":
        direct = DIRECT_EDGES.get(node, ())
        for target in SPEAK_TARGETS:
            if target not in direct:
                yield target, 1, "speak"


def _dijkstra(start: str, end: str, *, speak: bool, transcribe: bool):
    """Dijkstra. Equal cost keeps the path with fewer speech hops."""
    if start == end:
        return [start]
    counter = 0
    heap = [(0, 0, counter, start, [start])]
    seen: set[str] = set()
    while heap:
        cost, speech_hops, _, node, path = heapq.heappop(heap)
        if node in seen:
            continue
        seen.add(node)
        if node == end:
            return path
        for target, weight, operation in _neighbors(node, speak=speak, transcribe=transcribe):
            if target in seen:
                continue
            counter += 1
            heapq.heappush(
                heap,
                (
                    cost + weight,
                    speech_hops + (1 if operation else 0),
                    counter,
                    target,
                    path + [target],
                ),
            )
    return None


def _nodes_from(start: str, *, speak: bool, transcribe: bool) -> set[str]:
    seen = {start}
    queue = [start]
    while queue:
        node = queue.pop(0)
        for target, _weight, _operation in _neighbors(node, speak=speak, transcribe=transcribe):
            if target in seen:
                continue
            seen.add(target)
            queue.append(target)
    return seen


def _text_documents() -> set[str]:
    return (set(text_products()) - set(SPEAK_TARGETS)) | {"txt"}


def _via_transcript(start: str, end: str):
    """Shortest path that recognizes speech before producing a text format.

    A gif can also become a pdf by extracting a frame. That picture is not a
    transcript, so a text target from media goes through recognition even when
    the picture path is shorter.
    """
    best = None
    plain = _nodes_from(start, speak=False, transcribe=False)
    sources = [node for node in plain if node in TRANSCRIBE_SOURCES]
    for mid in sources:
        left = [start] if start == mid else _dijkstra(start, mid, speak=False, transcribe=False)
        right = ["txt"] if end == "txt" else _dijkstra("txt", end, speak=False, transcribe=False)
        if not left or not right:
            continue
        path = left + ["txt"] + right[1:]
        rank = (len(path), path)
        if best is None or rank < best[0]:
            best = (rank, path)
    return None if best is None else best[1]


def find_shortest_path(start: str, end: str, *, speak: bool = True, transcribe: bool = True):
    if start == end:
        return [start]
    # Media can also reach a document by turning a frame into a picture.
    # A text target from that media is a transcript, so recognition wins.
    if (
        speak
        and transcribe
        and start != "txt"
        and end in _text_documents()
        and _reaches_media(start)
    ):
        forced = _via_transcript(start, end)
        if forced:
            return forced
    return _dijkstra(start, end, speak=speak, transcribe=transcribe)


def _reaches(start: str, goal: str, *, speak: bool, transcribe: bool) -> bool:
    if start == goal:
        return True
    return find_shortest_path(start, goal, speak=speak, transcribe=transcribe) is not None


def text_products() -> list[str]:
    """Formats txt can become, including speech, without wrapping that audio as video."""
    products: list[str] = []
    seen = {"txt"}
    queue = ["txt"]
    while queue:
        node = queue.pop(0)
        if node in MEDIA:
            continue
        for target, _weight, _operation in _neighbors(node, speak=True, transcribe=False):
            if target in seen:
                continue
            seen.add(target)
            products.append(target)
            queue.append(target)
    return products


def _reaches_media(fmt: str) -> bool:
    if fmt in MEDIA:
        return True
    return any(
        _reaches(fmt, media, speak=False, transcribe=False)
        for media in MEDIA
    )


def targets_for(fmt: str) -> list[str]:
    """Formats offered for a file.

    A format that can become text can also be spoken. A format that can become
    audio or video can be transcribed and then turned into anything text can
    become. Targets already offered stay in their previous order.
    """
    chosen = list(BASE_TARGETS.get(fmt, []))
    seen = set(chosen)

    def add(target: str) -> None:
        if not target or target == fmt or target in seen:
            return
        seen.add(target)
        chosen.append(target)

    if _reaches(fmt, "txt", speak=False, transcribe=False):
        for audio in SPEAK_TARGETS:
            add(audio)
    if fmt == "txt" or _reaches_media(fmt):
        add("txt")
        for product in text_products():
            add(product)
    return chosen


def ai_targets_for(fmt: str) -> dict[str, str]:
    """Speech operation on the chosen path: speak, transcribe, or both."""
    marked: dict[str, str] = {}
    for target in targets_for(fmt):
        if target == fmt:
            continue
        path = find_shortest_path(fmt, target)
        if not path:
            continue
        operations = [
            operation
            for operation in (hop_kind(left, right) for left, right in zip(path, path[1:]))
            if operation
        ]
        if not operations:
            continue
        if "speak" in operations and "transcribe" in operations:
            marked[target] = "both"
        else:
            marked[target] = operations[0]
    return marked
