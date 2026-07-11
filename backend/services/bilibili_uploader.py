"""
B站投稿上传器
基于 UPOS 分片协议（preupload → 分片 → 合并 → 提交）
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class BilibiliUploader:
    """同步 B 站上传器，适合 Celery worker 调用。"""

    def __init__(self, cookies: str):
        self.cookies = cookies.strip()
        self.bv_id: Optional[str] = None
        self.av_id: Optional[str] = None
        self.error_message: Optional[str] = None
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Cookie": self.cookies,
            "Referer": "https://member.bilibili.com/",
            "Origin": "https://member.bilibili.com",
        })

    def _csrf(self) -> Optional[str]:
        for part in self.cookies.split(";"):
            part = part.strip()
            if part.startswith("bili_jct="):
                return part.split("=", 1)[1]
        return None

    def upload_video(self, video_path: str, metadata: Dict[str, Any], max_retries: int = 3) -> bool:
        """上传并投稿。metadata 需含 title/desc/tid/tag。"""
        try:
            path = Path(video_path)
            if not path.exists() or path.stat().st_size == 0:
                self.error_message = f"视频文件不存在或为空: {video_path}"
                return False

            if not self._check_login():
                return False

            pre = self._preupload(path)
            if not pre:
                return False

            upload_id = self._init_upload(pre)
            if not upload_id:
                return False

            parts = self._upload_chunks(path, pre, upload_id, max_retries=max_retries)
            if not parts:
                return False

            if not self._complete_upload(path, pre, upload_id, parts):
                return False

            return self._submit(pre, metadata)
        except Exception as e:
            self.error_message = str(e)
            logger.exception("上传视频失败")
            return False

    # 兼容旧接口命名
    def upload_video_sync(self, video_path: str, metadata: Dict[str, Any], max_retries: int = 3) -> bool:
        return self.upload_video(video_path, metadata, max_retries=max_retries)

    async def upload_video_async(self, video_path: str, metadata: Dict[str, Any], max_retries: int = 3) -> bool:
        return self.upload_video(video_path, metadata, max_retries=max_retries)

    def _check_login(self) -> bool:
        try:
            resp = self.session.get(
                "https://api.bilibili.com/x/web-interface/nav",
                timeout=15,
            )
            data = resp.json()
            if data.get("code") == 0 and data.get("data", {}).get("isLogin"):
                logger.info("B站登录状态正常: %s", data["data"].get("uname"))
                return True
            self.error_message = "B站账号未登录或 Cookie 已失效，请重新导入 Cookie"
            logger.error(self.error_message)
            return False
        except Exception as e:
            self.error_message = f"检查登录状态失败: {e}"
            logger.error(self.error_message)
            return False

    def _preupload(self, path: Path) -> Optional[Dict[str, Any]]:
        try:
            params = {
                "name": path.name,
                "size": str(path.stat().st_size),
                "r": "upos",
                "profile": "ugcupos/bup",
                "ssl": "0",
                "version": "2.14.0",
                "build": "2140000",
                "upcdn": "bda2",
                "probe_version": "20221109",
            }
            resp = self.session.get(
                "https://member.bilibili.com/preupload",
                params=params,
                timeout=30,
            )
            result = resp.json()
            if result.get("OK") != 1:
                self.error_message = f"预上传失败: {result.get('message') or result}"
                logger.error("%s | raw=%s", self.error_message, result)
                return None

            endpoint = result.get("endpoint") or ""
            if "," in endpoint:
                endpoint = endpoint.split(",")[0]
            if endpoint.startswith("//"):
                endpoint = "https:" + endpoint
            elif not endpoint.startswith("http"):
                endpoint = "https://" + endpoint.lstrip("/")

            upos_uri = result.get("upos_uri") or ""
            upos_path = upos_uri[7:] if upos_uri.startswith("upos://") else upos_uri

            info = {
                "endpoint": endpoint.rstrip("/"),
                "upos_uri": upos_uri,
                "upos_path": upos_path,
                "auth": result.get("auth") or "",
                "biz_id": result.get("biz_id"),
                "chunk_size": int(result.get("chunk_size") or 10 * 1024 * 1024),
            }
            logger.info("预上传成功: biz_id=%s endpoint=%s", info["biz_id"], info["endpoint"])
            return info
        except Exception as e:
            self.error_message = f"预上传异常: {e}"
            logger.error(self.error_message)
            return None

    def _init_upload(self, pre: Dict[str, Any]) -> Optional[str]:
        try:
            url = f"{pre['endpoint']}/{pre['upos_path']}?uploads&output=json"
            headers = {"X-Upos-Auth": pre["auth"]}
            resp = self.session.post(url, headers=headers, timeout=30)
            result = resp.json()
            upload_id = result.get("upload_id")
            if not upload_id:
                self.error_message = f"初始化分片上传失败: {result}"
                logger.error(self.error_message)
                return None
            logger.info("初始化分片上传成功: upload_id=%s", upload_id)
            return upload_id
        except Exception as e:
            self.error_message = f"初始化分片上传异常: {e}"
            logger.error(self.error_message)
            return None

    def _upload_chunks(
        self,
        path: Path,
        pre: Dict[str, Any],
        upload_id: str,
        max_retries: int = 3,
    ) -> Optional[List[Dict[str, Any]]]:
        try:
            file_size = path.stat().st_size
            chunk_size = pre["chunk_size"]
            total_chunks = (file_size + chunk_size - 1) // chunk_size
            parts: List[Dict[str, Any]] = []

            with open(path, "rb") as f:
                for index in range(total_chunks):
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    start = index * chunk_size
                    end = start + len(chunk) - 1
                    part_number = index + 1

                    params = (
                        f"partNumber={part_number}"
                        f"&uploadId={quote(str(upload_id))}"
                        f"&chunk={index}"
                        f"&chunks={total_chunks}"
                        f"&size={len(chunk)}"
                        f"&start={start}"
                        f"&end={end}"
                        f"&total={file_size}"
                    )
                    url = f"{pre['endpoint']}/{pre['upos_path']}?{params}"
                    headers = {
                        "X-Upos-Auth": pre["auth"],
                        "Content-Type": "application/octet-stream",
                        "Content-Length": str(len(chunk)),
                    }

                    ok = False
                    last_error = ""
                    for attempt in range(max_retries):
                        try:
                            resp = self.session.put(url, headers=headers, data=chunk, timeout=120)
                            if resp.status_code in (200, 201, 204):
                                etag = resp.headers.get("ETag") or resp.headers.get("etag") or "etag"
                                parts.append({"partNumber": part_number, "eTag": etag})
                                ok = True
                                logger.debug("分片 %s/%s 上传成功", part_number, total_chunks)
                                break
                            last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                        except Exception as e:
                            last_error = str(e)
                        time.sleep(min(2 ** attempt, 8))

                    if not ok:
                        self.error_message = f"分片 {part_number}/{total_chunks} 上传失败: {last_error}"
                        logger.error(self.error_message)
                        return None

            logger.info("全部分片上传完成: %s", total_chunks)
            return parts
        except Exception as e:
            self.error_message = f"分片上传异常: {e}"
            logger.error(self.error_message)
            return None

    def _complete_upload(
        self,
        path: Path,
        pre: Dict[str, Any],
        upload_id: str,
        parts: List[Dict[str, Any]],
    ) -> bool:
        try:
            name = quote(path.name)
            params = (
                f"output=json&name={name}&profile=ugcupos%2Fbup"
                f"&uploadId={quote(str(upload_id))}&biz_id={pre['biz_id']}"
            )
            url = f"{pre['endpoint']}/{pre['upos_path']}?{params}"
            headers = {
                "X-Upos-Auth": pre["auth"],
                "Content-Type": "application/json",
            }
            resp = self.session.post(url, headers=headers, data=json.dumps({"parts": parts}), timeout=60)
            result = resp.json()
            # OK 可能是 1 或 "1"
            if str(result.get("OK")) == "1" or result.get("code") == 0:
                logger.info("分片合并成功")
                return True
            self.error_message = f"分片合并失败: {result}"
            logger.error(self.error_message)
            return False
        except Exception as e:
            self.error_message = f"分片合并异常: {e}"
            logger.error(self.error_message)
            return False

    def _submit(self, pre: Dict[str, Any], metadata: Dict[str, Any]) -> bool:
        try:
            csrf = self._csrf()
            if not csrf:
                self.error_message = "Cookie 中缺少 bili_jct，请重新导入完整 Cookie"
                return False

            upos_uri = pre.get("upos_uri") or ""
            filename = Path(upos_uri.split("/")[-1]).stem

            tags = metadata.get("tag") or metadata.get("tags") or ""
            if isinstance(tags, list):
                tags = ",".join(str(t).strip() for t in tags if str(t).strip())

            title = (metadata.get("title") or "未命名视频")[:80]
            desc = metadata.get("desc") or metadata.get("description") or title
            tid = int(metadata.get("tid") or metadata.get("partition_id") or 21)

            payload = {
                "copyright": int(metadata.get("copyright") or 1),
                "videos": [{
                    "filename": filename,
                    "title": title,
                    "desc": desc,
                    "cid": pre.get("biz_id"),
                }],
                "source": metadata.get("source") or "",
                "tid": tid,
                "cover": metadata.get("cover") or "",
                "title": title,
                "tag": tags or "autoclip",
                "desc_format_id": 0,
                "desc": desc,
                "dynamic": "",
                "subtitle": {"open": 0, "lan": ""},
                "no_reprint": 0,
                "open_elec": 1,
            }

            url = f"https://member.bilibili.com/x/vu/web/add/v3?t={int(time.time() * 1000)}&csrf={csrf}"
            headers = {
                "Content-Type": "application/json;charset=UTF-8",
                "X-CSRF-Token": csrf,
            }
            resp = self.session.post(url, headers=headers, data=json.dumps(payload), timeout=60)
            result = resp.json()
            if result.get("code") == 0:
                data = result.get("data") or {}
                self.bv_id = data.get("bvid")
                self.av_id = str(data.get("aid") or "")
                logger.info("投稿成功: BV=%s AV=%s", self.bv_id, self.av_id)
                return True

            self.error_message = f"投稿提交失败: {result.get('message') or result}"
            logger.error("%s | payload_tid=%s", self.error_message, tid)
            return False
        except Exception as e:
            self.error_message = f"投稿提交异常: {e}"
            logger.error(self.error_message)
            return False


# 兼容旧类名
BilibiliDirectUploader = BilibiliUploader
