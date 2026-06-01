import json
import random
import sys
import time
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(PROJECT_ROOT))

from apis.xhs_pc_apis import XHS_Apis
from myscripts.config import (
    COOKIE_PATH,
    DATA_DIR,
    DELETION_REPORT_PATH,
    FILTERED_NOTE_SLEEP_MULTIPLIER,
    FORCE_COMMENTS_WITHIN_DAYS,
    LIMIT,
    MAX_RETRY,
    MAX_SLEEP_SECONDS,
    MIN_COMMENT_COUNT,
    MIN_SLEEP_SECONDS,
    MIN_VIEW_COUNT,
    RAW_DATA_DIR,
    RAW_JSONL_PATH,
    RATE_LIMIT_SLEEP_SECONDS,
    REFETCH_COMMENTS_ON_COUNT_CHANGE_WITHIN_DAYS,
    REFETCH_LATEST_NOTE_COMMENTS,
    SKIP_COMMENTS,
    TARGET_URL_PATH,
)


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\r", " ").replace("\n", " ").strip()


def strip_wrapping_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1].strip()
    return value


def read_required_text(path: Path, label: str) -> str:
    if not path.exists():
        raise RuntimeError(f"{label} 文件不存在: {path}")

    lines = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(stripped)

    value = "\n".join(lines).strip()
    if not value:
        raise RuntimeError(f"{label} 为空，请填写: {path}")
    return value


def load_cookie_text() -> str:
    cookie = read_required_text(COOKIE_PATH, "Cookie")
    if cookie.startswith("COOKIES="):
        cookie = cookie.split("=", 1)[1]
    return strip_wrapping_quotes(cookie)


def load_target_user_url() -> str:
    target_url = read_required_text(TARGET_URL_PATH, "用户主页 URL")
    if target_url.startswith("TARGET_USER_URL="):
        target_url = target_url.split("=", 1)[1]
    target_url = strip_wrapping_quotes(target_url)

    if "/user/profile/" not in target_url:
        raise RuntimeError(f"用户主页 URL 格式不正确，请粘贴包含 /user/profile/ 的完整 URL: {TARGET_URL_PATH}")
    if "xsec_token=" not in target_url:
        raise RuntimeError(f"用户主页 URL 缺少 xsec_token，请粘贴登录后浏览器地址栏里的完整 URL: {TARGET_URL_PATH}")

    return target_url


def timestamp_to_datetime_text(value: Any) -> str:
    """
    小红书常见时间戳为 13 位毫秒，也可能出现 10 位秒。
    返回本地时间字符串。
    """
    if value is None or value == "":
        return ""

    try:
        ts = int(value)
    except Exception:
        return clean_text(value)

    if ts <= 0:
        return ""

    if ts > 10_000_000_000:
        ts = ts / 1000

    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
    except Exception:
        return ""


def timestamp_to_sort_value(value: Any) -> float:
    """
    将 10 位秒或 13 位毫秒时间戳转换为可排序值。
    解析失败时返回 0，避免影响主流程。
    """
    if value is None or value == "":
        return 0

    try:
        ts = float(value)
    except Exception:
        return 0

    if ts <= 0:
        return 0

    if ts > 10_000_000_000:
        ts = ts / 1000

    return ts


def first_non_empty(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and value.strip() == "":
            continue
        return value
    return ""


def first_field(mapping: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value is None:
            continue
        if isinstance(value, str) and value.strip() == "":
            continue
        return value
    return ""


def parse_count(value: Any) -> int:
    """
    将 123、"123"、"1,234"、"1.2万"、"1.2w"、"1.2k" 等计数字段转成整数。
    解析失败时返回 0。
    """
    if value is None or value == "":
        return 0

    if isinstance(value, bool):
        return 0

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        return int(value)

    text = clean_text(value).replace(",", "").replace("+", "")
    if not text:
        return 0

    multiplier = 1
    lowered = text.lower()

    if "万" in lowered or "w" in lowered:
        multiplier = 10_000
        lowered = lowered.replace("万", "").replace("w", "")
    elif "千" in lowered or "k" in lowered:
        multiplier = 1_000
        lowered = lowered.replace("千", "").replace("k", "")

    try:
        return int(float(lowered) * multiplier)
    except Exception:
        digits = "".join(ch for ch in text if ch.isdigit())
        return int(digits) if digits else 0


def save_debug_json(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def sleep_jitter(multiplier: float = 1.0) -> None:
    seconds = random.uniform(MIN_SLEEP_SECONDS, MAX_SLEEP_SECONDS) * multiplier
    print(f"  sleep {seconds:.1f}s")
    time.sleep(seconds)


def is_rate_limited(raw: Any, msg: Any = "") -> bool:
    if isinstance(raw, dict):
        if raw.get("code") == 300013:
            return True
        if "访问频繁" in str(raw.get("msg", "")):
            return True

    if "访问频繁" in str(msg):
        return True

    return False


def call_with_backoff(fn: Callable, *args: Any) -> tuple[Any, Any, Any]:
    last_result = (False, "no result", None)

    for attempt in range(1, MAX_RETRY + 1):
        result = fn(*args)
        last_result = result

        if not isinstance(result, tuple) or len(result) != 3:
            return result

        ok, msg, raw = result

        if is_rate_limited(raw, msg):
            wait = RATE_LIMIT_SLEEP_SECONDS * attempt
            print(f"  rate limited: {msg}, sleep {wait}s, retry {attempt}/{MAX_RETRY}")
            time.sleep(wait)
            continue

        return result

    return last_result


def build_note_url(simple_note: dict[str, Any]) -> str:
    note_id = simple_note.get("note_id") or simple_note.get("id")
    xsec_token = simple_note.get("xsec_token", "")

    # 严格参考 cv-cat/Spider_XHS 项目内 spider_user_all_note() 的实现：
    # 不 urlencode，不额外加 xsec_source。
    return f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={xsec_token}"


def extract_note_item(note_raw: dict[str, Any]) -> dict[str, Any] | None:
    data = note_raw.get("data") or {}

    items = data.get("items")
    if isinstance(items, list) and items:
        return items[0]

    if isinstance(data.get("item"), dict):
        return data["item"]

    if isinstance(data.get("note"), dict):
        return data["note"]

    if isinstance(data.get("note_detail"), dict):
        return data["note_detail"]

    if isinstance(data.get("note_card"), dict):
        return data

    return None


def extract_note_fields(item: dict[str, Any]) -> dict[str, Any]:
    note_card = item.get("note_card") or item

    publish_time_raw = (
        note_card.get("time")
        or note_card.get("publish_time")
        or note_card.get("create_time")
        or note_card.get("created_time")
        or item.get("time")
        or item.get("publish_time")
        or item.get("create_time")
    )

    user_info = note_card.get("user") or note_card.get("user_info") or {}
    interact_info = note_card.get("interact_info") or {}

    view_count = first_non_empty(
        first_field(
            interact_info,
            [
                "view_count",
                "view_num",
                "views",
                "read_count",
                "read_num",
                "browse_count",
                "browse_num",
            ],
        ),
        first_field(
            note_card,
            [
                "view_count",
                "view_num",
                "views",
                "read_count",
                "read_num",
                "browse_count",
                "browse_num",
            ],
        ),
        first_field(
            item,
            [
                "view_count",
                "view_num",
                "views",
                "read_count",
                "read_num",
                "browse_count",
                "browse_num",
            ],
        ),
    )

    return {
        "title": clean_text(
            note_card.get("title")
            or note_card.get("display_title")
            or note_card.get("note_title")
            or ""
        ),
        "content": clean_text(
            note_card.get("desc")
            or note_card.get("content")
            or note_card.get("description")
            or ""
        ),
        "publish_time": publish_time_raw,
        "publish_time_text": timestamp_to_datetime_text(publish_time_raw),
        "note_type": note_card.get("type", ""),
        "author_user_id": user_info.get("user_id", ""),
        "author_nickname": user_info.get("nickname", ""),
        "liked_count": interact_info.get("liked_count", ""),
        "collected_count": interact_info.get("collected_count", ""),
        "comment_count_from_note": interact_info.get("comment_count", ""),
        "view_count": view_count,
        "share_count": interact_info.get("share_count", ""),
        "ip_location": note_card.get("ip_location", ""),
    }


def normalize_comment(comment: dict[str, Any]) -> dict[str, Any]:
    user_info = comment.get("user_info") or {}
    create_time_raw = comment.get("create_time", "")

    replies = []
    for sub in comment.get("sub_comments") or []:
        sub_user_info = sub.get("user_info") or {}
        sub_create_time_raw = sub.get("create_time", "")

        replies.append(
            {
                "comment_id": sub.get("id", ""),
                "user_id": sub_user_info.get("user_id", ""),
                "nickname": sub_user_info.get("nickname", ""),
                "content": clean_text(sub.get("content", "")),
                "like_count": sub.get("like_count", 0),
                "create_time": sub_create_time_raw,
                "create_time_text": timestamp_to_datetime_text(sub_create_time_raw),
                "ip_location": sub.get("ip_location", ""),
            }
        )

    return {
        "comment_id": comment.get("id", ""),
        "user_id": user_info.get("user_id", ""),
        "nickname": user_info.get("nickname", ""),
        "content": clean_text(comment.get("content", "")),
        "like_count": comment.get("like_count", 0),
        "create_time": create_time_raw,
        "create_time_text": timestamp_to_datetime_text(create_time_raw),
        "ip_location": comment.get("ip_location", ""),
        "replies": replies,
    }


def load_existing_records(jsonl_path: Path) -> list[dict[str, Any]]:
    if not jsonl_path.exists():
        return []

    records = []
    with jsonl_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                record = json.loads(line)
            except Exception:
                continue

            if isinstance(record, dict):
                records.append(record)

    return records


def load_existing_note_ids(jsonl_path: Path) -> set[str]:
    return {
        str(record.get("note_id"))
        for record in load_existing_records(jsonl_path)
        if record.get("note_id")
    }


def build_existing_records_by_note_id(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    existing_records_by_note_id = {}
    for record in records:
        note_id = record.get("note_id")
        if note_id:
            existing_records_by_note_id[str(note_id)] = record
    return existing_records_by_note_id


def get_simple_note_id(simple_note: dict[str, Any]) -> str:
    note_id = simple_note.get("note_id") or simple_note.get("id")
    return str(note_id) if note_id else ""


def build_deletion_report(
    existing_records: list[dict[str, Any]],
    current_simple_notes: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """
    对比本地 JSONL 和当前博主主页返回的笔记 ID。
    本地存在但当前列表不存在的笔记，视为已删除或已不可见。
    """
    current_note_ids = {
        note_id
        for note_id in (get_simple_note_id(simple_note) for simple_note in current_simple_notes)
        if note_id
    }

    deleted_notes = []
    seen_note_ids = set()

    for record in existing_records:
        note_id = str(record.get("note_id") or "")
        if not note_id or note_id in seen_note_ids or note_id in current_note_ids:
            continue

        seen_note_ids.add(note_id)
        deleted_notes.append(
            {
                "note_id": note_id,
                "title": clean_text(record.get("title")),
                "publish_time": str(record.get("publish_time") or ""),
                "publish_time_text": first_non_empty(
                    record.get("publish_time_text"),
                    timestamp_to_datetime_text(record.get("publish_time")),
                ),
                "note_url": str(record.get("note_url") or ""),
            }
        )

    deleted_notes.sort(
        key=lambda note: timestamp_to_sort_value(note.get("publish_time")),
        reverse=True,
    )
    return deleted_notes


def write_deletion_report(report_path: Path, deleted_notes: list[dict[str, str]]) -> None:
    lines = [
        "# 删除报告",
        "",
        f"生成时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}",
        f"疑似已删除或不可见文章数: {len(deleted_notes)}",
        "",
    ]

    if deleted_notes:
        lines.extend(
            [
                "| 标题 | 文章发布日期 | note_id |",
                "| --- | --- | --- |",
            ]
        )

        for note in deleted_notes:
            title = clean_text(note.get("title")) or "(无标题)"
            title = title.replace("|", "\\|")
            publish_time_text = clean_text(note.get("publish_time_text")) or "(未知)"
            note_id = clean_text(note.get("note_id"))
            lines.append(f"| {title} | {publish_time_text} | {note_id} |")
    else:
        lines.append("未发现本地存在但当前主页列表缺失的文章。")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def print_deletion_report(deleted_notes: list[dict[str, str]], report_path: Path) -> None:
    print("deletion_report:", report_path)
    print("deleted_or_invisible_count:", len(deleted_notes))

    if not deleted_notes:
        print("deleted_or_invisible_notes: none")
        return

    print("deleted_or_invisible_notes:")
    for note in deleted_notes:
        title = clean_text(note.get("title")) or "(无标题)"
        publish_time_text = clean_text(note.get("publish_time_text")) or "(未知)"
        print(f"  - {publish_time_text} | {title} | note_id={note.get('note_id')}")


def append_jsonl(jsonl_path: Path, record: dict[str, Any]) -> None:
    with jsonl_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()


def rewrite_jsonl_replacing_record(jsonl_path: Path, new_record: dict[str, Any]) -> None:
    """
    用同 note_id 的新记录替换旧记录。
    保持 JSONL 单 note_id 单行，避免每次重爬最新评论时产生重复记录。
    """
    note_id = str(new_record.get("note_id") or "")
    if not note_id:
        append_jsonl(jsonl_path, new_record)
        return

    records = load_existing_records(jsonl_path)
    replaced = False
    next_records = []

    for record in records:
        if str(record.get("note_id") or "") == note_id:
            if not replaced:
                next_records.append(new_record)
                replaced = True
            continue
        next_records.append(record)

    if not replaced:
        next_records.append(new_record)

    tmp_path = jsonl_path.with_suffix(jsonl_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        for record in next_records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()

    tmp_path.replace(jsonl_path)


def simple_note_publish_time(simple_note: dict[str, Any]) -> Any:
    return (
        simple_note.get("time")
        or simple_note.get("publish_time")
        or simple_note.get("create_time")
        or simple_note.get("created_time")
        or simple_note.get("last_update_time")
        or simple_note.get("update_time")
    )


def simple_note_view_count(simple_note: dict[str, Any]) -> Any:
    return first_field(
        simple_note,
        [
            "view_count",
            "view_num",
            "views",
            "read_count",
            "read_num",
            "browse_count",
            "browse_num",
        ],
    )


def simple_note_comment_count(simple_note: dict[str, Any]) -> Any:
    return first_field(
        simple_note,
        [
            "comment_count",
            "comments_count",
            "comment_num",
        ],
    )


def note_publish_time_for_window(
    simple_note: dict[str, Any],
    existing_record: dict[str, Any] | None,
) -> Any:
    existing_record = existing_record or {}
    return first_non_empty(
        simple_note_publish_time(simple_note),
        existing_record.get("publish_time"),
        existing_record.get("time"),
        existing_record.get("create_time"),
        existing_record.get("created_time"),
    )


def is_note_within_days(publish_time: Any, days: int) -> bool:
    sort_value = timestamp_to_sort_value(publish_time)
    if sort_value <= 0:
        return False

    return time.time() - sort_value <= days * 24 * 60 * 60


def has_comment_count_value(value: Any) -> bool:
    return value is not None and not (isinstance(value, str) and value.strip() == "")


def did_comment_count_change(
    simple_note: dict[str, Any],
    existing_record: dict[str, Any] | None,
) -> bool:
    if not existing_record:
        return False

    current_count = simple_note_comment_count(simple_note)
    existing_count = existing_record.get("comment_count_from_note")

    if not has_comment_count_value(current_count) or not has_comment_count_value(existing_count):
        return False

    return parse_count(current_count) != parse_count(existing_count)


def should_skip_comments_by_metrics(note_fields: dict[str, Any]) -> tuple[bool, str]:
    view_count = parse_count(note_fields.get("view_count"))
    comment_count = parse_count(note_fields.get("comment_count_from_note"))

    if MIN_VIEW_COUNT is not None and MIN_VIEW_COUNT > 0 and view_count < MIN_VIEW_COUNT:
        return True, f"view_count {view_count} < MIN_VIEW_COUNT {MIN_VIEW_COUNT}"

    if MIN_COMMENT_COUNT is not None and MIN_COMMENT_COUNT > 0 and comment_count < MIN_COMMENT_COUNT:
        return True, f"comment_count {comment_count} < MIN_COMMENT_COUNT {MIN_COMMENT_COUNT}"

    return False, ""


def get_latest_note_id_from_existing_records(jsonl_path: Path) -> str:
    """
    从已保存 JSONL 中读取 publish_time，按发布时间最大值判断最新笔记。
    网页列表排序不参与判断。
    """
    records = load_existing_records(jsonl_path)
    candidates = []

    for record in records:
        note_id = record.get("note_id")
        if not note_id:
            continue

        publish_time = first_non_empty(
            record.get("publish_time"),
            record.get("time"),
            record.get("create_time"),
            record.get("created_time"),
        )
        sort_value = timestamp_to_sort_value(publish_time)
        if sort_value <= 0:
            continue

        candidates.append((sort_value, str(note_id)))

    if not candidates:
        return ""

    return max(candidates)[1]


def get_latest_note_id_from_simple_notes(simple_notes: list[dict[str, Any]]) -> str:
    """
    首次运行或旧 JSONL 没有可解析 publish_time 时的兜底逻辑。
    优先按 simple_notes 里的时间字段判断。
    如果列表没有时间字段，才使用列表第 1 条。
    """
    candidates = []

    for idx, simple_note in enumerate(simple_notes):
        note_id = simple_note.get("note_id") or simple_note.get("id")
        if not note_id:
            continue

        sort_value = timestamp_to_sort_value(simple_note_publish_time(simple_note))
        candidates.append((sort_value, -idx, str(note_id)))

    if not candidates:
        return ""

    if any(sort_value > 0 for sort_value, _, _ in candidates):
        return max(candidates)[2]

    return candidates[0][2]


def fetch_note_record(
    api: XHS_Apis,
    cookies_str: str,
    simple_note: dict[str, Any],
    out_dir: Path,
    idx: int,
    total: int,
    force_fetch_comments: bool = False,
    force_fetch_comments_reason: str = "",
) -> dict[str, Any] | None:
    note_id = simple_note.get("note_id") or simple_note.get("id")
    if not note_id:
        print(f"[{idx}/{total}] skip: missing note_id")
        return None

    note_url = build_note_url(simple_note)
    print(f"[{idx}/{total}] note:", note_url)

    ok, note_msg, note_raw = call_with_backoff(
        api.get_note_info,
        note_url,
        cookies_str,
    )

    if is_rate_limited(note_raw, note_msg):
        debug_path = out_dir / f"debug_rate_limited_note_{idx:04d}_{note_id}.json"
        save_debug_json(debug_path, {"msg": str(note_msg), "raw": note_raw})
        print("  note rate limited, saved debug:", debug_path)
        return None

    if not ok:
        debug_path = out_dir / f"debug_note_failed_{idx:04d}_{note_id}.json"
        save_debug_json(debug_path, {"msg": str(note_msg), "raw": note_raw})
        print("  note failed:", note_msg, "debug:", debug_path)
        return None

    item = extract_note_item(note_raw)
    if item is None:
        debug_path = out_dir / f"debug_note_raw_{idx:04d}_{note_id}.json"
        save_debug_json(debug_path, note_raw)

        print("  note detail structure unknown, saved debug:", debug_path)
        print("  top keys:", list(note_raw.keys()) if isinstance(note_raw, dict) else type(note_raw))

        data = note_raw.get("data") if isinstance(note_raw, dict) else None
        if isinstance(data, dict):
            print("  data keys:", list(data.keys()))
            print("  data preview:", json.dumps(data, ensure_ascii=False)[:500])
        else:
            print("  raw preview:", json.dumps(note_raw, ensure_ascii=False)[:500])

        return None

    note_fields = extract_note_fields(item)

    note_fields["view_count"] = first_non_empty(
        note_fields.get("view_count"),
        simple_note_view_count(simple_note),
    )
    note_fields["comment_count_from_note"] = first_non_empty(
        note_fields.get("comment_count_from_note"),
        simple_note_comment_count(simple_note),
    )

    should_skip_by_metrics, metric_skip_reason = should_skip_comments_by_metrics(note_fields)
    comments_skipped = False
    comments_skipped_by_metrics = False
    comments_skip_type = ""
    comments_skip_reason = ""

    if force_fetch_comments:
        if force_fetch_comments_reason:
            print("  force fetch comments:", force_fetch_comments_reason)
        comments_skip_reason = ""
    elif SKIP_COMMENTS:
        comments = []
        comments_skipped = True
        comments_skip_type = "global_skip_comments"
    elif should_skip_by_metrics:
        comments = []
        comments_skipped = True
        comments_skipped_by_metrics = True
        comments_skip_type = "metrics_filter"
        comments_skip_reason = metric_skip_reason
        print("  skip comments by metrics:", comments_skip_reason)
    else:
        force_fetch_comments = False

    if not comments_skipped:
        ok_comments, comment_msg, comments_raw = call_with_backoff(
            api.get_note_all_comment,
            note_url,
            cookies_str,
        )

        if is_rate_limited(comments_raw, comment_msg):
            debug_path = out_dir / f"debug_rate_limited_comments_{idx:04d}_{note_id}.json"
            save_debug_json(debug_path, {"msg": str(comment_msg), "raw": comments_raw})
            print("  comments rate limited, saved debug:", debug_path)
            comments = []
            comments_skipped = True
            comments_skip_type = "comments_rate_limited"
            comments_skip_reason = str(comment_msg)
        elif not ok_comments:
            debug_path = out_dir / f"debug_comments_failed_{idx:04d}_{note_id}.json"
            save_debug_json(debug_path, {"msg": str(comment_msg), "raw": comments_raw})
            print("  comments failed:", comment_msg, "debug:", debug_path)
            comments = []
            comments_skipped = True
            comments_skip_type = "comments_failed"
            comments_skip_reason = str(comment_msg)
        else:
            comments = [normalize_comment(c) for c in comments_raw]

    return {
        "note_id": str(note_id),
        "note_url": note_url,
        "title": note_fields["title"],
        "content": note_fields["content"],
        "publish_time": note_fields["publish_time"],
        "publish_time_text": note_fields["publish_time_text"],
        "note_type": note_fields["note_type"],
        "author_user_id": note_fields["author_user_id"],
        "author_nickname": note_fields["author_nickname"],
        "liked_count": note_fields["liked_count"],
        "collected_count": note_fields["collected_count"],
        "comment_count_from_note": note_fields["comment_count_from_note"],
        "view_count": note_fields["view_count"],
        "share_count": note_fields["share_count"],
        "ip_location": note_fields["ip_location"],
        "comments_skipped": comments_skipped,
        "comments_skipped_by_metrics": comments_skipped_by_metrics,
        "comments_skip_type": comments_skip_type,
        "comments_skip_reason": comments_skip_reason,
        "comments_force_fetch_reason": force_fetch_comments_reason if force_fetch_comments else "",
        "fetched_comment_count": len(comments),
        "fetched_reply_count": sum(len(c.get("replies") or []) for c in comments),
        "comments": comments,
    }


def main() -> None:
    cookies_str = load_cookie_text()
    target_user_url = load_target_user_url()
    if not cookies_str or cookies_str.strip().strip("'").strip('"') == "":
        raise RuntimeError(f"Cookie 为空，请先在 {COOKIE_PATH} 粘贴小红书 Cookie")

    api = XHS_Apis()

    user_id = target_user_url.split("/profile/")[-1].split("?")[0]
    out_dir = RAW_DATA_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    jsonl_path = RAW_JSONL_PATH
    progress_path = out_dir / "progress.json"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    deletion_report_path = DELETION_REPORT_PATH

    existing_records_before_crawl = load_existing_records(jsonl_path)
    existing_records_by_note_id = build_existing_records_by_note_id(existing_records_before_crawl)
    existing_note_ids = {
        str(record.get("note_id"))
        for record in existing_records_before_crawl
        if record.get("note_id")
    }

    success, msg, simple_notes = call_with_backoff(
        api.get_user_all_notes,
        target_user_url,
        cookies_str,
    )

    print("get_user_all_notes:", success, msg, "count:", len(simple_notes or []))

    if not success:
        raise RuntimeError(str(msg))

    if not simple_notes:
        raise RuntimeError("用户笔记列表为空")

    current_simple_notes = simple_notes
    deleted_notes = build_deletion_report(existing_records_before_crawl, current_simple_notes)
    write_deletion_report(deletion_report_path, deleted_notes)
    print_deletion_report(deleted_notes, deletion_report_path)

    if LIMIT is not None:
        simple_notes = simple_notes[:LIMIT]

    latest_note_id = ""
    if REFETCH_LATEST_NOTE_COMMENTS and simple_notes:
        latest_note_id = get_latest_note_id_from_existing_records(jsonl_path)

        # 首次运行或旧 JSONL 没有 publish_time 时，才退回 simple_notes 的时间字段。
        if not latest_note_id:
            latest_note_id = get_latest_note_id_from_simple_notes(simple_notes)

        if latest_note_id:
            print("latest note by publish_time will refetch comments:", latest_note_id)

    saved_count = len(existing_note_ids)

    for idx, simple_note in enumerate(simple_notes, 1):
        note_id = simple_note.get("note_id") or simple_note.get("id")
        if not note_id:
            print(f"[{idx}/{len(simple_notes)}] skip: missing note_id")
            continue

        note_id = str(note_id)
        existing_record = existing_records_by_note_id.get(note_id)
        should_refetch_latest = bool(latest_note_id and note_id == latest_note_id)
        publish_time_for_window = note_publish_time_for_window(simple_note, existing_record)
        should_force_recent_comments = is_note_within_days(
            publish_time_for_window,
            FORCE_COMMENTS_WITHIN_DAYS,
        )
        should_refetch_comments_by_count = (
            note_id in existing_note_ids
            and is_note_within_days(
                publish_time_for_window,
                REFETCH_COMMENTS_ON_COUNT_CHANGE_WITHIN_DAYS,
            )
            and did_comment_count_change(simple_note, existing_record)
        )

        force_fetch_comments_reason = ""
        if should_refetch_comments_by_count:
            force_fetch_comments_reason = "comments_count_changed_within_15_days"
        elif should_force_recent_comments:
            force_fetch_comments_reason = "publish_time_within_30_days"

        if note_id in existing_note_ids and not should_refetch_latest and not should_refetch_comments_by_count:
            print(f"[{idx}/{len(simple_notes)}] skip existing:", note_id)
            continue

        if note_id in existing_note_ids and should_refetch_latest:
            print(f"[{idx}/{len(simple_notes)}] refetch latest by publish_time comments:", note_id)
        elif should_refetch_comments_by_count:
            print(f"[{idx}/{len(simple_notes)}] refetch comments by comment count change:", note_id)

        sleep_multiplier = 1.0

        try:
            record = fetch_note_record(
                api=api,
                cookies_str=cookies_str,
                simple_note=simple_note,
                out_dir=out_dir,
                idx=idx,
                total=len(simple_notes),
                force_fetch_comments=bool(force_fetch_comments_reason),
                force_fetch_comments_reason=force_fetch_comments_reason,
            )

            if record is None:
                sleep_jitter()
                continue

            if record.get("comments_skipped_by_metrics"):
                sleep_multiplier = FILTERED_NOTE_SLEEP_MULTIPLIER

            if note_id in existing_note_ids:
                rewrite_jsonl_replacing_record(jsonl_path, record)
                action = "updated"
            else:
                append_jsonl(jsonl_path, record)
                existing_note_ids.add(note_id)
                saved_count += 1
                action = "saved"

            save_debug_json(
                progress_path,
                {
                    "total": len(simple_notes),
                    "current_index": idx,
                    "saved_count": saved_count,
                    "last_note_id": note_id,
                    "latest_note_id": latest_note_id,
                    "latest_note_source": "existing_jsonl_publish_time",
                    "jsonl_path": str(jsonl_path),
                    "user_id": user_id,
                    "target_url_path": str(TARGET_URL_PATH),
                    "cookie_path": str(COOKIE_PATH),
                    "skip_comments": SKIP_COMMENTS,
                    "refetch_latest_note_comments": REFETCH_LATEST_NOTE_COMMENTS,
                    "force_comments_within_days": FORCE_COMMENTS_WITHIN_DAYS,
                    "refetch_comments_on_count_change_within_days": REFETCH_COMMENTS_ON_COUNT_CHANGE_WITHIN_DAYS,
                    "min_view_count": MIN_VIEW_COUNT,
                    "min_comment_count": MIN_COMMENT_COUNT,
                    "filtered_note_sleep_multiplier": FILTERED_NOTE_SLEEP_MULTIPLIER,
                    "limit": LIMIT,
                },
            )

            print(
                f"  {action}:",
                "title=", record["title"][:30],
                "publish_time=", record["publish_time_text"],
                "view_count=", record["view_count"],
                "comment_count_from_note=", record["comment_count_from_note"],
                "comments_skipped=", record["comments_skipped"],
                "comments=", record["fetched_comment_count"],
                "replies=", record["fetched_reply_count"],
            )

        except Exception as e:
            debug_path = out_dir / f"debug_exception_{idx:04d}_{note_id}.json"
            save_debug_json(
                debug_path,
                {
                    "exception": repr(e),
                    "simple_note": simple_note,
                },
            )
            print("  handle failed:", repr(e), "debug:", debug_path)

        sleep_jitter(sleep_multiplier)

    print("done")
    print("saved_count:", saved_count)
    print("jsonl:", jsonl_path)
    print("deletion_report:", deletion_report_path)
    print("dir:", out_dir)


if __name__ == "__main__":
    main()
