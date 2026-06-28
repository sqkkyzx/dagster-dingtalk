from __future__ import annotations

import argparse
import html
import json
import logging
import re
import shutil
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


SCRIPT_DIR = Path(__file__).absolute().parent
DEFAULT_JSON_PATH = SCRIPT_DIR / "docinfolist_20260608.json"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "dingtalk_static_html"
DEFAULT_LOG_PATH = SCRIPT_DIR / "fetch_dingtalk_static_html.log"
DEFAULT_CATALOG_PATH = SCRIPT_DIR / "dingtalk_static_html_catalog.yaml"


QPS_LIMIT = 15
URL_TEMPLATE = (
    "https://icms-document.oss-cn-beijing.aliyuncs.com/"
    "zh-CN/dingtalk/development/topics/{slug}.html"
)
EXCLUDE_PARENT_TITLES = ("专属钉钉,炼丹炉（模型服务）,历史文档（不推荐）,宜搭,"
                         "Teambition 项目管理,行业与生态,音视频,Agoal,自有 OA 审批,"
                         "高级版专享接口,上下游组织（原合作空间）,上下级组织（原关联组织）,"
                         "钉钉快办,组织大脑,更多开放,智能招聘,应用市场,平台公告与计费,智能填表")

REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRIES = 2
RETRY_BACKOFF_SECONDS = 1.5
MAX_PATH_COMPONENT_LENGTH = 80
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)


@dataclass
class CatalogNode:
    title: str
    children: list[CatalogNode] = field(default_factory=list)
    static_url: str = ""
    source_doc_url: str = ""
    output_path: Path | None = None
    updated_at: str = ""
    fetched: bool = False


class RateLimiter:
    def __init__(self, qps: int) -> None:
        if qps <= 0:
            raise ValueError("qps must be greater than 0")
        self.interval_seconds = 1 / qps
        self.next_request_at = 0.0

    def wait(self) -> None:
        now = time.monotonic()
        sleep_seconds = self.next_request_at - now
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
        self.next_request_at = time.monotonic() + self.interval_seconds


class GmtModifyParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.gmt_modify = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "meta":
            return

        values = {name.lower(): value or "" for name, value in attrs}
        if values.get("name") == "gmtModify":
            self.gmt_modify = values.get("content", "").strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch DingTalk static HTML files and write a YAML catalog."
    )
    parser.add_argument(
        "--json-path",
        type=Path,
        default=DEFAULT_JSON_PATH,
        help=f"docinfolist JSON path. Default: {DEFAULT_JSON_PATH}",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory for downloaded HTML files. Default: {DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument(
        "--catalog-path",
        type=Path,
        default=DEFAULT_CATALOG_PATH,
        help=f"YAML catalog path. Default: {DEFAULT_CATALOG_PATH}",
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=DEFAULT_LOG_PATH,
        help=f"Log file path. Default: {DEFAULT_LOG_PATH}",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing HTML files instead of skipping them.",
    )
    parser.add_argument(
        "--clean-output",
        action="store_true",
        help="Remove the output directory before downloading.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Only process the first N document pages. Default: 0 means no limit.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only parse and log planned downloads; do not request or write files.",
    )
    return parser.parse_args()


def configure_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
    )


def load_catalog_tree(json_path: Path, output_dir: Path, limit: int) -> list[CatalogNode]:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("docinfolist JSON root must be a list")

    state = {"docs": 0}
    excluded_parent_titles = parse_exclude_parent_titles()

    def build_nodes(raw_nodes: list[Any], current_dir: Path) -> list[CatalogNode]:
        nodes: list[CatalogNode] = []
        name_parts = allocate_path_parts(raw_nodes)

        for raw_node, path_part in zip(raw_nodes, name_parts, strict=True):
            if not isinstance(raw_node, dict):
                continue

            doc_url = str(raw_node.get("docUrl") or "")
            if doc_url and limit > 0 and state["docs"] >= limit:
                continue

            title = str(raw_node.get("docName") or "").strip() or "未命名"
            children = raw_node.get("children")
            node = CatalogNode(title=title)

            if not doc_url and isinstance(children, list) and title in excluded_parent_titles:
                logging.info("EXCLUDE parent=%r", title)
                continue

            if doc_url:
                state["docs"] += 1
                slug = extract_slug(doc_url)
                node.source_doc_url = doc_url
                node.static_url = URL_TEMPLATE.format(slug=slug)
                node.output_path = current_dir / f"{path_part}.html"
                nodes.append(node)
                continue

            if isinstance(children, list):
                node.children = build_nodes(children, current_dir / path_part)
                if node.children:
                    nodes.append(node)

        return nodes

    return build_nodes(data, output_dir)


def parse_exclude_parent_titles() -> set[str]:
    return {title.strip() for title in EXCLUDE_PARENT_TITLES.split(",") if title.strip()}


def allocate_path_parts(raw_nodes: list[Any]) -> list[str]:
    base_parts: list[str] = []
    counts: dict[str, int] = {}

    for raw_node in raw_nodes:
        title = ""
        if isinstance(raw_node, dict):
            title = str(raw_node.get("docName") or "").strip()
        base_part = make_path_component(title or "未命名")
        base_parts.append(base_part)
        counts[base_part] = counts.get(base_part, 0) + 1

    seen: dict[str, int] = {}
    path_parts: list[str] = []
    for base_part in base_parts:
        if counts[base_part] == 1:
            path_parts.append(base_part)
            continue

        seen[base_part] = seen.get(base_part, 0) + 1
        suffix = f"（{seen[base_part]}）"
        path_parts.append(truncate_component(f"{base_part}{suffix}"))

    return path_parts


def make_path_component(title: str) -> str:
    replacements = {
        "<": "＜",
        ">": "＞",
        ":": "：",
        '"': "＂",
        "/": "／",
        "\\": "＼",
        "|": "｜",
        "?": "？",
        "*": "＊",
    }
    text = "".join(replacements.get(char, char) for char in title)
    text = re.sub(r"[\x00-\x1f]", "", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    if not text:
        text = "未命名"
    if text.upper() in {"CON", "PRN", "AUX", "NUL", "COM1", "LPT1"}:
        text = f"{text}_"
    return truncate_component(text)


def truncate_component(path_part: str) -> str:
    if len(path_part) <= MAX_PATH_COMPONENT_LENGTH:
        return path_part
    return path_part[:MAX_PATH_COMPONENT_LENGTH].rstrip(" .")


def extract_slug(doc_url: str) -> str:
    slug = Path(urlparse(doc_url).path).name.strip()
    if not slug:
        raise ValueError(f"cannot extract slug from docUrl: {doc_url}")
    return slug


def count_documents(nodes: list[CatalogNode]) -> int:
    total = 0
    for node in nodes:
        if node.static_url:
            total += 1
        total += count_documents(node.children)
    return total


def iter_document_nodes(nodes: list[CatalogNode]) -> list[CatalogNode]:
    documents: list[CatalogNode] = []
    for node in nodes:
        if node.static_url:
            documents.append(node)
        documents.extend(iter_document_nodes(node.children))
    return documents


def fetch_html(url: str, limiter: RateLimiter) -> tuple[int, bytes]:
    last_error: Exception | None = None
    request = Request(url, headers={"User-Agent": USER_AGENT})

    for attempt in range(1, MAX_RETRIES + 2):
        limiter.wait()
        try:
            with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                status = response.status
                body = response.read()
            if 200 <= status < 300:
                return status, body
            last_error = RuntimeError(f"HTTP {status}")
        except HTTPError as exc:
            if not should_retry_status(exc.code):
                raise
            last_error = exc
        except (TimeoutError, URLError) as exc:
            last_error = exc

        if attempt <= MAX_RETRIES:
            logging.warning(
                "retry attempt=%s/%s url=%s error=%s",
                attempt,
                MAX_RETRIES + 1,
                url,
                last_error,
            )
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)

    if last_error is None:
        raise RuntimeError(f"fetch failed without error: {url}")
    raise last_error


def should_retry_status(status: int) -> bool:
    return status == 408 or status == 429 or status >= 500


def extract_updated_at(body: bytes) -> str:
    parser = GmtModifyParser()
    parser.feed(body.decode("utf-8", errors="replace"))
    return parser.gmt_modify


def fetch_document(
    *,
    node: CatalogNode,
    index: int,
    total: int,
    limiter: RateLimiter,
    force: bool,
) -> str:
    if node.output_path is None:
        raise ValueError(f"document node has no output path: {node.title}")

    if node.output_path.exists() and not force:
        body = node.output_path.read_bytes()
        node.updated_at = extract_updated_at(body)
        node.fetched = True
        logging.info(
            "[%s/%s] SKIP title=%r updated_at=%s file=%s",
            index,
            total,
            node.title,
            node.updated_at,
            node.output_path.absolute(),
        )
        return "skipped"

    try:
        http_status, body = fetch_html(node.static_url, limiter)
        node.output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = node.output_path.with_suffix(node.output_path.suffix + ".tmp")
        temp_path.write_bytes(body)
        temp_path.replace(node.output_path)
        node.updated_at = extract_updated_at(body)
        node.fetched = True
        logging.info(
            "[%s/%s] SUCCESS title=%r http=%s bytes=%s updated_at=%s file=%s",
            index,
            total,
            node.title,
            http_status,
            len(body),
            node.updated_at,
            node.output_path.absolute(),
        )
        return "success"
    except Exception as exc:
        http_status = exc.code if isinstance(exc, HTTPError) else None
        logging.error(
            "[%s/%s] FAILED title=%r http=%s url=%s file=%s error=%s",
            index,
            total,
            node.title,
            http_status,
            node.static_url,
            node.output_path.absolute(),
            exc,
        )
        return "failed"


def prune_catalog(nodes: list[CatalogNode]) -> list[CatalogNode]:
    pruned: list[CatalogNode] = []
    for node in nodes:
        if node.static_url:
            if node.fetched:
                pruned.append(node)
            continue

        children = prune_catalog(node.children)
        if children:
            pruned.append(CatalogNode(title=node.title, children=children))

    return pruned


def write_catalog_yaml(path: Path, nodes: list[CatalogNode]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []

    def emit(node: CatalogNode, indent: int) -> None:
        prefix = " " * indent
        lines.append(f"{prefix}- 标题: {yaml_string(node.title)}")

        if node.static_url:
            if node.output_path is None:
                raise ValueError(f"document node has no output path: {node.title}")
            lines.append(
                f"{prefix}  静态文件: {yaml_string(str(node.output_path.absolute()))}"
            )
            lines.append(f"{prefix}  更新日期: {yaml_string(node.updated_at)}")

        if node.children:
            lines.append(f"{prefix}  子级:")
            for child in node.children:
                emit(child, indent + 4)

    for node in nodes:
        emit(node, 0)

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def yaml_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def log_plan(nodes: list[CatalogNode]) -> None:
    documents = iter_document_nodes(nodes)
    total = len(documents)
    for index, node in enumerate(documents, start=1):
        if node.output_path is None:
            continue
        logging.info(
            "[%s/%s] PLAN title=%r url=%s file=%s",
            index,
            total,
            node.title,
            node.static_url,
            node.output_path.absolute(),
        )


def clean_output_dir(output_dir: Path) -> None:
    if not output_dir.exists():
        return

    resolved_output_dir = output_dir.resolve()
    resolved_script_dir = SCRIPT_DIR.resolve()
    if resolved_output_dir == resolved_script_dir or resolved_script_dir not in resolved_output_dir.parents:
        raise ValueError("--clean-output only supports a generated directory under docs")

    shutil.rmtree(resolved_output_dir)
    logging.info("cleaned output_dir=%s", resolved_output_dir)


def main() -> int:
    args = parse_args()
    configure_logging(args.log_path)

    logging.info("json_path=%s", args.json_path)
    logging.info("output_dir=%s", args.output_dir)
    logging.info("catalog_path=%s", args.catalog_path)
    logging.info("log_path=%s", args.log_path)
    logging.info("qps_limit=%s", QPS_LIMIT)
    logging.info("url_template=%s", URL_TEMPLATE)
    logging.info("exclude_parent_titles=%s", sorted(parse_exclude_parent_titles()))

    tree = load_catalog_tree(args.json_path, args.output_dir, args.limit)
    total = count_documents(tree)

    logging.info(
        "documents=%s dry_run=%s force=%s clean_output=%s",
        total,
        args.dry_run,
        args.force,
        args.clean_output,
    )

    if args.dry_run:
        log_plan(tree)
        return 0

    if args.clean_output:
        clean_output_dir(args.output_dir)

    counters = {"success": 0, "skipped": 0, "failed": 0}
    limiter = RateLimiter(QPS_LIMIT)
    documents = iter_document_nodes(tree)
    for index, node in enumerate(documents, start=1):
        status = fetch_document(
            node=node,
            index=index,
            total=total,
            limiter=limiter,
            force=args.force,
        )
        counters[status] += 1

    catalog_nodes = prune_catalog(tree)
    write_catalog_yaml(args.catalog_path, catalog_nodes)

    logging.info(
        "done total=%s success=%s skipped=%s failed=%s catalog=%s",
        total,
        counters["success"],
        counters["skipped"],
        counters["failed"],
        args.catalog_path.absolute(),
    )
    return 1 if counters["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
