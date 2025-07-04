"""Utilities for working with SRT files"""

import re
from pathlib import Path
from typing import Optional
from src.logger import logger
import opencc


def extract_text_from_srt(
    srt_path: str, convert_to_traditional: bool = True
) -> Optional[str]:
    """
    Extract plain text from an SRT file

    Args:
        srt_path: Path to the SRT file
        convert_to_traditional: Whether to convert simplified Chinese to traditional Chinese

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

        # Convert simplified to traditional Chinese if requested
        if convert_to_traditional and full_text:
            try:
                converter = opencc.OpenCC("s2twp")  # 簡體轉繁體（台灣用詞）
                full_text = converter.convert(full_text)
                logger.info("Converted text from simplified to traditional Chinese")
            except Exception as e:
                logger.warning(f"Failed to convert to traditional Chinese: {e}")

        logger.info(f"Extracted {len(full_text)} characters from SRT file")
        return full_text

    except Exception as e:
        logger.error(f"Error extracting text from SRT file {srt_path}: {e}")
        return None


def parse_srt_with_speakers(
    srt_path: str, convert_to_traditional: bool = True
) -> Optional[dict]:
    """
    Parse SRT file and extract text with speaker information

    Args:
        srt_path: Path to the SRT file
        convert_to_traditional: Whether to convert simplified Chinese to traditional Chinese

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

        # Initialize converter if needed
        converter = None
        if convert_to_traditional:
            try:
                converter = opencc.OpenCC("s2twp")  # 簡體轉繁體（台灣用詞）
            except Exception as e:
                logger.warning(f"Failed to initialize OpenCC converter: {e}")

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

            # Convert to traditional Chinese if converter is available
            if converter and text:
                try:
                    text = converter.convert(text)
                except Exception as e:
                    logger.warning(f"Failed to convert segment text: {e}")

            segments.append(
                {
                    "index": int(index),
                    "start": start_time,
                    "end": end_time,
                    "speaker": speaker,
                    "text": text,
                }
            )

        if converter and segments:
            logger.info("Converted SRT segments from simplified to traditional Chinese")

        return {"segments": segments, "total_segments": len(segments)}

    except Exception as e:
        logger.error(f"Error parsing SRT file {srt_path}: {e}")
        return None


def convert_srt_file_to_traditional(srt_path: str) -> bool:
    """
    Convert an SRT file from simplified to traditional Chinese and overwrite it

    Args:
        srt_path: Path to the SRT file to convert

    Returns:
        True if successful, False otherwise
    """
    try:
        if not Path(srt_path).exists():
            logger.error(f"SRT file not found: {srt_path}")
            return False

        # Read the original content
        with open(srt_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Convert to traditional Chinese
        try:
            converter = opencc.OpenCC("s2twp")  # 簡體轉繁體（台灣用詞）
            converted_content = converter.convert(content)

            # Write back to the same file
            with open(srt_path, "w", encoding="utf-8") as f:
                f.write(converted_content)

            logger.info(
                f"Successfully converted SRT file to traditional Chinese: {srt_path}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to convert SRT file to traditional Chinese: {e}")
            return False

    except Exception as e:
        logger.error(f"Error processing SRT file {srt_path}: {e}")
        return False
