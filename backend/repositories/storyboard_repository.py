"""
解说分镜 Repository
"""

from typing import List, Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from .base import BaseRepository
from ..models.storyboard import Storyboard


class StoryboardRepository(BaseRepository[Storyboard]):
    def __init__(self, db: Session):
        super().__init__(Storyboard, db)

    def get_paginated_by_project(
        self,
        project_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[List[Storyboard], int]:
        query = self.db.query(self.model).filter(self.model.project_id == project_id)
        total = query.count()
        items = (
            query.order_by(desc(self.model.updated_at))
            .offset(skip)
            .limit(limit)
            .all()
        )
        return items, total
