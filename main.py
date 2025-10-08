"""Production-Ready FastAPI M3U8 Video Merger"""
import os
import uuid
import logging
import asyncio
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl, Field
from contextlib import asynccontextmanager
import tempfile
import shutil
import redis.asyncio as redis

from config import settings
from video_processor import VideoProcessor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

redis_client: Optional[redis.Redis] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client
    Path("output").mkdir(exist_ok=True)
    Path("logs").mkdir(exist_ok=True)
    Path("temp").mkdir(exist_ok=True)
    redis_client = await redis.from_url(settings.REDIS_URL, decode_responses=True)
    yield
    if redis_client:
        await redis_client.close()

app = FastAPI(title="M3U8 Video Merger API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class RedditVideo(BaseModel):
    hls_url: HttpUrl

class SecureMedia(BaseModel):
    reddit_video: RedditVideo

class VideoItem(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    author_fullname: Optional[str] = None
    secure_media: SecureMedia
    url: HttpUrl

class MergeRequest(BaseModel):
    videos: List[VideoItem] = Field(..., min_items=1, max_items=10)
    transition_duration: float = Field(default=0.5, ge=0.1, le=2.0)
    overlay_duration: float = Field(default=2.0, ge=0.5, le=5.0)

class JobStatus(BaseModel):
    job_id: str
    status: str
    progress: Optional[str] = None
    output_file: Optional[str] = None
    error: Optional[str] = None

async def get_redis():
    if redis_client is None:
        raise HTTPException(status_code=503, detail="Redis not available")
    return redis_client

async def store_job(redis_conn: redis.Redis, job_id: str, status: str, progress: str = "", output: str = "", error: str = ""):
    await redis_conn.hset(f"job:{job_id}", mapping={"status": status, "progress": progress, "output_file": output, "error": error})
    await redis_conn.expire(f"job:{job_id}", settings.JOB_RETENTION_SECONDS)

async def get_job(redis_conn: redis.Redis, job_id: str):
    return await redis_conn.hgetall(f"job:{job_id}")

async def process_merge_job(job_id: str, request: MergeRequest):
    redis_conn = await redis.from_url(settings.REDIS_URL, decode_responses=True)
    temp_dir = None
    try:
        await store_job(redis_conn, job_id, "downloading", "Starting...")
        temp_dir = tempfile.mkdtemp(dir="temp")
        processor = VideoProcessor(settings.REELS_WIDTH, settings.REELS_HEIGHT, temp_dir)
        
        downloaded = []
        for i, video in enumerate(request.videos):
            await store_job(redis_conn, job_id, "downloading", f"Downloading {i+1}/{len(request.videos)}")
            downloaded.append(await processor.download_m3u8(str(video.secure_media.reddit_video.hls_url), i))
        
        await store_job(redis_conn, job_id, "processing", "Processing videos...")
        processed = []
        for i, (path, data) in enumerate(zip(downloaded, request.videos)):
            await store_job(redis_conn, job_id, "processing", f"Processing {i+1}/{len(request.videos)}")
            processed.append(await processor.process_video(path, i, data.title, request.overlay_duration))
        
        await store_job(redis_conn, job_id, "merging", "Merging videos...")
        output_path = f"output/{job_id}.mp4"
        await processor.merge_videos(processed, request.transition_duration, output_path)
        
        await store_job(redis_conn, job_id, "completed", "Done!", output=output_path)
    except Exception as e:
        await store_job(redis_conn, job_id, "failed", error=str(e))
    finally:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        await redis_conn.close()

@app.get("/")
async def root():
    return {"name": "M3U8 Video Merger API", "status": "operational"}

@app.get("/health")
async def health(redis_conn: redis.Redis = Depends(get_redis)):
    try:
        await redis_conn.ping()
        redis_status = "healthy"
    except:
        redis_status = "unhealthy"
    return {"status": "healthy" if redis_status == "healthy" else "degraded", "redis": redis_status}

@app.post("/api/merge", response_model=JobStatus)
async def create_merge_job(request: MergeRequest, background_tasks: BackgroundTasks, redis_conn: redis.Redis = Depends(get_redis)):
    job_id = str(uuid.uuid4())
    await store_job(redis_conn, job_id, "queued", "Queued")
    background_tasks.add_task(process_merge_job, job_id, request)
    return JobStatus(job_id=job_id, status="queued", progress="Queued")

@app.get("/api/status/{job_id}", response_model=JobStatus)
async def get_status(job_id: str, redis_conn: redis.Redis = Depends(get_redis)):
    job = await get_job(redis_conn, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatus(job_id=job_id, status=job.get("status", "unknown"), progress=job.get("progress"), output_file=job.get("output_file"), error=job.get("error"))

@app.get("/api/download/{job_id}")
async def download(job_id: str, redis_conn: redis.Redis = Depends(get_redis)):
    job = await get_job(redis_conn, job_id)
    if not job or job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Job not completed")
    output_file = job.get("output_file")
    if not output_file or not os.path.exists(output_file):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(output_file, media_type="video/mp4", filename=f"merged_{job_id}.mp4")
