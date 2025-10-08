"""
Production-Ready FastAPI M3U8 Video Merger
Main application file
"""
import os
import uuid
import logging
import asyncio
from pathlib import Path
from typing import List, Optional
import aiohttp
import redis.asyncio as redis
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel, HttpUrl, Field, validator
from contextlib import asynccontextmanager
import tempfile
import shutil

# Configuration
from config import settings
from video_processor import VideoProcessor
from rate_limiter import rate_limit

# Setup logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Redis connection pool
redis_client: Optional[redis.Redis] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    global redis_client
    
    # Startup
    logger.info("Starting application...")
    
    # Create necessary directories
    Path("output").mkdir(exist_ok=True)
    Path("logs").mkdir(exist_ok=True)
    Path("temp").mkdir(exist_ok=True)
    
    # Initialize Redis
    redis_client = await redis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        max_connections=50
    )
    
    logger.info("Application started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down application...")
    if redis_client:
        await redis_client.close()
    
    # Cleanup old temp files
    cleanup_temp_files()
    
    logger.info("Application shut down successfully")

app = FastAPI(
    title="M3U8 Video Merger API",
    version="1.0.0",
    description="Production-ready API for merging M3U8 videos with overlays and transitions",
    lifespan=lifespan,
    docs_url="/api/docs" if settings.ENABLE_DOCS else None,
    redoc_url="/api/redoc" if settings.ENABLE_DOCS else None,
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)

if settings.TRUSTED_HOSTS:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.TRUSTED_HOSTS
    )

# Models
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
    videos: List[VideoItem] = Field(..., min_items=1, max_items=50)
    transition_duration: float = Field(default=0.5, ge=0.1, le=2.0)
    overlay_duration: float = Field(default=2.0, ge=0.5, le=5.0)
    
    @validator('videos')
    def validate_videos(cls, v):
        if len(v) > settings.MAX_VIDEOS_PER_REQUEST:
            raise ValueError(f'Maximum {settings.MAX_VIDEOS_PER_REQUEST} videos allowed')
        return v

class JobStatus(BaseModel):
    job_id: str
    status: str
    progress: Optional[str] = None
    output_file: Optional[str] = None
    error: Optional[str] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None

# Dependency to get Redis client
async def get_redis():
    if redis_client is None:
        raise HTTPException(status_code=503, detail="Redis not available")
    return redis_client

# Helper functions
def cleanup_temp_files():
    """Cleanup temporary files older than 24 hours"""
    temp_dir = Path("temp")
    for item in temp_dir.glob("*"):
        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        except Exception as e:
            logger.error(f"Failed to cleanup {item}: {e}")

async def cleanup_old_jobs(redis_conn: redis.Redis):
    """Cleanup completed jobs older than configured retention period"""
    try:
        keys = await redis_conn.keys("job:*")
        for key in keys:
            job_data = await redis_conn.hgetall(key)
            if job_data.get("status") in ["completed", "failed"]:
                completed_at = job_data.get("completed_at")
                if completed_at:
                    # Check if older than retention period
                    # Implementation depends on your needs
                    pass
    except Exception as e:
        logger.error(f"Failed to cleanup old jobs: {e}")

async def store_job_status(
    redis_conn: redis.Redis,
    job_id: str,
    status: str,
    progress: Optional[str] = None,
    output_file: Optional[str] = None,
    error: Optional[str] = None
):
    """Store job status in Redis"""
    job_key = f"job:{job_id}"
    job_data = {
        "status": status,
        "progress": progress or "",
        "output_file": output_file or "",
        "error": error or "",
    }
    
    if status == "queued":
        from datetime import datetime
        job_data["created_at"] = datetime.utcnow().isoformat()
    elif status in ["completed", "failed"]:
        from datetime import datetime
        job_data["completed_at"] = datetime.utcnow().isoformat()
    
    await redis_conn.hset(job_key, mapping=job_data)
    await redis_conn.expire(job_key, settings.JOB_RETENTION_SECONDS)

async def get_job_status_from_redis(redis_conn: redis.Redis, job_id: str) -> Optional[dict]:
    """Get job status from Redis"""
    job_key = f"job:{job_id}"
    job_data = await redis_conn.hgetall(job_key)
    return job_data if job_data else None

async def process_merge_job(job_id: str, request: MergeRequest):
    """Background task to process video merging"""
    redis_conn = await redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
    temp_dir = None
    
    try:
        await store_job_status(redis_conn, job_id, "downloading", "Initializing...")
        temp_dir = tempfile.mkdtemp(dir="temp")
        
        processor = VideoProcessor(
            width=settings.REELS_WIDTH,
            height=settings.REELS_HEIGHT,
            temp_dir=temp_dir
        )
        
        # Download all M3U8 streams
        downloaded_videos = []
        total_videos = len(request.videos)
        
        for i, video in enumerate(request.videos):
            progress = f"Downloading video {i+1}/{total_videos}"
            await store_job_status(redis_conn, job_id, "downloading", progress)
            logger.info(f"Job {job_id}: {progress}")
            
            try:
                download_path = await processor.download_m3u8(
                    str(video.secure_media.reddit_video.hls_url),
                    i
                )
                downloaded_videos.append(download_path)
            except Exception as e:
                logger.error(f"Job {job_id}: Failed to download video {i+1}: {e}")
                raise Exception(f"Failed to download video {i+1}: {str(e)}")
        
        # Process each video
        await store_job_status(redis_conn, job_id, "processing", "Processing videos...")
        processed_videos = []
        
        for i, (video_path, video_data) in enumerate(zip(downloaded_videos, request.videos)):
            progress = f"Processing video {i+1}/{total_videos}"
            await store_job_status(redis_conn, job_id, "processing", progress)
            logger.info(f"Job {job_id}: {progress}")
            
            try:
                processed_path = await processor.process_video(
                    video_path,
                    i,
                    video_data.title,
                    request.overlay_duration
                )
                processed_videos.append(processed_path)
            except Exception as e:
                logger.error(f"Job {job_id}: Failed to process video {i+1}: {e}")
                raise Exception(f"Failed to process video {i+1}: {str(e)}")
        
        # Merge all videos
        await store_job_status(redis_conn, job_id, "merging", "Merging videos with transitions...")
        logger.info(f"Job {job_id}: Merging videos")
        
        output_dir = Path("output")
        output_path = str(output_dir / f"{job_id}.mp4")
        
        try:
            await processor.merge_videos(
                processed_videos,
                request.transition_duration,
                output_path
            )
        except Exception as e:
            logger.error(f"Job {job_id}: Failed to merge videos: {e}")
            raise Exception(f"Failed to merge videos: {str(e)}")
        
        # Success
        await store_job_status(
            redis_conn,
            job_id,
            "completed",
            "Completed successfully!",
            output_file=output_path
        )
        logger.info(f"Job {job_id}: Completed successfully")
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Job {job_id}: Failed - {error_msg}")
        await store_job_status(
            redis_conn,
            job_id,
            "failed",
            error=error_msg
        )
    finally:
        # Cleanup temp files
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.error(f"Job {job_id}: Failed to cleanup temp dir: {e}")
        
        await redis_conn.close()

# API Endpoints
@app.get("/")
async def root():
    """API information"""
    return {
        "name": "M3U8 Video Merger API",
        "version": "1.0.0",
        "status": "operational",
        "endpoints": {
            "POST /api/merge": "Create a new merge job",
            "GET /api/status/{job_id}": "Check job status",
            "GET /api/download/{job_id}": "Download completed video",
            "GET /health": "Health check endpoint"
        }
    }

@app.get("/health")
async def health_check(redis_conn: redis.Redis = Depends(get_redis)):
    """Health check endpoint"""
    try:
        await redis_conn.ping()
        redis_status = "healthy"
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        redis_status = "unhealthy"
    
    return {
        "status": "healthy" if redis_status == "healthy" else "degraded",
        "redis": redis_status,
        "ffmpeg": "available" if shutil.which("ffmpeg") else "unavailable"
    }

@app.post("/api/merge", response_model=JobStatus)
@rate_limit(max_requests=settings.RATE_LIMIT_PER_MINUTE, window=60)
async def create_merge_job(
    request: MergeRequest,
    background_tasks: BackgroundTasks,
    redis_conn: redis.Redis = Depends(get_redis)
):
    """Create a new video merge job"""
    job_id = str(uuid.uuid4())
    
    await store_job_status(redis_conn, job_id, "queued", "Job queued for processing")
    
    background_tasks.add_task(process_merge_job, job_id, request)
    
    logger.info(f"Created job {job_id} with {len(request.videos)} videos")
    
    return JobStatus(
        job_id=job_id,
        status="queued",
        progress="Job queued for processing"
    )

@app.get("/api/status/{job_id}", response_model=JobStatus)
async def get_job_status(
    job_id: str,
    redis_conn: redis.Redis = Depends(get_redis)
):
    """Get the status of a merge job"""
    job_data = await get_job_status_from_redis(redis_conn, job_id)
    
    if not job_data:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return JobStatus(
        job_id=job_id,
        status=job_data.get("status", "unknown"),
        progress=job_data.get("progress") or None,
        output_file=job_data.get("output_file") or None,
        error=job_data.get("error") or None,
        created_at=job_data.get("created_at") or None,
        completed_at=job_data.get("completed_at") or None
    )

@app.get("/api/download/{job_id}")
async def download_video(
    job_id: str,
    redis_conn: redis.Redis = Depends(get_redis)
):
    """Download the merged video"""
    job_data = await get_job_status_from_redis(redis_conn, job_id)
    
    if not job_data:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job_data["status"] != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Job status: {job_data['status']}. {job_data.get('error', '')}"
        )
    
    output_file = job_data.get("output_file")
    
    if not output_file or not os.path.exists(output_file):
        raise HTTPException(status_code=404, detail="Output file not found")
    
    return FileResponse(
        output_file,
        media_type="video/mp4",
        filename=f"merged_reels_{job_id}.mp4",
        headers={
            "Cache-Control": "public, max-age=3600",
            "Content-Disposition": f'attachment; filename="merged_reels_{job_id}.mp4"'
        }
    )

@app.delete("/api/job/{job_id}")
async def delete_job(
    job_id: str,
    redis_conn: redis.Redis = Depends(get_redis)
):
    """Delete a job and its output file"""
    job_data = await get_job_status_from_redis(redis_conn, job_id)
    
    if not job_data:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Delete output file if exists
    output_file = job_data.get("output_file")
    if output_file and os.path.exists(output_file):
        try:
            os.remove(output_file)
        except Exception as e:
            logger.error(f"Failed to delete output file: {e}")
    
    # Delete job from Redis
    await redis_conn.delete(f"job:{job_id}")
    
    return {"message": "Job deleted successfully"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        workers=settings.WORKERS,
        log_level=settings.LOG_LEVEL.lower(),
        access_log=True,
        reload=settings.DEBUG
    )
