"""
统一路径管理工具
解决项目中路径构建不一致的问题
"""

import os
from pathlib import Path
from typing import Optional

def get_project_root() -> Path:
    """
    获取项目根目录
    从backend目录向上查找，直到找到包含frontend和backend的目录
    """
    current_path = Path(__file__).parent  # backend/core/
    
    # 向上查找项目根目录
    while current_path.parent != current_path:  # 未到达根目录
        if (current_path.parent / "frontend").exists() and (current_path.parent / "backend").exists():
            return current_path.parent
        current_path = current_path.parent
    
    # 如果没找到，使用默认路径
    return Path(__file__).parent.parent.parent

def get_data_directory() -> Path:
    """获取数据目录"""
    # 统一使用项目根目录下的data目录，与config.py保持一致
    project_root = get_project_root()
    data_dir = project_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir

def get_projects_directory() -> Path:
    """获取项目目录"""
    projects_dir = get_data_directory() / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    return projects_dir

def get_output_directory() -> Path:
    """获取输出目录"""
    output_dir = get_project_root() / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir

def get_project_directory(project_id: str) -> Path:
    """获取项目目录"""
    project_dir = get_projects_directory() / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    return project_dir

def get_project_raw_directory(project_id: str) -> Path:
    """获取项目原始文件目录"""
    raw_dir = get_project_directory(project_id) / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir

def get_project_output_directory(project_id: str) -> Path:
    """获取项目输出目录"""
    output_dir = get_project_directory(project_id) / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir

def get_clips_directory() -> Path:
    """获取切片目录"""
    clips_dir = get_output_directory() / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    return clips_dir

def get_collections_directory() -> Path:
    """获取合集目录"""
    collections_dir = get_output_directory() / "collections"
    collections_dir.mkdir(parents=True, exist_ok=True)
    return collections_dir

def get_metadata_directory() -> Path:
    """获取元数据目录"""
    metadata_dir = get_output_directory() / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    return metadata_dir

def get_settings_file_path() -> Path:
    """获取设置文件路径"""
    return get_data_directory() / "settings.json"

def get_uploads_directory() -> Path:
    """获取上传目录"""
    uploads_dir = get_data_directory() / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    return uploads_dir

def get_temp_directory() -> Path:
    """获取临时目录"""
    temp_dir = get_data_directory() / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir

def ensure_directory_exists(path: Path) -> Path:
    """确保目录存在"""
    path.mkdir(parents=True, exist_ok=True)
    return path

def get_video_file_path(project_id: str, filename: str) -> Path:
    """获取项目视频文件路径"""
    return get_project_raw_directory(project_id) / filename

def get_srt_file_path(project_id: str, filename: str) -> Path:
    """获取项目SRT文件路径"""
    return get_project_raw_directory(project_id) / filename

def get_clip_file_path(clip_id: str, title: str) -> Path:
    """获取切片文件路径"""
    # 清理文件名，移除特殊字符
    safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).rstrip()
    safe_title = safe_title.replace(' ', '_')
    return get_clips_directory() / f"{clip_id}_{safe_title}.mp4"

def get_collection_file_path(collection_id: str, title: str) -> Path:
    """获取合集文件路径"""
    # 清理文件名，移除特殊字符
    safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).rstrip()
    safe_title = safe_title.replace(' ', '_')
    return get_collections_directory() / f"{collection_id}_{safe_title}.mp4"

def get_metadata_file_path(project_id: str) -> Path:
    """获取项目元数据文件路径"""
    return get_metadata_directory() / f"{project_id}_metadata.json"

def get_log_file_path() -> Path:
    """获取日志文件路径"""
    return get_project_root() / "backend.log"

def get_cache_directory() -> Path:
    """获取缓存目录"""
    cache_dir = get_data_directory() / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir

def get_backup_directory() -> Path:
    """获取备份目录"""
    backup_dir = get_data_directory() / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir

def cleanup_temp_files(max_age_hours: int = 24):
    """清理临时文件"""
    import time
    temp_dir = get_temp_directory()
    current_time = time.time()
    
    for file_path in temp_dir.iterdir():
        if file_path.is_file():
            file_age = current_time - file_path.stat().st_mtime
            if file_age > (max_age_hours * 3600):
                try:
                    file_path.unlink()
                except Exception as e:
                    print(f"清理临时文件失败: {file_path}, 错误: {e}")

def validate_file_path(file_path: Path) -> bool:
    """验证文件路径是否安全"""
    try:
        # 检查路径是否在允许的目录内
        allowed_dirs = [
            get_data_directory(),
            get_output_directory(),
            get_project_root()
        ]
        
        file_path = file_path.resolve()
        return any(file_path.is_relative_to(allowed_dir) for allowed_dir in allowed_dirs)
    except Exception:
        return False


def resolve_data_file_path(stored_path: Optional[str], project_id: Optional[str] = None) -> Optional[Path]:
    """
    兼容本机绝对路径与 Docker 挂载路径。

    库里可能存着宿主机路径（如 /Users/.../autoclip/data/projects/...），
    容器内实际在 /app/data/projects/...。将任意含 /data/ 的路径重映射到当前 data 目录。
    """
    if not stored_path:
        return None

    path = Path(stored_path)
    if path.exists():
        return path

    parts = path.parts
    if "data" in parts:
        idx = parts.index("data")
        relative_parts = parts[idx + 1 :]
        if relative_parts:
            candidate = get_data_directory().joinpath(*relative_parts)
            if candidate.exists():
                return candidate

    if project_id and path.name:
        project_dir = get_project_directory(project_id)
        for sub in ("output/clips", "output/collections", "raw", "output/metadata"):
            candidate = project_dir / sub / path.name
            if candidate.exists():
                return candidate

    return None


def resolve_clip_video_file(
    project_id: str,
    clip_id: str,
    video_path: Optional[str] = None,
    title: Optional[str] = None,
) -> Optional[Path]:
    """定位切片视频：支持 {clip_id}_*.mp4、序号_标题.mp4，以及宿主机/容器路径重映射。"""
    clips_dir = get_project_directory(project_id) / "output" / "clips"

    if clips_dir.exists():
        by_id = list(clips_dir.glob(f"{clip_id}_*.mp4"))
        if by_id:
            return by_id[0]
        exact = clips_dir / f"{clip_id}.mp4"
        if exact.exists():
            return exact

    remapped = resolve_data_file_path(video_path, project_id=project_id)
    if remapped and remapped.exists():
        return remapped

    if clips_dir.exists() and title:
        mp4_files = list(clips_dir.glob("*.mp4"))
        # 完整标题命中
        for mp4 in mp4_files:
            if title in mp4.stem:
                return mp4
        # 标题前缀关键词命中
        keywords = [k for k in title.replace("：", " ").replace(":", " ").split() if len(k) >= 2][:4]
        if keywords:
            for mp4 in mp4_files:
                if sum(1 for k in keywords if k in mp4.name) >= min(2, len(keywords)):
                    return mp4

    return None

