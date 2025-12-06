"""Utility functions for audio file processing"""

import os
from typing import Optional
from mutagen import File as MutagenFile
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from mutagen.flac import FLAC
from mutagen.oggvorbis import OggVorbis
from src.core.logger import logger


def get_audio_duration(file_path: str) -> Optional[int]:
    """
    Extract audio duration from file using mutagen

    Args:
        file_path: Path to the audio file

    Returns:
        Duration in seconds (as integer), or None if unable to extract
    """
    try:
        # Try to load the file with mutagen
        audio_file = MutagenFile(file_path)

        if audio_file is not None and hasattr(audio_file.info, "length"):
            duration = int(audio_file.info.length)
            logger.info(
                f"Extracted audio duration: {duration} seconds from {file_path}"
            )
            return duration
        else:
            # Try specific formats if generic approach fails
            ext = os.path.splitext(file_path)[1].lower()

            if ext == ".mp3":
                audio = MP3(file_path)
                duration = int(audio.info.length)
            elif ext in [".mp4", ".m4a", ".mov"]:
                audio = MP4(file_path)
                duration = int(audio.info.length)
            elif ext == ".flac":
                audio = FLAC(file_path)
                duration = int(audio.info.length)
            elif ext == ".ogg":
                audio = OggVorbis(file_path)
                duration = int(audio.info.length)
            else:
                logger.warning(f"Unable to extract duration for file type: {ext}")
                return None

            logger.info(
                f"Extracted audio duration: {duration} seconds from {file_path}"
            )
            return duration

    except Exception as e:
        logger.error(f"Error extracting audio duration from {file_path}: {e}")
        return None
