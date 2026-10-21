from __future__ import annotations

import json
from pathlib import Path

from pumpgrok.tools.desk._memory import MemoryBank


def test_corrupt_line_is_skipped_and_counted(tmp_path: Path) -> None:
    path = tmp_path / "memory.jsonl"
    valid_a = {"id": "a1", "key": "ka", "content": "alpha"}
    valid_b = {"id": "b2", "key": "kb", "content": "bravo"}
    path.write_text(
        json.dumps(valid_a) + "\n{not json\n" + json.dumps(valid_b) + "\n", encoding="utf-8"
    )

    bank = MemoryBank(path)

    assert bank.corrupt_lines == 1
    contents = [hit["content"] for hit in bank.recall("", 10)]
    assert sorted(contents) == ["alpha", "bravo"]


def test_retain_after_torn_final_line_keeps_new_record(tmp_path: Path) -> None:
    path = tmp_path / "memory.jsonl"
    path.write_text('{"id": "a1", "key": "ka", "content": "alpha"}\n{"id": "x', encoding="utf-8")

    bank = MemoryBank(path)
    assert bank.corrupt_lines == 1
    bank.retain(key="kc", record={"content": "charlie"})

    reloaded = MemoryBank(path)
    assert reloaded.corrupt_lines == 1
    contents = sorted(hit["content"] for hit in reloaded.recall("", 10))
    assert contents == ["alpha", "charlie"]
