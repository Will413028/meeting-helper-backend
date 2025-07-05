"""Utilities for working with SRT files"""

import re
from pathlib import Path
from typing import Optional
from src.logger import logger
import opencc


def extract_text_from_srt(
    srt_path: str, convert_to_traditional: bool = True, preserve_speakers: bool = True
) -> Optional[str]:
    """
    Extract plain text from an SRT file

    Args:
        srt_path: Path to the SRT file
        convert_to_traditional: Whether to convert simplified Chinese to traditional Chinese
        preserve_speakers: Whether to preserve speaker information in the output

    Returns:
        The extracted text without timestamps or None if failed
    """
    try:
        if not Path(srt_path).exists():
            logger.error(f"SRT file not found: {srt_path}")
            return None

        with open(srt_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Try to detect format - check if it's simple format or standard SRT
        # Simple format: HH:MM:SS\ntext
        # Standard SRT: number\nHH:MM:SS,mmm --> HH:MM:SS,mmm\ntext

        if re.search(r"^\d+\n\d{2}:\d{2}:\d{2},\d{3} --> ", content, re.MULTILINE):
            # Standard SRT format with sequence numbers and timestamps
            pattern = r"\d+\n\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}\n(.+?)(?=\n\n|\n\d+\n|\Z)"
        elif re.search(r"^\d{2}:\d{2}:\d{2},\d{3} --> ", content, re.MULTILINE):
            # SRT format without sequence numbers
            pattern = (
                r"\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}\n(.+?)(?=\n\n|\Z)"
            )
        else:
            # Simple format (HH:MM:SS\ntext)
            pattern = r"\d{2}:\d{2}:\d{2}\n(.+?)(?=\n\n|\Z)"

        matches = re.findall(pattern, content, re.DOTALL)

        # Join all text parts
        text_parts = []
        for match in matches:
            # Clean up the text
            text = match.strip()
            if text:
                # Convert speaker labels if preserving speakers
                if preserve_speakers:
                    # Convert [SPEAKER_XX]: to 講者 X: (increment number by 1)
                    def convert_speaker(match):
                        speaker_num = int(match.group(1)) + 1
                        return f"講者 {speaker_num}: "

                    text = re.sub(r"\[SPEAKER_(\d+)\]:\s*", convert_speaker, text)
                else:
                    # Remove speaker labels entirely
                    text = re.sub(r"\[SPEAKER_\d+\]:\s*", "", text)

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

        # Try to detect format
        segments = []

        if re.search(r"^\d+\n\d{2}:\d{2}:\d{2},\d{3} --> ", content, re.MULTILINE):
            # Standard SRT format with sequence numbers
            pattern = r"(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.+?)(?=\n\n|\n\d+\n|\Z)"
            matches = re.findall(pattern, content, re.DOTALL)

            for match in matches:
                index, start_time, end_time, text = match
                segments.append((index, start_time, end_time, text))

        elif re.search(r"^\d{2}:\d{2}:\d{2},\d{3} --> ", content, re.MULTILINE):
            # SRT format without sequence numbers
            pattern = r"(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.+?)(?=\n\n|\Z)"
            matches = re.findall(pattern, content, re.DOTALL)

            for i, match in enumerate(matches):
                start_time, end_time, text = match
                segments.append((str(i + 1), start_time, end_time, text))

        else:
            # Simple format (HH:MM:SS\ntext)
            pattern = r"(\d{2}:\d{2}:\d{2})\n(.+?)(?=\n\n|\Z)"
            matches = re.findall(pattern, content, re.DOTALL)

            for i, match in enumerate(matches):
                start_time, text = match
                # For simple format, we don't have end times, so we'll use empty string
                segments.append((str(i + 1), f"{start_time},000", "", text))

        # Initialize converter if needed
        converter = None
        if convert_to_traditional:
            try:
                converter = opencc.OpenCC("s2twp")  # 簡體轉繁體（台灣用詞）
            except Exception as e:
                logger.warning(f"Failed to initialize OpenCC converter: {e}")

        result_segments = []
        for index, start_time, end_time, text in segments:
            text = text.strip()

            # Check if text contains speaker information
            # Handle both original format (SPEAKER_01: text) and converted format (講者 1: text)
            speaker_match = re.match(r"^(SPEAKER_\d+):\s*(.+)$", text, re.DOTALL)
            chinese_speaker_match = re.match(r"^(講者\s*\d+):\s*(.+)$", text, re.DOTALL)

            if speaker_match:
                # Original format: SPEAKER_01: text
                # Convert SPEAKER_00 to 講者 1, SPEAKER_01 to 講者 2, etc.
                speaker_num = int(speaker_match.group(1).replace("SPEAKER_", "")) + 1
                speaker = f"講者 {speaker_num}"
                text = speaker_match.group(2).strip()  # Extract only the content
            elif chinese_speaker_match:
                # Already converted format: 講者 1: text
                speaker = chinese_speaker_match.group(1).replace(
                    " ", " "
                )  # Normalize spacing
                text = chinese_speaker_match.group(
                    2
                ).strip()  # Extract only the content
            else:
                speaker = "未知講者"  # Unknown speaker in Chinese
                # text remains as is (no speaker prefix to remove)

            # Convert to traditional Chinese if converter is available
            if converter and text:
                try:
                    text = converter.convert(text)
                except Exception as e:
                    logger.warning(f"Failed to convert segment text: {e}")

            result_segments.append(
                {
                    "index": int(index),
                    "start": start_time,
                    "end": end_time,
                    "speaker": speaker,
                    "text": text,
                }
            )

        if converter and result_segments:
            logger.info("Converted SRT segments from simplified to traditional Chinese")

        return {"segments": result_segments, "total_segments": len(result_segments)}

    except Exception as e:
        logger.error(f"Error parsing SRT file {srt_path}: {e}")
        return None


def convert_srt_file_to_traditional(
    srt_path: str, convert_speakers: bool = True
) -> bool:
    """
    Convert an SRT file from simplified to traditional Chinese and convert speaker labels

    Args:
        srt_path: Path to the SRT file to convert
        convert_speakers: Whether to convert speaker labels from [SPEAKER_XX]: to 講者 XX:

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

        # Convert speaker labels if requested
        if convert_speakers:
            # Convert [SPEAKER_XX]: to 講者 X: (increment number by 1)
            def convert_speaker(match):
                speaker_num = int(match.group(1)) + 1
                return f"講者 {speaker_num}: "

            content = re.sub(r"\[SPEAKER_(\d+)\]:\s*", convert_speaker, content)
            logger.info("Converted speaker labels to Chinese format")

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


def remove_srt_sequence_numbers(srt_path: str) -> bool:
    """
    Remove sequence numbers from an SRT file, keeping only timestamps and text

    Args:
        srt_path: Path to the SRT file to process

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

        # Pattern to match subtitle blocks: number, timestamp, text
        # We'll capture the timestamp and text parts, but not the number
        pattern = r"\d+\n(\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}\n.+?)(?=\n\n|\n\d+\n|\Z)"

        matches = re.findall(pattern, content, re.DOTALL)

        # Rebuild the SRT content without sequence numbers
        new_content = []
        for match in matches:
            # Each match contains timestamp line and text
            new_content.append(match.strip())

        # Join with double newlines between entries
        final_content = "\n\n".join(new_content)

        # Ensure file ends with a newline
        if final_content and not final_content.endswith("\n"):
            final_content += "\n"

        # Write back to the same file
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(final_content)

        logger.info(f"Successfully removed sequence numbers from SRT file: {srt_path}")
        return True

    except Exception as e:
        logger.error(f"Error removing sequence numbers from SRT file {srt_path}: {e}")
        return False


def convert_srt_to_simple_format(srt_path: str) -> bool:
    """
    Convert SRT file to a simplified format with only start times (no end times)
    and simplified timestamp format (HH:MM:SS instead of HH:MM:SS,mmm)

    Args:
        srt_path: Path to the SRT file to process

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

        # Pattern to match subtitle blocks without sequence numbers
        # Captures: start_time, end_time (ignored), and text
        pattern = (
            r"(\d{2}:\d{2}:\d{2}),\d{3} --> \d{2}:\d{2}:\d{2},\d{3}\n(.+?)(?=\n\n|\Z)"
        )

        matches = re.findall(pattern, content, re.DOTALL)

        # Rebuild content with simplified format
        new_content = []
        for start_time, text in matches:
            # start_time is already in HH:MM:SS format (we just ignore the milliseconds)
            text = text.strip()
            if text:
                new_content.append(f"{start_time}\n{text}")

        # Join with double newlines between entries
        final_content = "\n\n".join(new_content)

        # Ensure file ends with a newline
        if final_content and not final_content.endswith("\n"):
            final_content += "\n"

        # Write back to the same file
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(final_content)

        logger.info(f"Successfully converted SRT to simple format: {srt_path}")
        return True

    except Exception as e:
        logger.error(f"Error converting SRT to simple format {srt_path}: {e}")
        return False
