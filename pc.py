#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import random
import hashlib
import logging
import csv
import traceback
import threading
from collections import deque
from datetime import datetime
from urllib.parse import urlparse, urljoin
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import urllib.robotparser as robotparser
from html.parser import HTMLParser

# ========== 在这里填写 / 修改（只需修改 START_URL） ==========
print("=" * 60)
print("H型爬虫--Free工作室出品全网模式")
print("""
本隐私政策适用于所有使用本Python爬虫工具（以下简称“本工具”）的个人、开发者及机构用户，涵盖工具所有本地运行、离线调用、二次开发衍生的全部使用场景。
二、数据收集与使用规则
最小化采集原则
本工具默认仅在用户主动配置的任务范围内，采集用户明确指定的公开网页内容，不会主动窃取用户本地设备的通讯录、浏览记录、存储文件、地理位置等非授权隐私信息。
非必要数据零上传
本工具为本地优先运行架构，除用户主动开启的可选云端同步功能外，所有爬取任务数据、配置参数均仅存储在用户本地设备，不会默认回传至任何第三方服务器。
日志记录说明
工具仅保留本地运行的错误排查日志，日志内容不包含用户输入的敏感账号、密码、身份凭证信息，日志仅可由用户本地查看与删除。
三、用户权利与合规使用义务
用户享有爬取任务的完全控制权，可随时终止任务、删除所有本地爬取数据与工具配置信息。
用户承诺使用本工具时严格遵守《网络安全法》《数据安全法》及目标网站的robots协议规则，禁止使用本工具爬取国家涉密信息、个人隐私数据、付费非公开内容，禁止对目标站点发起高频恶意请求造成服务器过载。
用户利用本工具爬取、处理数据产生的所有行为及对应的法律责任，由用户自行全部承担，本工具开发者不对用户的违规使用行为承担连带责任。
四、数据安全保障
工具本地存储的爬取数据默认提供基础加密选项，用户可自主开启加密防护，避免本地数据被非授权访问。
本工具不会在任何版本中植入后台偷跑、静默上传数据的恶意代码，所有开源版本的代码均可由用户自行审计核验。
五、协议更新与争议处理
本政策后续更新会随工具版本迭代同步公示，持续使用工具即视为同意更新后的协议条款。
因本政策引发的争议，双方优先通过友好协商解决，协商不成可提交至工具
""")
print("=" * 60)

# 用户可以输入：普通起始 URL，例如 https://example.com
# 或者输入 "qwpc" 来启用全网并发模式（启动后会询问线程数和种子 URL 列表）
START_URL = input("请输入爬虫网址（输入 qwpc 启用全网自动爬虫模式）：").strip()
print("提示请插入U盘（E:）作为文本保存路径（脚本会优先写入 E:，若不可写会回退）")
# 输出目录（保存页面 HTML，如果希望也保存到 E:，可改为 r"E:\pages"）
OUTPUT_DIR = "pages"

# 统一 CSV 输出路径（优先写入 E:），将包含页面记录与日志记录
CSV_ON_E = r"E:\爬虫记录.csv"

# 默认最大抓取页数（在普通模式中会向用户询问）
DEFAULT_MAX_PAGES = 100

# 随机延迟范围（秒） - 在普通模式中会向用户询问
DEFAULT_DELAY_MIN = 1.0
DEFAULT_DELAY_MAX = 3.0

# 请求超时（秒）
TIMEOUT = 20.0

# 是否仅同域爬取（True = 只抓同域），在全网模式会被强制设为 False
SAME_DOMAIN = False

# 是否显示详细日志（True/False），详细日志也会以中文显示
VERBOSE = True

# 在终端打印最近日志的条数（重要事件后会显示）
PRINT_LOG_TAIL = 8

# 全网并发模式的最大线程上限（为了安全，做硬限制）
GLOBAL_MAX_THREADS = 10

# 每个域名的最小访问间隔（秒），用于并发模式避免对单域频繁请求
PER_DOMAIN_MIN_INTERVAL = 1.0

# ========== 失败处理相关配置（新增） ==========
# 单个 URL 最多重试次数（超过则标为最终失败）
MAX_RETRIES_PER_URL = 3
# 当单个域累计失败次数超过阈值时，进入冷却
DOMAIN_FAILURE_THRESHOLD = 10
# 域冷却时长（秒）
DOMAIN_COOLDOWN_SECONDS = 60

# ========== 结束可修改部分 ===================================

# 伪装头列表（示例：可扩展）
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/115.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/16.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/115.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
]

ACCEPT_LANGS = [
    "en-US,en;q=0.9",
    "zh-CN,zh;q=0.9,en;q=0.8",
    "en-GB,en;q=0.9",
]

class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []
        self.in_title = False
        self.title_chunks = []
        self.meta_description = None

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "a":
            for (k, v) in attrs:
                if k.lower() == "href" and v:
                    self.hrefs.append(v)
        elif tag == "title":
            self.in_title = True
        elif tag == "meta":
            attrd = {k.lower(): v for k, v in attrs}
            name = attrd.get("name", "").lower()
            if name == "description" and "content" in attrd:
                self.meta_description = attrd.get("content", "").strip()

    def handle_endtag(self, tag):
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title_chunks.append(data)

    def get_title(self):
        return "".join(self.title_chunks).strip() if self.title_chunks else ""

def safe_filename_from_url(url):
    h = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return f"{h[:16]}.html"

def is_same_domain(url_a, url_b):
    pa = urlparse(url_a)
    pb = urlparse(url_b)
    return pa.netloc == pb.netloc

def get_robot_parser_for(base_url, cache):
    p = urlparse(base_url)
    netloc = p.netloc
    if netloc in cache:
        return cache[netloc]
    robots_url = f"{p.scheme}://{netloc}/robots.txt"
    rp = robotparser.RobotFileParser()
    try:
        rp.set_url(robots_url)
        rp.read()
    except Exception:
        rp = None
    cache[netloc] = rp
    return rp

def allowed_by_robots(rp, user_agent, url):
    if rp is None:
        return True
    try:
        return rp.can_fetch(user_agent, url)
    except Exception:
        return True

def fetch_url(url, headers, timeout, retries=2, backoff=1.0):
    last_exc = None
    for attempt in range(retries + 1):
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=timeout) as resp:
                info = resp.info()
                content_type = info.get_content_type()
                charset = info.get_param('charset') or 'utf-8'
                data = resp.read()
                try:
                    text = data.decode(charset, errors='replace')
                except Exception:
                    text = data.decode('utf-8', errors='replace')
                return resp.getcode(), content_type, text, info
        except HTTPError as e:
            last_exc = e
            code = getattr(e, 'code', None)
            # 对 5xx 或 429 做重试（指数退避）
            if code and 500 <= code < 600:
                time.sleep(backoff * (attempt + 1))
                continue
            if code == 429:
                time.sleep(backoff * (attempt + 1))
                continue
            # 其他 HTTPError：直接返回状态码（下游会记录原因）
            return e.code, None, None, None
        except URLError as e:
            last_exc = e
            # 网络错误重试
            time.sleep(backoff * (attempt + 1))
            continue
    # 如果重试耗尽，抛出最后一次异常以便上层记录具体原因
    raise last_exc

def ensure_csv_location(csv_path):
    # 如果 E: 不存在或不可写，回退到当前目录
    try:
        dirpath = os.path.dirname(csv_path) or '.'
        if not os.path.exists(dirpath):
            os.makedirs(dirpath, exist_ok=True)
        # 测试写权限（临时写入并删除）
        test_path = os.path.join(dirpath, '.write_test.tmp')
        with open(test_path, 'w', encoding='utf-8') as f:
            f.write('test')
        os.remove(test_path)
        return csv_path
    except Exception:
        fallback = os.path.join(os.getcwd(), 'crawler_unified.csv')
        print(f"无法写入 {csv_path}，已改为写入当前目录：{fallback}")
        return fallback

# ----------------- 统一 CSV（页面 + 日志）相关 -----------------
UNIFIED_FIELDNAMES = [
    "类型",        # "页面" 或 "日志"
    "时间",        # ISO 时间
    "网址",
    "状态码",
    "标题",
    "描述",
    "保存文件名",
    "保存路径",
    "失败原因",
    "日志等级",
    "日志消息",
    "日志详情"
]

def write_unified_header_if_needed(unified_csv_path):
    exists = os.path.exists(unified_csv_path)
    if not exists:
        with open(unified_csv_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=UNIFIED_FIELDNAMES)
            writer.writeheader()

# Use a Lock to serialize writes from multiple threads
_csv_write_lock = threading.Lock()

def append_unified_row(unified_csv_path, row):
    try:
        with _csv_write_lock:
            with open(unified_csv_path, 'a', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=UNIFIED_FIELDNAMES)
                writer.writerow(row)
    except Exception:
        logging.exception("写入统一 CSV 失败：%s", unified_csv_path)

def format_exception_reason(e: Exception) -> str:
    try:
        if isinstance(e, HTTPError):
            return f"HTTPError {getattr(e, 'code', '')}: {str(e)}"
        if isinstance(e, URLError):
            reason = getattr(e, 'reason', None)
            return f"URLError: {reason if reason is not None else str(e)}"
        return str(e)
    except Exception:
        return repr(e)

def print_recent_log_table(unified_csv_path, n=PRINT_LOG_TAIL):
    try:
        if not os.path.exists(unified_csv_path):
            return
        with open(unified_csv_path, 'r', encoding='utf-8') as f:
            reader = list(csv.DictReader(f))
            if not reader:
                return
            logs = [r for r in reader if r.get("类型") == "日志"]
            if not logs:
                return
            rows = logs[-n:]
    except Exception:
        return

    cols = ["时间", "日志等级", "日志消息", "网址", "日志详情"]
    widths = {c: len(c) for c in cols}
    for r in rows:
        for c in cols:
            widths[c] = max(widths[c], len(str(r.get(c, ""))))

    try:
        term_w = os.get_terminal_size().columns
    except Exception:
        term_w = 120
    total_w = sum(widths.values()) + 3 * (len(cols) - 1) + 4
    if total_w > term_w:
        extra = total_w - term_w
        for key in ("日志详情", "日志消息", "网址"):
            reduce_by = min(extra, max(0, widths.get(key, 0) - 10))
            widths[key] -= reduce_by
            extra -= reduce_by
            if extra <= 0:
                break

    sep = " | "
    header = sep.join(c.ljust(widths[c]) for c in cols)
    line = "-" * min(term_w, len(header) + 4)
    print(line)
    print(header)
    print(line)
    for r in rows:
        cells = []
        for c in cols:
            v = str(r.get(c, ""))
            if len(v) > widths[c]:
                v = v[:widths[c] - 3] + "..."
            cells.append(v.ljust(widths[c]))
        print(sep.join(cells))
    print(line)

# 封装日志写入（同时写入标准 logging 与统一 CSV）
def unified_log(unified_csv_path, level, msg, url=None, detail=None):
    if level == "INFO":
        logging.info(msg if isinstance(msg, str) else repr(msg))
    elif level == "WARNING":
        logging.warning(msg if isinstance(msg, str) else repr(msg))
    elif level in ("ERROR", "EXCEPTION"):
        logging.error(msg if isinstance(msg, str) else repr(msg))
    row = {
        "类型": "日志",
        "时间": datetime.utcnow().isoformat(),
        "网址": url or "",
        "状态码": "",
        "标题": "",
        "描述": "",
        "保存文件名": "",
        "保存路径": "",
        "失败原因": "",
        "日志等级": level,
        "日志消息": msg if isinstance(msg, str) else repr(msg),
        "日志详情": detail or "",
    }
    append_unified_row(unified_csv_path, row)

# ----------------- 统一 CSV 相关 结束 -----------------

# ----------------- 单线程/原有爬取逻辑（保留） -----------------
def crawl_single(start_url, output_dir, unified_csv_path, max_pages, delay_min, delay_max, timeout, same_domain, verbose):
    os.makedirs(output_dir, exist_ok=True)
    visited = set()
    q = deque([start_url])
    robot_cache = {}
    rp = get_robot_parser_for(start_url, robot_cache)

    pages = 0
    start_time = time.time()
    if verbose:
        unified_log(unified_csv_path, "INFO", f"开始抓取（单线程）：{start_url}", url=start_url)

    while q and pages < max_pages:
        url = q.popleft()
        if url in visited:
            continue
        visited.add(url)

        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept-Language": random.choice(ACCEPT_LANGS),
            "Referer": start_url,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        user_agent_for_robots = headers.get("User-Agent", "*")
        if not allowed_by_robots(rp, user_agent_for_robots, url):
            if verbose:
                unified_log(unified_csv_path, "INFO", "被 robots.txt 拦截，跳过：%s" % url, url=url, detail="被 robots.txt 拦截")
            row = {
                "类型": "页面",
                "时间": datetime.utcnow().isoformat(),
                "网址": url,
                "状态码": "",
                "标题": "",
                "描述": "",
                "保存文件名": "",
                "保存路径": "",
                "失败原因": "被 robots.txt 拦截",
                "日志等级": "",
                "日志消息": "",
                "日志详情": "",
            }
            append_unified_row(unified_csv_path, row)
            if verbose:
                print_recent_log_table(unified_csv_path, PRINT_LOG_TAIL)
            continue

        if verbose:
            unified_log(unified_csv_path, "INFO", "抓取：%s" % url, url=url)

        try:
            code, content_type, text, info = fetch_url(url, headers, timeout)
            fetch_time_iso = datetime.utcnow().isoformat()
            if code != 200:
                reason = f"HTTP 状态码 {code}"
                if verbose:
                    unified_log(unified_csv_path, "WARNING", "返回非 200 (%s)：%s" % (code, url), url=url, detail=reason)
                row = {
                    "类型": "页面",
                    "时间": fetch_time_iso,
                    "网址": url,
                    "状态码": code,
                    "标题": "",
                    "描述": "",
                    "保存文件名": "",
                    "保存路径": "",
                    "失败原因": reason,
                    "日志等级": "",
                    "日志消息": "",
                    "日志详情": "",
                }
                append_unified_row(unified_csv_path, row)
                if verbose:
                    print_recent_log_table(unified_csv_path, PRINT_LOG_TAIL)
                continue
            if content_type and not content_type.startswith("text/html"):
                if verbose:
                    unified_log(unified_csv_path, "INFO", "跳过非 HTML 内容（%s）：%s" % (content_type, url), url=url, detail=f"非 HTML 内容: {content_type}")
                row = {
                    "类型": "页面",
                    "时间": fetch_time_iso,
                    "网址": url,
                    "状态码": code,
                    "标题": "",
                    "描述": "",
                    "保存文件名": "",
                    "保存路径": "",
                    "失败原因": f"非 HTML 内容: {content_type}",
                    "日志等级": "",
                    "日志消息": "",
                    "日志详情": "",
                }
                append_unified_row(unified_csv_path, row)
                if verbose:
                    print_recent_log_table(unified_csv_path, PRINT_LOG_TAIL)
                continue

            parser = LinkParser()
            try:
                parser.feed(text)
            except Exception as e:
                unified_log(unified_csv_path, "EXCEPTION", "解析 HTML 时出错（继续）：%s" % format_exception_reason(e), url=url, detail=format_exception_reason(e))
            title = parser.get_title()
            meta_desc = parser.meta_description or ""

            fname = safe_filename_from_url(url)
            path = os.path.join(output_dir, fname)
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(text)
            except Exception as e:
                unified_log(unified_csv_path, "EXCEPTION", "保存 HTML 文件失败：%s -> %s" % (url, path), url=url, detail=format_exception_reason(e))
                row = {
                    "类型": "页面",
                    "时间": fetch_time_iso,
                    "网址": url,
                    "状态码": code,
                    "标题": title,
                    "描述": meta_desc,
                    "保存文件名": "",
                    "保存路径": "",
                    "失败原因": f"保存文件失败: {format_exception_reason(e)}",
                    "日志等级": "",
                    "日志消息": "",
                    "日志详情": "",
                }
                append_unified_row(unified_csv_path, row)
                if verbose:
                    print_recent_log_table(unified_csv_path, PRINT_LOG_TAIL)
                continue

            pages += 1
            if verbose:
                unified_log(unified_csv_path, "INFO", "已保存（%d）：%s -> %s" % (pages, url, path), url=url, detail=os.path.abspath(path))

            row = {
                "类型": "页面",
                "时间": fetch_time_iso,
                "网址": url,
                "状态码": code,
                "标题": title,
                "描述": meta_desc,
                "保存文件名": fname,
                "保存路径": os.path.abspath(path),
                "失败原因": "",
                "日志等级": "",
                "日志消息": "",
                "日志详情": "",
            }
            append_unified_row(unified_csv_path, row)

            if verbose:
                print_recent_log_table(unified_csv_path, PRINT_LOG_TAIL)

            for href in parser.hrefs:
                href = href.strip()
                if not href or href.lower().startswith(("javascript:", "mailto:", "#")):
                    continue
                new_url = urljoin(url, href)
                parsed = urlparse(new_url)
                if parsed.scheme not in ("http", "https"):
                    continue
                if same_domain and not is_same_domain(start_url, new_url):
                    continue
                if new_url not in visited:
                    q.append(new_url)

        except Exception as e:
            reason = format_exception_reason(e)
            unified_log(unified_csv_path, "EXCEPTION", "抓取失败：%s" % reason, url=url, detail=reason)
            row = {
                "类型": "页面",
                "时间": datetime.utcnow().isoformat(),
                "网址": url,
                "状态码": "",
                "标题": "",
                "描述": "",
                "保存文件名": "",
                "保存路径": "",
                "失败原因": reason,
                "日志等级": "",
                "日志消息": "",
                "日志详情": "",
            }
            append_unified_row(unified_csv_path, row)
            if verbose:
                print_recent_log_table(unified_csv_path, PRINT_LOG_TAIL)

        try:
            time.sleep(random.uniform(delay_min, delay_max))
        except Exception:
            time.sleep(1.0)

    elapsed = time.time() - start_time
    unified_log(unified_csv_path, "INFO", f"单线程抓取完成。已保存页面数量：{pages}，耗时 {elapsed:.1f} 秒。", detail=f"总耗时 {elapsed:.1f}s")
    print(f"完成。已保存页面数量：{pages}。输出 CSV：{unified_csv_path}")

# ----------------- 并发全网抓取逻辑（qwpc 模式） -----------------
def crawl_global(start_urls, output_dir, unified_csv_path, max_pages, delay_min, delay_max, timeout, num_workers):
    """
    并发全网抓取：
    - start_urls: 列表起始 URL（種子）
    - num_workers: 並發線程數（已在 main 中做安全上限）
    - max_pages: 全局總抓取頁數（跨線程計數）
    主要增强：
    - URL 重试计数（MAX_RETRIES_PER_URL）
    - 域失败计数与冷却（DOMAIN_FAILURE_THRESHOLD / DOMAIN_COOLDOWN_SECONDS）
    - in_flight 集合避免并发重复抓取
    """
    os.makedirs(output_dir, exist_ok=True)

    # 全局共享結構
    q = deque()
    for u in start_urls:
        q.append(u)
    visited = set()
    in_flight = set()
    visited_lock = threading.Lock()
    robot_cache = {}
    robot_lock = threading.Lock()
    last_access = {}  # domain -> last access timestamp
    last_access_lock = threading.Lock()

    pages_saved = 0
    pages_lock = threading.Lock()

    stop_event = threading.Event()

    # 失败/重试管理
    url_retry_counts = {}      # url -> retry count
    retry_lock = threading.Lock()
    domain_failures = {}       # domain -> failure count
    domain_cooldown_until = {} # domain -> timestamp until which domain is cooled down
    domain_lock = threading.Lock()

    def mark_final_failure(url, reason, code=None):
        """记录最终失败到 CSV 并从 in_flight 中移除"""
        row = {
            "类型": "页面",
            "时间": datetime.utcnow().isoformat(),
            "网址": url,
            "状态码": code if code is not None else "",
            "标题": "",
            "描述": "",
            "保存文件名": "",
            "保存路径": "",
            "失败原因": reason,
            "日志等级": "",
            "日志消息": "",
            "日志详情": "",
        }
        append_unified_row(unified_csv_path, row)
        with visited_lock:
            if url in in_flight:
                in_flight.remove(url)
            visited.add(url)

    # worker 函數
    def worker(worker_id):
        nonlocal pages_saved
        while not stop_event.is_set():
            # 終止條件：達到 max_pages
            with pages_lock:
                if pages_saved >= max_pages:
                    break
            try:
                with visited_lock:
                    if not q:
                        break
                    url = q.popleft()
                    # skip if already successfully visited
                    if url in visited or url in in_flight:
                        continue
                    # mark in flight to avoid duplicate concurrent processing
                    in_flight.add(url)
            except Exception:
                continue

            parsed = urlparse(url)
            domain = parsed.netloc

            # 如果域名处于冷却期，则重入队列末尾并跳过当前循环
            with domain_lock:
                until = domain_cooldown_until.get(domain)
                if until and time.time() < until:
                    # requeue to end and remove in_flight mark
                    with visited_lock:
                        if url in in_flight:
                            in_flight.remove(url)
                        if url not in q and url not in visited:
                            q.append(url)
                    time.sleep(0.1)
                    continue

            headers = {
                "User-Agent": random.choice(USER_AGENTS),
                "Accept-Language": random.choice(ACCEPT_LANGS),
                "Referer": random.choice(start_urls) if start_urls else "",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }

            # robots parser per domain
            with robot_lock:
                rp = robot_cache.get(domain)
                if rp is None:
                    rp = get_robot_parser_for(url, robot_cache)
                    robot_cache[domain] = rp

            if not allowed_by_robots(rp, headers.get("User-Agent", "*"), url):
                unified_log(unified_csv_path, "INFO", f"[W{worker_id}] 被 robots.txt 拦截，跳過：{url}", url=url, detail="被 robots.txt 拦截")
                # 写入页面记录（被 robots 拦截）
                row = {
                    "类型": "页面",
                    "时间": datetime.utcnow().isoformat(),
                    "网址": url,
                    "状态码": "",
                    "标题": "",
                    "描述": "",
                    "保存文件名": "",
                    "保存路径": "",
                    "失败原因": "被 robots.txt 拦截",
                    "日志等级": "",
                    "日志消息": "",
                    "日志详情": "",
                }
                append_unified_row(unified_csv_path, row)
                with visited_lock:
                    if url in in_flight:
                        in_flight.remove(url)
                    visited.add(url)
                continue

            # respect per-domain minimum interval
            to_wait = 0.0
            now_t = time.time()
            with last_access_lock:
                last = last_access.get(domain)
                if last is not None:
                    elapsed = now_t - last
                    if elapsed < PER_DOMAIN_MIN_INTERVAL:
                        to_wait = PER_DOMAIN_MIN_INTERVAL - elapsed
                last_access[domain] = time.time()  # update immediately to reserve slot

            if to_wait > 0:
                time.sleep(to_wait)

            # 抓取
            if VERBOSE:
                unified_log(unified_csv_path, "INFO", f"[W{worker_id}] 抓取：{url}", url=url)
            try:
                # 获取当前 retry count
                with retry_lock:
                    retries = url_retry_counts.get(url, 0)

                code, content_type, text, info = fetch_url(url, headers, timeout)
                fetch_time_iso = datetime.utcnow().isoformat()

                # 非 200 的响应，决定是否重试或最终失败
                if code != 200:
                    reason = f"HTTP 状态码 {code}"
                    # 对 5xx 和 429 视为可重试，否则直接记录为失败
                    if (isinstance(code, int) and (500 <= code < 600 or code == 429)) and retries < MAX_RETRIES_PER_URL:
                        with retry_lock:
                            url_retry_counts[url] = retries + 1
                        unified_log(unified_csv_path, "WARNING", f"[W{worker_id}] 返回可重试非 200 ({code})：{url}，重试 {retries+1}/{MAX_RETRIES_PER_URL}", url=url, detail=reason)
                        # 重新入队（尾部），稍作退避
                        with visited_lock:
                            if url in in_flight:
                                in_flight.remove(url)
                        time.sleep(min(5, (retries + 1) * 1.5))
                        with visited_lock:
                            if url not in q and url not in visited:
                                q.append(url)
                        continue
                    else:
                        unified_log(unified_csv_path, "WARNING", f"[W{worker_id}] 返回非 200 ({code})：{url}", url=url, detail=reason)
                        mark_final_failure(url, reason, code=code)
                        # update domain failure count
                        with domain_lock:
                            domain_failures[domain] = domain_failures.get(domain, 0) + 1
                            if domain_failures[domain] >= DOMAIN_FAILURE_THRESHOLD:
                                domain_cooldown_until[domain] = time.time() + DOMAIN_COOLDOWN_SECONDS
                                unified_log(unified_csv_path, "WARNING", f"[W{worker_id}] 域 {domain} 进入冷却 {DOMAIN_COOLDOWN_SECONDS}s，因为失败次数={domain_failures[domain]}", detail=f"domain cooldown")
                        continue

                if content_type and not content_type.startswith("text/html"):
                    # 非 HTML 通常不重试
                    unified_log(unified_csv_path, "INFO", f"[W{worker_id}] 跳过非 HTML 内容（{content_type}）：{url}", url=url, detail=f"非 HTML 内容: {content_type}")
                    mark_final_failure(url, f"非 HTML 内容: {content_type}", code=code)
                    with domain_lock:
                        domain_failures[domain] = domain_failures.get(domain, 0) + 1
                    continue

                parser = LinkParser()
                try:
                    parser.feed(text)
                except Exception as e:
                    unified_log(unified_csv_path, "EXCEPTION", f"[W{worker_id}] 解析 HTML 错误（继续）: {format_exception_reason(e)}", url=url, detail=format_exception_reason(e))
                title = parser.get_title()
                meta_desc = parser.meta_description or ""

                fname = safe_filename_from_url(url)
                path = os.path.join(output_dir, fname)
                try:
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(text)
                except Exception as e:
                    unified_log(unified_csv_path, "EXCEPTION", f"[W{worker_id}] 保存 HTML 文件失败：{url} -> {path}", url=url, detail=format_exception_reason(e))
                    # 保存失败，视为最终失败（不反复尝试写文件）
                    mark_final_failure(url, f"保存文件失败: {format_exception_reason(e)}")
                    with domain_lock:
                        domain_failures[domain] = domain_failures.get(domain, 0) + 1
                        if domain_failures[domain] >= DOMAIN_FAILURE_THRESHOLD:
                            domain_cooldown_until[domain] = time.time() + DOMAIN_COOLDOWN_SECONDS
                            unified_log(unified_csv_path, "WARNING", f"[W{worker_id}] 域 {domain} 进入冷却 {DOMAIN_COOLDOWN_SECONDS}s，因为失败次数={domain_failures[domain]}", detail=f"domain cooldown")
                    continue

                with pages_lock:
                    pages_saved += 1
                    current_saved = pages_saved

                unified_log(unified_csv_path, "INFO", f"[W{worker_id}] 已保存（{current_saved}）：{url} -> {path}", url=url, detail=os.path.abspath(path))
                row = {
                    "类型": "页面",
                    "时间": fetch_time_iso,
                    "网址": url,
                    "状态码": code,
                    "标题": title,
                    "描述": meta_desc,
                    "保存文件名": fname,
                    "保存路径": os.path.abspath(path),
                    "失败原因": "",
                    "日志等级": "",
                    "日志消息": "",
                    "日志详情": "",
                }
                append_unified_row(unified_csv_path, row)

                # enqueue discovered links (跨域允許)
                with visited_lock:
                    # 成功保存后把 url 从 in_flight 转到 visited
                    if url in in_flight:
                        in_flight.remove(url)
                    visited.add(url)
                    for href in parser.hrefs:
                        href = href.strip()
                        if not href or href.lower().startswith(("javascript:", "mailto:", "#")):
                            continue
                        new_url = urljoin(url, href)
                        parsed_new = urlparse(new_url)
                        if parsed_new.scheme not in ("http", "https"):
                            continue
                        if new_url not in visited and new_url not in q and new_url not in in_flight:
                            q.append(new_url)

                # 在每次保存後打印日志摘要到控制台（非阻塞）
                if VERBOSE:
                    print_recent_log_table(unified_csv_path, PRINT_LOG_TAIL)

                # 達到總數則觸發停止
                with pages_lock:
                    if pages_saved >= max_pages:
                        stop_event.set()
                        break

            except Exception as e:
                reason = format_exception_reason(e)
                # increment retry count and decide whether to retry
                with retry_lock:
                    retries = url_retry_counts.get(url, 0)
                    url_retry_counts[url] = retries + 1
                    retries_after = retries + 1

                # treat URLError / other transient exceptions as retryable up to MAX_RETRIES_PER_URL
                if retries_after <= MAX_RETRIES_PER_URL:
                    unified_log(unified_csv_path, "WARNING", f"[W{worker_id}] 抓取异常（重试 {retries_after}/{MAX_RETRIES_PER_URL}）：{url} -> {reason}", url=url, detail=reason)
                    # 将 in_flight 标记移除并把 URL 放回队列尾，带指数退避
                    with visited_lock:
                        if url in in_flight:
                            in_flight.remove(url)
                    time.sleep(min(5, retries_after * 1.5))
                    with visited_lock:
                        if url not in q and url not in visited:
                            q.append(url)
                    continue
                else:
                    unified_log(unified_csv_path, "EXCEPTION", f"[W{worker_id}] 抓取失败（最终）：{url} -> {reason}", url=url, detail=reason)
                    mark_final_failure(url, reason)
                    with domain_lock:
                        domain_failures[domain] = domain_failures.get(domain, 0) + 1
                        if domain_failures[domain] >= DOMAIN_FAILURE_THRESHOLD:
                            domain_cooldown_until[domain] = time.time() + DOMAIN_COOLDOWN_SECONDS
                            unified_log(unified_csv_path, "WARNING", f"[W{worker_id}] 域 {domain} 进入冷却 {DOMAIN_COOLDOWN_SECONDS}s，因为失败次数={domain_failures[domain]}", detail=f"domain cooldown")

                if VERBOSE:
                    print_recent_log_table(unified_csv_path, PRINT_LOG_TAIL)

            # 更自然的延迟（每个 worker 在请求间也随机睡眠）
            try:
                time.sleep(random.uniform(delay_min, delay_max))
            except Exception:
                time.sleep(0.5)

    # 启动线程
    threads = []
    for i in range(num_workers):
        t = threading.Thread(target=worker, args=(i+1,), daemon=True)
        threads.append(t)
        t.start()

    # 等待线程结束
    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        stop_event.set()
        unified_log(unified_csv_path, "WARNING", "收到中断信号，正在停止线程并退出", detail="KeyboardInterrupt")
        for t in threads:
            t.join(timeout=1.0)

    unified_log(unified_csv_path, "INFO", f"全网模式抓取完成。已保存页面数量（全局）：{pages_saved}", detail=f"目标总页数：{max_pages}")
    print(f"全网抓取完成。已保存页面数量（全局）：{pages_saved}。输出 CSV：{unified_csv_path}")

# ----------------- End global crawl -----------------

def main():
    # 把 global 提前声明，必须在函数內第一次使用 PER_DOMAIN_MIN_INTERVAL 之前
    global PER_DOMAIN_MIN_INTERVAL

    # 全局统一 CSV 路径（优先 E:，不可写则回退）
    unified_csv_target = ensure_csv_location(CSV_ON_E)

    # 初始化控制台日志格式
    if VERBOSE:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    # 写入统一 CSV 表头（若不存在）
    write_unified_header_if_needed(unified_csv_target)

    if not START_URL:
        print('请在脚本启动时输入要爬的起始网址，例如：https://example.com，或输入 qwpc 启用全网模式。')
        return

    # If user entered qwpc, go into global mode
    if START_URL.lower() == "qwpc":
        print("已启用 全网自动爬虫 模式（qwpc）。请谨慎使用，确保合规。")
        # 询问并发线程数
        try:
            n_raw = input(f"请输入并发爬虫数量（线程数，1-{GLOBAL_MAX_THREADS}，默认 2）：").strip()
            num_workers = int(n_raw) if n_raw else 2
        except Exception:
            num_workers = 2
        if num_workers < 1:
            num_workers = 1
        if num_workers > GLOBAL_MAX_THREADS:
            print(f"并发线程数上限为 {GLOBAL_MAX_THREADS}，已设置为 {GLOBAL_MAX_THREADS}")
            num_workers = GLOBAL_MAX_THREADS

        # 询问总抓取页面数（全局）
        try:
            max_raw = input(f"请输入全局总抓取页数（整数，默认 {DEFAULT_MAX_PAGES}）：").strip()
            max_pages = int(max_raw) if max_raw else DEFAULT_MAX_PAGES
        except Exception:
            max_pages = DEFAULT_MAX_PAGES

        # 询问每域最小访问间隔（可选）
        try:
            per_domain_raw = input(f"每域最小访问间隔（秒，默认 {PER_DOMAIN_MIN_INTERVAL}）：").strip()
            per_domain = float(per_domain_raw) if per_domain_raw else PER_DOMAIN_MIN_INTERVAL
        except Exception:
            per_domain = PER_DOMAIN_MIN_INTERVAL

        # 询问延迟范围
        try:
            dmin_raw = input(f"每请求最小延迟（秒，默认 {DEFAULT_DELAY_MIN}）：").strip()
            dmax_raw = input(f"每请求最大延迟（秒，默认 {DEFAULT_DELAY_MAX}）：").strip()
            delay_min_local = float(dmin_raw) if dmin_raw else DEFAULT_DELAY_MIN
            delay_max_local = float(dmax_raw) if dmax_raw else DEFAULT_DELAY_MAX
        except Exception:
            delay_min_local = DEFAULT_DELAY_MIN
            delay_max_local = DEFAULT_DELAY_MAX

        # 询问种子 URL 列表数目并收集
        try:
            seeds_count_raw = input("请输入要提供的起始种子 URL 数量（整数，默认为 3）：").strip()
            seeds_count = int(seeds_count_raw) if seeds_count_raw else 3
        except Exception:
            seeds_count = 3
        if seeds_count < 1:
            seeds_count = 1
        start_urls = []
        print("请依次输入起始种子 URL（每行回车）：")
        for i in range(seeds_count):
            s = input(f"种子 URL #{i+1}（示例 https://example.com，按回车跳过并使用默认）：").strip()
            if s:
                start_urls.append(s)
        # 如果用户没有输入任何 URL，使用一组小的默认种子（仅作为示例）
        if not start_urls:
            start_urls = [
                "https://example.com",
                "https://www.wikipedia.org",
                "https://www.python.org"
            ]
            print("未提供有效种子，使用默认种子：", ", ".join(start_urls))

        # 更新全局 config
        PER_DOMAIN_MIN_INTERVAL = max(0.1, float(per_domain))
        # 强制跨域抓取
        same_domain_local = False

        # 提前写入一条启动日志
        unified_log(unified_csv_target, "INFO", f"启动全网模式：workers={num_workers}, seeds={len(start_urls)}, max_pages={max_pages}", detail=f"种子: {start_urls}")

        # 启动全网并发爬取
        crawl_global(
            start_urls=start_urls,
            output_dir=OUTPUT_DIR,
            unified_csv_path=unified_csv_target,
            max_pages=max_pages,
            delay_min=delay_min_local,
            delay_max=delay_max_local,
            timeout=TIMEOUT,
            num_workers=num_workers
        )
        return

    # 普通單起始 URL 模式：詢問參數（保留原來交互）
    try:
        max_pages = int(input(f"请输入最大抓取页数（默认 {DEFAULT_MAX_PAGES}）：").strip() or DEFAULT_MAX_PAGES)
    except Exception:
        max_pages = DEFAULT_MAX_PAGES
    try:
        delay_min = float(input(f"请输入最小延迟（秒，默认 {DEFAULT_DELAY_MIN}）：").strip() or DEFAULT_DELAY_MIN)
    except Exception:
        delay_min = DEFAULT_DELAY_MIN
    try:
        delay_max = float(input(f"请输入最大延迟（秒，默认 {DEFAULT_DELAY_MAX}）：").strip() or DEFAULT_DELAY_MAX)
    except Exception:
        delay_max = DEFAULT_DELAY_MAX

    # 写入启动日志
    unified_log(unified_csv_target, "INFO", f"启动单起始模式：start={START_URL}, max_pages={max_pages}", url=START_URL)

    # 运行单线程爬虫（保留默认行为）
    crawl_single(
        start_url=START_URL,
        output_dir=OUTPUT_DIR,
        unified_csv_path=unified_csv_target,
        max_pages=max_pages,
        delay_min=delay_min,
        delay_max=delay_max,
        timeout=TIMEOUT,
        same_domain=SAME_DOMAIN,
        verbose=VERBOSE
    )

if __name__ == "__main__":
    main()