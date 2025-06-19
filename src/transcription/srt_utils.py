"""Utilities for working with SRT files"""

import re
from pathlib import Path
from typing import Optional
from src.logger import logger


def extract_text_from_srt(srt_path: str) -> Optional[str]:
    """
    Extract plain text from an SRT file

    Args:
        srt_path: Path to the SRT file

    Returns:
        The extracted text without timestamps or None if failed
    """
    try:
        if not Path(srt_path).exists():
            logger.error(f"SRT file not found: {srt_path}")
            return None

        with open(srt_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Remove SRT formatting
        # Pattern to match subtitle blocks: number, timestamp, text
        pattern = r"\d+\n\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}\n(.+?)(?=\n\n|\n\d+\n|\Z)"

        matches = re.findall(pattern, content, re.DOTALL)

        # Join all text parts
        text_parts = []
        for match in matches:
            # Clean up the text
            text = match.strip()
            if text:
                text_parts.append(text)

        full_text = " ".join(text_parts)

        # Clean up extra spaces
        full_text = re.sub(r"\s+", " ", full_text).strip()

        logger.info(f"Extracted {len(full_text)} characters from SRT file")
        return full_text

    except Exception as e:
        logger.error(f"Error extracting text from SRT file {srt_path}: {e}")
        return None


def parse_srt_with_speakers(srt_path: str) -> Optional[dict]:
    """
    Parse SRT file and extract text with speaker information

    Args:
        srt_path: Path to the SRT file

    Returns:
        Dictionary with speaker segments or None if failed
    """
    try:
        if not Path(srt_path).exists():
            logger.error(f"SRT file not found: {srt_path}")
            return None

        with open(srt_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Pattern to match subtitle blocks with potential speaker tags
        pattern = r"(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.+?)(?=\n\n|\n\d+\n|\Z)"

        matches = re.findall(pattern, content, re.DOTALL)

        segments = []
        for match in matches:
            index, start_time, end_time, text = match
            text = text.strip()

            # Check if text contains speaker information (e.g., "SPEAKER_01: text")
            speaker_match = re.match(r"^(SPEAKER_\d+):\s*(.+)$", text, re.DOTALL)
            if speaker_match:
                speaker = speaker_match.group(1)
                text = speaker_match.group(2).strip()
            else:
                speaker = "UNKNOWN"

            segments.append(
                {
                    "index": int(index),
                    "start": start_time,
                    "end": end_time,
                    "speaker": speaker,
                    "text": text,
                }
            )

        return {"segments": segments, "total_segments": len(segments)}

    except Exception as e:
        logger.error(f"Error parsing SRT file {srt_path}: {e}")
        return None
