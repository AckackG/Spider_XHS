#!/usr/bin/env python3
"""Trim Xiaohongshu raw JSONL records to text-only note and author reply threads.

The script reads JSONL line by line and writes JSONL line by line, so it can be
used for large raw exports without loading the whole file into memory.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from myscripts.config import DEFAULT_AUTHOR_NICKNAME, FINAL_JSONL_PATH, RAW_JSONL_PATH


def compact_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def pick_time(item: dict[str, Any], text_key: str, raw_key: str) -> Any:
    text_value = item.get(text_key)
    if text_value not in (None, ""):
        return text_value
    return item.get(raw_key, "")


def trim_message(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "用户名": compact_text(item.get("nickname")),
        "内容": compact_text(item.get("content")),
        "时间": pick_time(item, "create_time_text", "create_time"),
    }


def has_author_message(thread: Iterable[dict[str, Any]], author_nickname: str) -> bool:
    return any(compact_text(message.get("nickname")) == author_nickname for message in thread)


def trim_reply_threads(
    comments: Any,
    author_nickname: str,
) -> list[list[dict[str, Any]]]:
    if not isinstance(comments, list):
        return []

    threads: list[list[dict[str, Any]]] = []
    for comment in comments:
        if not isinstance(comment, dict):
            continue

        replies = comment.get("replies", [])
        if not isinstance(replies, list):
            replies = []

        thread = [comment]
        thread.extend(reply for reply in replies if isinstance(reply, dict))
        if has_author_message(thread, author_nickname):
            threads.append([trim_message(message) for message in thread])

    return threads


def trim_note(record: dict[str, Any], author_nickname: str) -> dict[str, Any]:
    return {
        "标题": compact_text(record.get("title")),
        "内容": compact_text(record.get("content")),
        "发布时间": pick_time(record, "publish_time_text", "publish_time"),
        "回复串": trim_reply_threads(record.get("comments"), author_nickname),
    }


def parse_publish_time(value: Any) -> float:
    if value in (None, ""):
        return 0

    if isinstance(value, (int, float)):
        timestamp = float(value)
        return timestamp / 1000 if timestamp > 10_000_000_000 else timestamp

    text = compact_text(value)
    if not text:
        return 0

    try:
        timestamp = float(text)
        return timestamp / 1000 if timestamp > 10_000_000_000 else timestamp
    except ValueError:
        pass

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).timestamp()
        except ValueError:
            continue

    return 0


def iter_trimmed_records(input_path: Path, author_nickname: str) -> Iterable[dict[str, Any]]:
    with input_path.open("r", encoding="utf-8") as input_file:
        for line_number, line in enumerate(input_file, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{input_path}:{line_number} is not valid JSON: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"{input_path}:{line_number} must contain a JSON object")
            yield trim_note(record, author_nickname)


def write_trimmed_jsonl(
    input_path: Path,
    output_path: Path,
    author_nickname: str,
) -> int:
    records = list(iter_trimmed_records(input_path, author_nickname))
    records.sort(key=lambda record: parse_publish_time(record.get("发布时间")), reverse=True)

    with output_path.open("w", encoding="utf-8", newline="\n") as output_file:
        for trimmed in records:
            output_file.write(json.dumps(trimmed, ensure_ascii=False, separators=(",", ":")))
            output_file.write("\n")
    return len(records)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Trim Xiaohongshu raw JSONL to title, content, publish time, "
            "and reply threads containing the given author."
        )
    )
    parser.add_argument(
        "input",
        nargs="?",
        default=RAW_JSONL_PATH,
        type=Path,
        help=f"Path to the raw JSONL file. Default: {RAW_JSONL_PATH}.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output JSONL path. Default: raw_trim.jsonl.",
    )
    parser.add_argument(
        "--author",
        default=DEFAULT_AUTHOR_NICKNAME,
        help=f"Author nickname that must appear in a reply thread. Default: {DEFAULT_AUTHOR_NICKNAME}.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = args.input
    output_path = args.output or FINAL_JSONL_PATH

    if not input_path.exists():
        print(f"Input file not found: {input_path}", file=sys.stderr)
        return 1
    if input_path.resolve() == output_path.resolve():
        print("Output path must be different from input path.", file=sys.stderr)
        return 1
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        count = write_trimmed_jsonl(input_path, output_path, args.author)
    except (OSError, ValueError) as exc:
        print(f"Failed to trim JSONL: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {count} records to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
