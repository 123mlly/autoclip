"""
混剪 Pydantic schemas
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import Field

from .base import BaseSchema, PaginationResponse


class MontageStatus(str, Enum):
    DRAFT = "draft"
    RENDERING = "rendering"
    COMPLETED = "completed"
    FAILED = "failed"


class MontageSegment(BaseSchema):
    id: str = Field(..., description="片段 ID")
    clip_id: str = Field(..., description="切片 ID")
    project_id: Optional[str] = Field(default=None, description="切片所属项目，默认同混剪项目")
    in_offset: float = Field(default=0, ge=0, description="切片内起始秒")
    out_offset: Optional[float] = Field(default=None, ge=0, description="切片内结束秒，空为整段")
    transition: str = Field(default="none", description="转场类型: none / fade")
    transition_duration: float = Field(default=0.5, ge=0.1, le=3.0, description="转场时长（秒）")


class MontageAudioSettings(BaseSchema):
    bgm_path: Optional[str] = Field(default=None, description="BGM 文件路径")
    bgm_filename: Optional[str] = Field(default=None, description="BGM 原始文件名")
    bgm_volume: float = Field(default=0.25, ge=0, le=1, description="BGM 音量 0-1")
    keep_original: bool = Field(default=True, description="是否保留原声")


class MontageOutputSettings(BaseSchema):
    aspect_ratio: str = Field(default="9:16", description="输出比例: 9:16 / 16:9")


class MontageTimeline(BaseSchema):
    segments: List[MontageSegment] = Field(default_factory=list)
    audio: Optional[MontageAudioSettings] = None
    output: Optional[MontageOutputSettings] = None


class MontageCreate(BaseSchema):
    project_id: str = Field(..., description="项目 ID")
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)
    timeline: Optional[MontageTimeline] = None


class MontageUpdate(BaseSchema):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)
    timeline: Optional[MontageTimeline] = None


class MontageResponse(BaseSchema):
    id: str
    project_id: str
    name: str
    description: Optional[str] = None
    status: MontageStatus
    timeline: dict
    total_duration: Optional[int] = None
    export_path: Optional[str] = None
    thumbnail_path: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    segment_count: int = 0


class MontageListResponse(BaseSchema):
    items: List[MontageResponse]
    pagination: PaginationResponse


class MontageFilter(BaseSchema):
    project_id: Optional[str] = None


class MontageClipItem(BaseSchema):
    id: str
    title: str
    duration: int = 0
    score: Optional[float] = None
    project_id: str
    project_name: str


class MontageClipSourceGroup(BaseSchema):
    project_id: str
    project_name: str
    clips: List[MontageClipItem]


class MontageClipSourcesResponse(BaseSchema):
    current_project: MontageClipSourceGroup
    other_projects: List[MontageClipSourceGroup] = Field(default_factory=list)


class MontageAIGenerateRequest(BaseSchema):
    project_id: str = Field(..., description="混剪所属项目 ID")
    prompt: str = Field(..., min_length=2, max_length=2000, description="混剪需求描述")
    aspect_ratio: str = Field(default="9:16", description="输出比例: 9:16 / 16:9")
    target_duration: int = Field(default=60, ge=15, le=600, description="目标总时长（秒）")
    max_segments: int = Field(default=8, ge=2, le=20, description="最多片段数")
    include_other_projects: bool = Field(default=False, description="是否允许跨项目选片")
    auto_render: bool = Field(default=False, description="生成后是否自动提交渲染")
