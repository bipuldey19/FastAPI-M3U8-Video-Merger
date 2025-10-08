"""
Video processing module for downloading, processing, and merging videos
"""
import asyncio
import os
import logging
from typing import List
from config import settings

logger = logging.getLogger(__name__)


class VideoProcessor:
    def __init__(self, width: int, height: int, temp_dir: str):
        self.width = width
        self.height = height
        self.temp_dir = temp_dir
    
    async def download_m3u8(self, url: str, index: int) -> str:
        """Download M3U8 stream using ffmpeg with retry logic"""
        output_path = os.path.join(self.temp_dir, f"download_{index}.mp4")
        
        for attempt in range(settings.MAX_RETRIES):
            try:
                cmd = [
                    'ffmpeg',
                    '-i', url,
                    '-c', 'copy',
                    '-bsf:a', 'aac_adtstoasc',
                    '-y',
                    '-loglevel', 'error',
                    '-timeout', str(settings.DOWNLOAD_TIMEOUT * 1000000),  # microseconds
                    output_path
                ]
                
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=settings.DOWNLOAD_TIMEOUT
                )
                
                if process.returncode != 0:
                    error_msg = stderr.decode()
                    logger.warning(f"Download attempt {attempt + 1} failed: {error_msg}")
                    if attempt == settings.MAX_RETRIES - 1:
                        raise Exception(f"Failed to download M3U8: {error_msg}")
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    continue
                
                # Verify file was created and has content
                if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                    raise Exception("Downloaded file is empty or doesn't exist")
                
                return output_path
                
            except asyncio.TimeoutError:
                logger.warning(f"Download attempt {attempt + 1} timed out")
                if attempt == settings.MAX_RETRIES - 1:
                    raise Exception(f"Download timed out after {settings.DOWNLOAD_TIMEOUT} seconds")
                await asyncio.sleep(2 ** attempt)
        
        raise Exception("Failed to download video after all retries")
    
    def create_overlay_filter(self, index: int, title: str, duration: float) -> str:
        """Create FFmpeg filter for text overlay with animation"""
        # Escape special characters
        safe_title = (title
                     .replace("'", "'\\\\\\''")
                     .replace(":", "\\:")
                     .replace("%", "\\%")
                     .replace("[", "\\[")
                     .replace("]", "\\]"))
        
        fade_duration = 0.3
        
        overlay_filter = (
            f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
            f"text='#{index + 1}':"
            f"fontsize=120:"
            f"fontcolor=white@0.9:"
            f"x=(w-text_w)/2:"
            f"y=h*0.15:"
            f"borderw=4:"
            f"bordercolor=black@0.8:"
            f"enable='between(t,0,{duration})':"
            f"alpha='if(lt(t,{fade_duration}),t/{fade_duration},if(gt(t,{duration-fade_duration}),({duration}-t)/{fade_duration},1))',"
            
            f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:"
            f"text='{safe_title}':"
            f"fontsize=60:"
            f"fontcolor=white@0.9:"
            f"x=(w-text_w)/2:"
            f"y=h*0.25:"
            f"borderw=3:"
            f"bordercolor=black@0.8:"
            f"enable='between(t,0,{duration})':"
            f"alpha='if(lt(t,{fade_duration}),t/{fade_duration},if(gt(t,{duration-fade_duration}),({duration}-t)/{fade_duration},1))'"
        )
        
        return overlay_filter
    
    async def process_video(
        self,
        video_path: str,
        index: int,
        title: str,
        overlay_duration: float
    ) -> str:
        """Process single video: resize to reels format and add overlay"""
        output_path = os.path.join(self.temp_dir, f"processed_{index}.mp4")
        
        overlay_filter = self.create_overlay_filter(index, title, overlay_duration)
        
        # Scale to reels format with padding
        filter_complex = (
            f"[0:v]scale={self.width}:{self.height}:force_original_aspect_ratio=decrease,"
            f"pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2:black,"
            f"fps=30,"  # Standardize frame rate
            f"{overlay_filter}[v]"
        )
        
        cmd = [
            'ffmpeg',
            '-i', video_path,
            '-filter_complex', filter_complex,
            '-map', '[v]',
            '-map', '0:a?',
            '-c:v', 'libx264',
            '-preset', settings.FFMPEG_PRESET,
            '-crf', str(settings.FFMPEG_CRF),
            '-profile:v', 'high',
            '-level', '4.0',
            '-pix_fmt', 'yuv420p',
            '-c:a', 'aac',
            '-b:a', '128k',
            '-ar', '44100',
            '-movflags', '+faststart',
            '-y',
            '-loglevel', 'error',
            output_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            raise Exception(f"Failed to process video {index}: {stderr.decode()}")
        
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise Exception(f"Processed video {index} is empty or doesn't exist")
        
        return output_path
    
    async def merge_videos(
        self,
        processed_videos: List[str],
        transition_duration: float,
        output_path: str
    ) -> str:
        """Merge all processed videos with concat"""
        if len(processed_videos) == 1:
            # Single video, just copy
            import shutil
            shutil.copy(processed_videos[0], output_path)
            return output_path
        
        # Create concat file
        concat_file = os.path.join(self.temp_dir, "concat_list.txt")
        with open(concat_file, 'w') as f:
            for video in processed_videos:
                f.write(f"file '{os.path.abspath(video)}'\n")
        
        cmd = [
            'ffmpeg',
            '-f', 'concat',
            '-safe', '0',
            '-i', concat_file,
            '-c', 'copy',
            '-movflags', '+faststart',
            '-y',
            '-loglevel', 'error',
            output_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            raise Exception(f"Failed to merge videos: {stderr.decode()}")
        
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise Exception("Merged video is empty or doesn't exist")
        
        return output_path
