"""
解说分镜 Pydantic schemas
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import Field

from .base import BaseSchema, PaginationResponse


class StoryboardStatus(str, Enum):
    DRAFT = "draft"
    GENERATING = "generating"
    READY = "ready"
    RENDERING = "rendering"
    COMPLETED = "completed"
    FAILED = "failed"


class StoryboardShot(BaseSchema):
    id: str = Field(..., description="镜头 ID")
    index: int = Field(..., ge=1, description="序号")
    start_time: float = Field(..., ge=0, description="开始时间（秒）")
    end_time: float = Field(..., ge=0, description="结束时间（秒）")
    narration: str = Field(default="", description="旁白文案")
    subtitle_ref: Optional[str] = Field(default=None, description="对应原字幕摘要")
    thumbnail_path: Optional[str] = Field(default=None, description="缩略图路径")


class StoryboardConfig(BaseSchema):
    duration_ratio: float = Field(default=0.5, ge=0.1, le=1.0, description="目标时长占原片比例")
    scene_align: bool = Field(default=True, description="场景对齐（贴字幕边界）")
    subtitle_align: bool = Field(default=True, description="字幕场景对齐")
    golden_opening: bool = Field(default=True, description="黄金 5 秒爆款开头")
    aspect_ratio: str = Field(default="9:16", description="输出比例 9:16 / 16:9")
    custom_prompt: Optional[str] = Field(default=None, description="合并后的 AI 提示（系统生成）")
    user_custom_prompt: Optional[str] = Field(default=None, description="用户补充要求")
    model_name: Optional[str] = Field(default=None, description="推理模型")
    voice_style: Optional[str] = Field(
        default=None,
        description="旁白文风 colloquial / punchy / suspense / documentary / minimal",
    )
    max_shots: Optional[int] = Field(default=None, ge=4, le=30, description="分镜数量")
    narration_max_chars: Optional[int] = Field(
        default=None, ge=4, le=80, description="单镜旁白最大字数"
    )


class StoryboardCreate(BaseSchema):
    project_id: str = Field(..., description="项目 ID")
    name: Optional[str] = Field(default=None, max_length=200)
    config: Optional[StoryboardConfig] = None


class StoryboardAIGenerateRequest(BaseSchema):
    project_id: str = Field(..., description="项目 ID")
    name: Optional[str] = Field(default=None, max_length=200)
    custom_prompt: Optional[str] = Field(default=None, max_length=2000, description="合并后的 AI 提示")
    user_custom_prompt: Optional[str] = Field(default=None, max_length=2000, description="用户补充要求")
    duration_ratio: float = Field(default=0.5, ge=0.1, le=1.0)
    scene_align: bool = Field(default=True)
    subtitle_align: bool = Field(default=True)
    golden_opening: bool = Field(default=True)
    aspect_ratio: str = Field(default="9:16")
    max_shots: int = Field(default=16, ge=4, le=30)
    narration_max_chars: int = Field(default=10, ge=4, le=80, description="单镜旁白最大字数")
    auto_render: bool = Field(default=False)
    model_name: Optional[str] = Field(default=None, description="推理模型，默认使用设置页当前模型")
    voice_style: str = Field(
        default="colloquial",
        description="旁白文风 colloquial / punchy / suspense / documentary / minimal",
    )


class StoryboardUpdate(BaseSchema):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)
    config: Optional[StoryboardConfig] = None
    shots: Optional[List[StoryboardShot]] = None


class StoryboardBatchTranslateRequest(BaseSchema):
    target_language: str = Field(default="en", description="目标语言，如 en / ja")
    replace: bool = Field(default=True, description="是否直接替换旁白")


class StoryboardBatchReplaceRequest(BaseSchema):
    find_text: str = Field(..., min_length=1, max_length=200)
    replace_text: str = Field(default="", max_length=500)


class StoryboardExportClipResponse(BaseSchema):
    clip_id: str = Field(..., description="可用于投稿的切片 ID")
    title: str = Field(..., description="投稿默认标题")


class StoryboardResponse(BaseSchema):
    id: str
    project_id: str
    name: str
    description: Optional[str] = None
    status: StoryboardStatus
    config: dict
    shots: List[dict]
    source_video_path: Optional[str] = None
    subtitle_path: Optional[str] = None
    total_duration: Optional[int] = None
    export_path: Optional[str] = None
    thumbnail_path: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    shot_count: int = 0


class StoryboardListResponse(BaseSchema):
    items: List[StoryboardResponse]
    pagination: PaginationResponse


class StoryboardProjectSummary(BaseSchema):
    project_id: str
    name: str
    created_at: datetime
    updated_at: datetime
    thumbnail: Optional[str] = None
    storyboard_id: Optional[str] = None
    storyboard_name: Optional[str] = None
    storyboard_status: Optional[StoryboardStatus] = None
    shot_count: int = 0
    total_duration: Optional[int] = None


class StoryboardProjectListResponse(BaseSchema):
    items: List[StoryboardProjectSummary]
    pagination: PaginationResponse


class StoryboardVideoSource(BaseSchema):
    id: str
    filename: str
    original_name: str
    size: int = 0
    order: int = 0
    uploaded_at: datetime


class StoryboardVideoSourceListResponse(BaseSchema):
    project_id: str
    items: List[StoryboardVideoSource]
    source_count: int = 0


class StoryboardVideoUploadResponse(BaseSchema):
    project_id: str
    source_count: int
    items: List[StoryboardVideoSource]
