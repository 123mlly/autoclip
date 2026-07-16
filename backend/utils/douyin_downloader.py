"""
抖音解析 / 下载（不依赖 yt-dlp DouyinIE 的 aweme 签名接口）。

优先走 iesdouyin 分享页的 window._ROUTER_DATA，多数公开视频无需登录 Cookie。
短链 v.douyin.com 会先跟随重定向再取视频 ID。
"""

from __future__ import annotations

import json
import logging
import re
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

import requests

logger = logging.getLogger(__name__)

_MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
    "Mobile/15E148 Safari/604.1"
)
_DESKTOP_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_VIDEO_ID_RE = re.compile(
    r"(?:douyin\.com/video/|iesdouyin\.com/share/video/|modal_id=)(\d{6,})",
    re.I,
)
_SHORT_HOSTS = {"v.douyin.com", "www.v.douyin.com"}
_USER_PAGE_RE = re.compile(r"douyin\.com/user/", re.I)


class DouyinDownloadError(RuntimeError):
    """抖音解析或下载失败。"""


def is_douyin_user_page(url: str) -> bool:
    return bool(_USER_PAGE_RE.search(url or ""))


def _session(cookiefile: Optional[Path] = None) -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": _MOBILE_UA,
            "Referer": "https://www.douyin.com/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
    )
    if cookiefile and Path(cookiefile).is_file():
        jar = MozillaCookieJar(str(cookiefile))
        try:
            jar.load(ignore_discard=True, ignore_expires=True)
            s.cookies.update(jar)
            logger.info("已加载抖音 cookiefile: %s (%d cookies)", cookiefile, len(jar))
        except Exception as e:
            logger.warning("加载抖音 cookiefile 失败（将继续尝试无 Cookie）: %s", e)
    return s


def resolve_douyin_video_id(url: str, session: Optional[requests.Session] = None) -> str:
    """从视频页 / 短链 / modal_id 中解析数字视频 ID。"""
    raw = (url or "").strip()
    if not raw:
        raise DouyinDownloadError("空链接")
    if is_douyin_user_page(raw):
        raise DouyinDownloadError(
            "这是抖音用户主页，不是视频链接。请粘贴单条视频链接"
            "（如 https://www.douyin.com/video/数字ID 或 https://v.douyin.com/短链/）。"
        )

    m = _VIDEO_ID_RE.search(raw)
    if m:
        return m.group(1)

    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    sess = session or _session()

    # 短链：跟随重定向
    if host in _SHORT_HOSTS or "v.douyin.com" in raw:
        try:
            resp = sess.get(raw, allow_redirects=True, timeout=20)
        except requests.RequestException as e:
            raise DouyinDownloadError(f"短链解析失败: {e}") from e
        final = str(resp.url or "")
        m = _VIDEO_ID_RE.search(final) or _VIDEO_ID_RE.search(resp.text or "")
        if m:
            return m.group(1)
        # Location / HTML 里再找 video/
        for candidate in [final, resp.text or ""]:
            m2 = re.search(r"/video/(\d{6,})", candidate)
            if m2:
                return m2.group(1)

    qs = parse_qs(parsed.query or "")
    if qs.get("modal_id"):
        return qs["modal_id"][0]

    raise DouyinDownloadError(
        "无法识别抖音视频 ID。请使用单条视频链接："
        "www.douyin.com/video/... 或 App 分享的 v.douyin.com 短链。"
    )


def _parse_router_data(html: str) -> dict[str, Any]:
    m = re.search(
        r"window\._ROUTER_DATA\s*=\s*(\{.*?\})\s*;?\s*</script>",
        html,
        re.S,
    )
    if not m:
        raise DouyinDownloadError("分享页未包含视频数据（可能需登录或视频不可见）")
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError as e:
        raise DouyinDownloadError(f"解析分享页 JSON 失败: {e}") from e


def _item_from_router(data: dict[str, Any]) -> dict[str, Any]:
    loader = data.get("loaderData") or {}
    page = None
    for key, val in loader.items():
        if isinstance(val, dict) and "videoInfoRes" in val:
            page = val
            break
        if isinstance(key, str) and "video" in key and isinstance(val, dict):
            page = val
    if not page:
        raise DouyinDownloadError("分享页缺少 videoInfoRes")

    info_res = page.get("videoInfoRes") or {}
    items = info_res.get("item_list") or info_res.get("aweme_list") or []
    if not items:
        # 偶发包在 filter / status
        status = info_res.get("status_code")
        msg = info_res.get("status_msg") or info_res.get("filter_list")
        raise DouyinDownloadError(
            f"分享页未返回视频条目（status={status}, msg={msg}）。"
            "可尝试上传 douyin.com cookies.txt 后重试。"
        )
    item = items[0]
    if not isinstance(item, dict):
        raise DouyinDownloadError("分享页视频条目格式异常")
    return item


def _pick_play_url(item: dict[str, Any]) -> str:
    video = item.get("video") or {}
    candidates: list[str] = []

    for key in ("play_addr", "play_addr_h264", "download_addr", "play_addr_lowbr"):
        addr = video.get(key) or {}
        urls = addr.get("url_list") if isinstance(addr, dict) else None
        if isinstance(urls, list):
            candidates.extend(u for u in urls if isinstance(u, str) and u.startswith("http"))

    bit_rates = video.get("bit_rate") or []
    if isinstance(bit_rates, list):
        for br in bit_rates:
            if not isinstance(br, dict):
                continue
            for key in ("play_addr", "play_addr_h264"):
                addr = br.get(key) or {}
                urls = addr.get("url_list") if isinstance(addr, dict) else None
                if isinstance(urls, list):
                    candidates.extend(
                        u for u in urls if isinstance(u, str) and u.startswith("http")
                    )

    if not candidates:
        raise DouyinDownloadError("未找到可播放地址")

    # 优先无水印 play（非 playwm）
    for u in candidates:
        if "/play/?" in u or "/play?" in u:
            return u
    # 把 playwm 换成 play
    for u in candidates:
        if "playwm" in u:
            return u.replace("playwm", "play")
    return candidates[0]


def _thumbnail(item: dict[str, Any]) -> str:
    video = item.get("video") or {}
    for key in ("cover", "origin_cover", "dynamic_cover"):
        cover = video.get(key) or {}
        urls = cover.get("url_list") if isinstance(cover, dict) else None
        if isinstance(urls, list) and urls:
            return urls[0]
    return ""


def fetch_douyin_share_info(
    url: str, cookiefile: Optional[Path] = None
) -> dict[str, Any]:
    """
    通过 iesdouyin 分享页解析视频元数据与直链。
    返回结构兼容 yt-dlp info_dict 的常用字段，并附带 `_direct_url`。
    """
    sess = _session(cookiefile)
    video_id = resolve_douyin_video_id(url, sess)
    share_url = f"https://www.iesdouyin.com/share/video/{video_id}/"
    logger.info("抖音分享页解析: %s -> %s", url, share_url)

    try:
        resp = sess.get(share_url, timeout=25, allow_redirects=True)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise DouyinDownloadError(f"请求分享页失败: {e}") from e

    data = _parse_router_data(resp.text)
    item = _item_from_router(data)
    play_url = _pick_play_url(item)

    author = item.get("author") or {}
    duration_ms = (item.get("video") or {}).get("duration") or 0
    try:
        duration_sec = float(duration_ms) / 1000.0 if duration_ms else 0.0
    except (TypeError, ValueError):
        duration_sec = 0.0

    stats = item.get("statistics") or {}
    title = (item.get("desc") or "").strip() or f"抖音视频_{video_id}"
    uploader = (
        author.get("nickname")
        or author.get("unique_id")
        or author.get("short_id")
        or "Unknown"
    )

    info = {
        "id": str(item.get("aweme_id") or video_id),
        "title": title,
        "description": item.get("desc") or "",
        "duration": duration_sec,
        "uploader": uploader,
        "creator": uploader,
        "thumbnail": _thumbnail(item),
        "view_count": stats.get("play_count") or 0,
        "like_count": stats.get("digg_count") or 0,
        "comment_count": stats.get("comment_count") or 0,
        "webpage_url": f"https://www.douyin.com/video/{video_id}",
        "extractor": "douyin_share",
        "_direct_url": play_url,
        "_share_url": share_url,
    }
    logger.info(
        "抖音分享页解析成功: id=%s title=%s duration=%.1fs",
        info["id"],
        title[:40],
        duration_sec,
    )
    return info


def download_douyin_direct(
    info: dict[str, Any],
    output_path: Path,
    cookiefile: Optional[Path] = None,
) -> Path:
    """用分享页直链下载到 output_path（.mp4）。"""
    direct = info.get("_direct_url")
    if not direct:
        raise DouyinDownloadError("缺少直链，无法下载")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    sess = _session(cookiefile)
    sess.headers["User-Agent"] = _DESKTOP_UA
    sess.headers["Referer"] = info.get("_share_url") or "https://www.iesdouyin.com/"

    logger.info("抖音直链下载: %s -> %s", direct[:100], output_path)
    try:
        with sess.get(direct, stream=True, timeout=120, allow_redirects=True) as resp:
            resp.raise_for_status()
            ctype = (resp.headers.get("content-type") or "").lower()
            if "html" in ctype and "video" not in ctype:
                raise DouyinDownloadError(
                    f"直链返回了 HTML 而非视频（content-type={ctype}），可能需更新 Cookie"
                )
            with open(output_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        f.write(chunk)
    except requests.RequestException as e:
        raise DouyinDownloadError(f"下载视频失败: {e}") from e

    if not output_path.is_file() or output_path.stat().st_size < 1024:
        raise DouyinDownloadError("下载文件过小或不存在")

    logger.info("抖音下载完成: %s (%d bytes)", output_path, output_path.stat().st_size)
    return output_path


def extract_and_optionally_download(
    url: str,
    *,
    cookiefile: Optional[Path] = None,
    download_to: Optional[Path] = None,
) -> dict[str, Any]:
    """解析；若提供 download_to 则同时下载。"""
    info = fetch_douyin_share_info(url, cookiefile=cookiefile)
    if download_to is not None:
        path = download_douyin_direct(info, download_to, cookiefile=cookiefile)
        info["_downloaded_path"] = str(path)
    return info
