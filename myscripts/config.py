from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = PROJECT_ROOT / "myscripts"

COOKIE_PATH = SCRIPT_DIR / "cookie.txt"
TARGET_URL_PATH = SCRIPT_DIR / "target_url.txt"
RAW_DATA_DIR = SCRIPT_DIR / "mydata_raw"
DATA_DIR = SCRIPT_DIR / "mydata"

RAW_JSONL_PATH = RAW_DATA_DIR / "notes_comments.jsonl"
FINAL_JSONL_PATH = DATA_DIR / "fez.jsonl"
DELETION_REPORT_PATH = DATA_DIR / "deletion_report.md"

DEFAULT_AUTHOR_NICKNAME = "fez"

# 调试阶段建议 5。确认正常后改成 None。
LIMIT = None

# 评论请求最容易触发风控。只抓标题正文时设为 True。
SKIP_COMMENTS = False

# 每次重爬时，强制重爬“publish_time 最新的一条笔记”的评论区。
REFETCH_LATEST_NOTE_COMMENTS = True

# 1 个月内的笔记进入抓取流程时，强制抓评论，不受 SKIP_COMMENTS 或评论数阈值影响。
FORCE_COMMENTS_WITHIN_DAYS = 30

# 15 天内的已存在笔记，如果主页评论数变化，则重新抓取评论。
REFETCH_COMMENTS_ON_COUNT_CHANGE_WITHIN_DAYS = 15

# 筛选器。任一条件不满足就跳过评论抓取，笔记主内容照常保存。
# 设为 0 或 None 表示不启用该条件。
MIN_VIEW_COUNT = 0
MIN_COMMENT_COUNT = 5

# 命中筛选器时，本轮循环末尾等待时间减半。
FILTERED_NOTE_SLEEP_MULTIPLIER = 0.5

# 请求间隔。抓 398 篇加评论时，建议不要太低。
MIN_SLEEP_SECONDS = 5
MAX_SLEEP_SECONDS = 15

# 触发 “访问频繁，请稍后再试” 后的退避。
RATE_LIMIT_SLEEP_SECONDS = 300
MAX_RETRY = 3
