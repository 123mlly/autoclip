"""
YouTube 投稿相关数据库模型
"""

from sqlalchemy import Column, String, Text, DateTime, Integer, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime

from .base import Base


class YouTubeAccount(Base):
    """YouTube 账号表（OAuth token）"""
    __tablename__ = "youtube_accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(String(100), unique=True, index=True)
    channel_title = Column(String(200))
    email = Column(String(200))
    # 加密存储的 refresh_token（及可选 access_token JSON）
    credentials = Column(Text, nullable=False)
    status = Column(String(20), default="active")  # active/inactive/expired
    is_default = Column(Boolean, default=False)

    last_used_at = Column(DateTime)
    upload_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    upload_records = relationship("YouTubeUploadRecord", back_populates="account")


class YouTubeUploadRecord(Base):
    """YouTube 投稿记录表"""
    __tablename__ = "youtube_upload_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(100), unique=True, index=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True)
    account_id = Column(Integer, ForeignKey("youtube_accounts.id"), nullable=False)
    clip_id = Column(String(255))

    title = Column(String(200), nullable=False)
    description = Column(Text)
    tags = Column(Text)  # JSON 字符串
    category_id = Column(String(20), default="22")  # YouTube 分类 ID
    privacy_status = Column(String(20), default="private")  # private/unlisted/public
    video_path = Column(String(500))

    video_id = Column(String(50))  # 上传成功后的 YouTube video id
    video_url = Column(String(300))
    status = Column(String(20), default="pending")  # pending/processing/completed/failed/cancelled
    error_message = Column(Text)
    progress = Column(Integer, default=0)
    file_size = Column(Integer)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    account = relationship("YouTubeAccount", back_populates="upload_records")
