"""Main API router

This module combines all API routers (REST v1 and OpenAI-compatible)
"""
from fastapi import APIRouter

from backend.api.v1 import llm, images, videos, tasks, workflow, settings, tts
from backend.api.routes import projects
from backend.api.openai import chat, images as openai_images, videos as openai_videos

# Create main API router
api_router = APIRouter()

# REST API v1 routes
v1_router = APIRouter(prefix="/api/v1", tags=["REST API v1"])
v1_router.include_router(llm.router, prefix="/llm", tags=["LLM"])
v1_router.include_router(images.router, prefix="/images", tags=["Images"])
v1_router.include_router(videos.router, prefix="/videos", tags=["Videos"])
v1_router.include_router(tasks.router, prefix="/tasks", tags=["Tasks"])
v1_router.include_router(workflow.router, prefix="/workflow", tags=["Workflow"])
v1_router.include_router(settings.router, prefix="/settings", tags=["Settings"])
v1_router.include_router(tts.router, prefix="/tts", tags=["TTS"])
v1_router.include_router(projects.router, tags=["Projects"])  # Projects router

# OpenAI-compatible routes
openai_router = APIRouter(prefix="/v1", tags=["OpenAI Compatible"])
openai_router.include_router(chat.router, tags=["OpenAI Chat"])
openai_router.include_router(openai_images.router, tags=["OpenAI Images"])
openai_router.include_router(openai_videos.router, prefix="/videos", tags=["OpenAI Videos"])

# Include all routers
api_router.include_router(v1_router)
api_router.include_router(openai_router)

