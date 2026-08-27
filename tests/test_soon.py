from soon.soon import apply_op, claim_name, normalize_room, sniff_mime, validate_object


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8


def test_normalize_room_defaults_and_rejects_paths():
    assert normalize_room(None) == "board"
    assert normalize_room("My-Room_1") == "my-room_1"
    try:
        normalize_room("../etc")
        assert False, "expected invalid room"
    except ValueError:
        pass


def test_validate_stroke_and_reject_javascript_link():
    stroke = validate_object(
        {
            "id": "abcd1234efgh",
            "type": "stroke",
            "points": [[0, 0], [4, 6]],
            "color": "#D4A373",
            "width": 3,
            "z": 1,
        }
    )
    assert stroke["color"] == "#d4a373"
    assert stroke["points"][1] == [4.0, 6.0]
    assert stroke["alpha"] == 1.0

    faded = validate_object(
        {
            "id": "abcd1234efgh",
            "type": "stroke",
            "points": [[0, 0], [4, 6]],
            "color": "rgba(212, 163, 115, 0.4)",
            "width": 3,
            "alpha": 0,
            "z": 1,
        }
    )
    assert faded["color"] == "#d4a373"
    assert faded["alpha"] == 0.0

    try:
        validate_object(
            {
                "id": "abcd1234efgh",
                "type": "link",
                "x": 0,
                "y": 0,
                "w": 200,
                "h": 64,
                "url": "https://javascript:alert(1)",
                "z": 1,
            }
        )
        assert False, "expected rejected link"
    except ValueError:
        pass


def test_apply_op_add_update_delete_and_board_cap():
    store = {}
    added = apply_op(
        store,
        {
            "op": "add",
            "object": {
                "id": "abcd1234efgh",
                "type": "text",
                "x": 1,
                "y": 2,
                "text": "hello",
                "color": "#e5e1db",
                "size": 18,
                "z": 1,
            },
        },
    )
    assert added["object"]["text"] == "hello"
    assert "abcd1234efgh" in store

    apply_op(
        store,
        {
            "op": "update",
            "object": {
                "id": "abcd1234efgh",
                "type": "text",
                "x": 8,
                "y": 2,
                "text": "there",
                "color": "#e5e1db",
                "size": 18,
                "z": 2,
            },
        },
    )
    assert store["abcd1234efgh"]["text"] == "there"

    apply_op(store, {"op": "delete", "id": "abcd1234efgh"})
    assert store == {}


def test_claim_name_rejects_duplicates_and_short_values():
    presence = {"a": {"name": "Рыжий-лис"}}
    assert claim_name(presence, "a", "рыжий-лис") == "рыжий-лис"
    try:
        claim_name(presence, "b", "рыжий-лис")
        assert False, "expected taken name"
    except ValueError:
        pass
    try:
        claim_name(presence, "b", "x")
        assert False, "expected short name"
    except ValueError:
        pass
    assert claim_name(presence, "b", "Новый-мох") == "Новый-мох"


def test_sniff_png_and_reject_html():
    assert sniff_mime(PNG) == "image/png"
    assert sniff_mime(b"<html>not a file</html>") is None
