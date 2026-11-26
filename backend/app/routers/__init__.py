"""业务路由汇总：跨模块链接 / 分组处置等专用路由必须先于通用资源路由注册。"""
from __future__ import annotations

from app.routers import cross_links, group_release, resource

ROUTERS = [group_release, cross_links, resource]
