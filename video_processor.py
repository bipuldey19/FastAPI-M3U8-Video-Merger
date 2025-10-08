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
        output_path = os.path.join(self.temp_dir, f"download_{index}.mp4")
        cmd = ['ffmpeg', '-i', url, '-c', 'copy', '-y', output_path]
        process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await process.communicate()
        if process.returncode != 0:
            raise Exception(f"Download failed")
        return output_path
    
    def create_overlay_filter(self, index: int, title: str, duration: float) -> str:
        safe_title = title.replace("'", "\\'").replace(":", "\\:")
        return (
            f"drawtext=fontsize=80:fontcolor=white:x=(w-text_w)/2:y=h*0.15:text='#{index+1}',"
            f"drawtext=fontsize=40:fontcolor=white:x=(w-text_w)/2:y=h*0.25:text='{safe_title}'"
        )
    
    async def process_video(self, video_path: str, index: int, title: str, overlay_duration: float) -> str:
        output_path = os.path.join(self.temp_dir, f"processed_{index}.mp4")
        overlay_filter = self.create_overlay_filter(index, title, overlay_duration)
        filter_complex = f"[0:v]scale={self.width}:{self.height}:force_original_aspect_ratio=decrease,pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2:black,{overlay_filter}[v]"
        cmd = ['ffmpeg', '-i', video_path, '-filter_complex', filter_complex, '-map', '[v]', '-map', '0:a?', '-c:v', 'libx264', '-preset', settings.FFMPEG_PRESET, '-crf', str(settings.FFMPEG_CRF), '-c:a', 'aac', '-y', output_path]
        process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await process.communicate()
        if process.returncode != 0:
            raise Exception(f"Processing failed")
        return output_path
    
    async def merge_videos(self, processed_videos: List[str], transition_duration: float, output_path: str) -> str:
        if len(processed_videos) == 1:
            import shutil
            shutil.copy(processed_videos[0], output_path)
            return output_path
        concat_file = os.path.join(self.temp_dir, "concat.txt")
        with open(concat_file, 'w') as f:
            for video in processed_videos:
                f.write(f"file '{os.path.abspath(video)}'\n")
        cmd = ['ffmpeg', '-f', 'concat', '-safe', '0', '-i', concat_file, '-c', 'copy', '-y', output_path]
        process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await process.communicate()
        if process.returncode != 0:
            raise Exception(f"Merge failed")
        return output_path
