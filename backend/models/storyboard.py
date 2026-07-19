"""
解说分镜模型
"""

import enum
from sqlalchemy import Column, String, Integer, ForeignKey, Enum, JSON, Text
from sqlalchemy.orm import relationship
from .base import BaseModel


class StoryboardStatus(str, enum.Enum):
    DRAFT = "draft"
    GENERATING = "generating"
    READY = "ready"
    RENDERING = "rendering"
    COMPLETED = "completed"
    FAILED = "failed"


class Storyboard(BaseModel):
    __tablename__ = "storyboards"

    name = Column(String(255), nullable=False, comment="分镜名称")
    description = Column(Text, nullable=True, comment="分镜描述")
    status = Column(
        Enum(StoryboardStatus),
        default=StoryboardStatus.DRAFT,
        nullable=False,
        comment="状态",
    )
    config = Column(JSON, nullable=False, default=dict, comment="生成配置")
    shots = Column(JSON, nullable=False, default=list, comment="分镜镜头列表")
    source_video_path = Column(String(500), nullable=True, comment="源视频路径")
    subtitle_path = Column(String(500), nullable=True, comment="字幕路径")
    total_duration = Column(Integer, nullable=True, comment="成片总时长（秒）")
    export_path = Column(String(500), nullable=True, comment="导出视频路径")
    thumbnail_path = Column(String(500), nullable=True, comment="封面路径")
    error_message = Column(Text, nullable=True, comment="错误信息")
    storyboard_metadata = Column(JSON, nullable=True, comment="扩展元数据")

    project_id = Column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属项目 ID",
    )

    project = relationship("Project", back_populates="storyboards")

    def __repr__(self):
        return f"<Storyboard(id={self.id}, name='{self.name}', status={self.status})>"
