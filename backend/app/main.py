"""智考通后端入口（数学学科 MVP）。

启动：uvicorn app.main:app --reload
文档：http://127.0.0.1:8000/docs
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import router
from app.core.config import settings

app = FastAPI(
    title="智考通 · 基于认知诊断的高考自适应备考助手（数学 MVP）",
    description=("绝不押题/预测原题；核心是基于认知诊断的个性化提分。"
                 "解题强制苏格拉底引导，全链路合规（高考熔断 + 防沉迷）。"),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.include_router(router, prefix="/api/v1")


@app.get("/")
def root() -> dict:
    return {
        "name": "智考通 ZhiKaoTong",
        "subject": "math (MVP)",
        "env": settings.app_env,
        "docs": "/docs",
        "principles": ["不押题不预测", "绝不直接给答案·强制苏格拉底引导",
                       "高考期间熔断", "防沉迷", "数据最小化"],
    }
