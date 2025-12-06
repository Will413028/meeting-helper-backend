import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from pydub import AudioSegment
from fastapi import UploadFile
from src.core.logger import logger
from src.transcription.audio_utils import get_audio_duration


def convert_to_mp3(
    file: UploadFile, task_id: str, output_dir: str
) -> tuple[str, float]:
    """
    Convert uploaded audio file to MP3 format used by the system.
    Returns tuple of (audio_path, duration).
    This function performs blocking I/O and should be run in a threadpool.
    """
    file_extension = Path(file.filename).suffix.lower()
    temp_file = None
    temp_path = None

    try:
        # Create a temporary file to save the uploaded content
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=file_extension
        ) as temp_file:
            shutil.copyfileobj(file.file, temp_file)
            temp_path = temp_file.name

        logger.info(f"Converting {file.filename} to MP3 format")

        # Load the audio file
        audio = AudioSegment.from_file(temp_path)

        # Set up MP3 output path
        mp3_filename = f"{task_id}_{Path(file.filename).stem}.mp3"
        audio_path = os.path.join(output_dir, mp3_filename)

        # Export as MP3 with good quality settings
        audio.export(
            audio_path,
            format="mp3",
            bitrate="192k",
            parameters=["-q:a", "2"],
        )

        logger.info(f"Successfully converted audio to MP3: {audio_path}")

        # Extract duration
        audio_duration = get_audio_duration(audio_path)
        if audio_duration is None:
            logger.warning(
                f"Could not extract audio duration for {audio_path}, setting to 0"
            )
            audio_duration = 0.0

        return audio_path, audio_duration

    finally:
        # Clean up temporary file
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


def create_transcription_zip(
    transcription_id: int,
    task_id: str,
    audio_path: str,
    srt_path: str,
    transcription_title: str | None,
    summary: str | None,
) -> str:
    """
    Create a zip file containing transcription assets.
    Returns path to the temporary zip file.
    This function performs blocking I/O and should be run in a threadpool.
    """
    temp_dir = tempfile.mkdtemp()
    zip_filename = f"transcription_{transcription_id}_download.zip"
    zip_path = os.path.join(temp_dir, zip_filename)

    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            # Add audio file
            if audio_path and os.path.exists(audio_path):
                audio_filename = Path(audio_path).name
                # Remove task_id prefix if present
                if "_" in audio_filename and audio_filename.split("_")[0] == task_id:
                    audio_filename = "_".join(audio_filename.split("_")[1:])
                zipf.write(audio_path, arcname=audio_filename)

            # Add SRT file
            if srt_path and os.path.exists(srt_path):
                srt_filename = f"{transcription_title or 'subtitles'}.txt"
                zipf.write(srt_path, arcname=srt_filename)

            # Add summary file
            if summary:
                summary_filename = f"{transcription_title or 'summary'}_summary.txt"
                summary_path = os.path.join(temp_dir, summary_filename)
                with open(summary_path, "w", encoding="utf-8") as f:
                    f.write(summary)
                zipf.write(summary_path, arcname=summary_filename)
                os.remove(summary_path)

        return zip_path
    except Exception:
        # Cleanup on failure
        if os.path.exists(zip_path):
            os.remove(zip_path)
        if os.path.exists(temp_dir):
            os.rmdir(temp_dir)
        raise
