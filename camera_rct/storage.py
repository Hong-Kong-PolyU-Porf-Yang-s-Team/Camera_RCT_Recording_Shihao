"""Validated, atomic JSON storage for operator selections."""

import json
import os
import tempfile
from pathlib import Path


def validate_selection(value):
    if not isinstance(value, dict):
        raise ValueError("选择必须是 JSON 对象 / Selection must be an object")
    number = value.get("number")
    if type(number) is not int or not 1 <= number <= 9999:
        raise ValueError("编号范围为 0001–9999 / Number must be 1–9999")
    if value.get("group") not in ("I", "C"):
        raise ValueError("组别必须是 I 或 C / Group must be I or C")
    if type(value.get("visit")) is not int or value["visit"] not in (1, 2):
        raise ValueError("选项必须是 1 或 2 / Visit must be 1 or 2")
    return {"number": number, "group": value["group"], "visit": value["visit"]}


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=".state-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class SelectionStore:
    def __init__(self, path):
        self.path = Path(path)
        if self.path.exists():
            with self.path.open(encoding="utf-8") as stream:
                self.value = validate_selection(json.load(stream))
        else:
            self.value = {"number": 1, "group": "I", "visit": 1}
            write_json(self.path, self.value)

    def save(self, value):
        validated = validate_selection(value)
        write_json(self.path, validated)
        self.value = validated
