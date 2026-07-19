"""
混剪模型
"""

import enum
from sqlalchemy import Column, String, Integer, ForeignKey, Enum, JSON, Text
from sqlalchemy.orm import relationship
from .base import BaseModel


class MontageStatus(str, enum.Enum):
    DRAFT = "draft"
    RENDERING = "rendering"
    COMPLETED = "completed"
    FAILED = "failed"


class Montage(BaseModel):
    __tablename__ = "montages"

    name = Column(String(255), nullable=False, comment="混剪名称")
    description = Column(Text, nullable=True, comment="混剪描述")
    status = Column(
        Enum(MontageStatus),
        default=MontageStatus.DRAFT,
        nullable=False,
        comment="混剪状态",
    )
    timeline = Column(JSON, nullable=False, default=dict, comment="时间轴 JSON")
    total_duration = Column(Integer, nullable=True, comment="总时长（秒）")
    export_path = Column(String(500), nullable=True, comment="导出视频路径")
    thumbnail_path = Column(String(500), nullable=True, comment="缩略图路径")
    error_message = Column(Text, nullable=True, comment="错误信息")
    montage_metadata = Column(JSON, nullable=True, comment="扩展元数据")

    project_id = Column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属项目 ID",
    )

    project = relationship("Project", back_populates="montages")

    def __repr__(self):
        return f"<Montage(id={self.id}, name='{self.name}', status={self.status})>"
