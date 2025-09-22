import os
import shutil
import subprocess
from typing import Optional, Dict, Any

from openai import OpenAI

JsonDict = Dict[str, Any]


class MediaProcessor:
    def __init__(self, openai_api_key: Optional[str] = None):
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY", "")
        self.client = OpenAI(api_key=self.openai_api_key)

    def _extract_audio(self, video_path: str, audio_path: str) -> None:
        if not shutil.which("ffmpeg"):
            raise RuntimeError("ffmpeg not found in PATH for video processing")
        cmd = ["ffmpeg", "-i", video_path, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", audio_path, "-y"]
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def transcribe_audio(self, file_path: str, language: str = "en") -> str:
        with open(file_path, "rb") as f:
            transcript = self.client.audio.transcriptions.create(model="whisper-1", file=f, language=language)
        # transcript.text is expected in latest SDK
        return getattr(transcript, "text", "")

    def transcribe_video(self, video_path: str, tmp_audio_path: str = "/tmp/journal_audio.wav", language: str = "en") -> str:
        self._extract_audio(video_path, tmp_audio_path)
        return self.transcribe_audio(tmp_audio_path, language=language)