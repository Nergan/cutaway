import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_bestiary_records_name_a_source_and_keep_derived_tiers_out_of_the_file():
    creatures = json.loads((ROOT / "dnd" / "static" / "db.json").read_text(encoding="utf-8"))
    assert creatures
    names = [creature["n_en"] for creature in creatures]
    assert len(names) == len(set(names))
    for creature in creatures:
        assert isinstance(creature["fam"], bool)
        assert creature["src"] and creature["src_ru"]
        assert "cat" not in creature
        for speed in creature["sp"].values():
            assert speed >= 0


def test_foundry_and_bestiary_rules_agree_with_the_browser_scripts():
    node = shutil.which("node")
    assert node, "node is required to check the browser scripts"
    completed = subprocess.run(
        [node, str(ROOT / "tests" / "dnd_logic.test.cjs")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
