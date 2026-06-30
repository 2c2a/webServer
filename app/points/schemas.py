"""积分系统 Pydantic Schema。"""
from __future__ import annotations

from pydantic import BaseModel


class PointTaskOut(BaseModel):
    id: int
    name: str
    description: str | None
    detection_method: str
    points: int
    is_active: bool
    config: dict | None
    site_group_id: int | None

    model_config = {"from_attributes": True}


class PointTaskCreate(BaseModel):
    name: str
    description: str | None = None
    detection_method: str
    points: int = 0
    is_active: bool = True
    config: dict | None = None


class PointTaskUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    detection_method: str | None = None
    points: int | None = None
    is_active: bool | None = None
    config: dict | None = None


class PointRecordOut(BaseModel):
    id: int
    user_id: int
    delta: int
    balance_after: int
    source: str
    task_id: int | None
    ref_type: str | None
    ref_id: int | None
    description: str | None
    site_group_id: int | None
    created_at: str

    model_config = {"from_attributes": True}


class UserPointsOut(BaseModel):
    user_id: int
    site_group_id: int | None
    balance: int

    model_config = {"from_attributes": True}


class DetectorMethodOut(BaseModel):
    method_id: str
    name: str
    description: str
    passive: bool


class AdminAwardRequest(BaseModel):
    user_id: int
    delta: int
    description: str | None = None
