import subprocess
import re
from datetime import datetime, timedelta
from typing import Callable, Optional


def whisperx_diarize_with_progress(
    audio_path: str,
    output_dir: str,
    model: str = "large-v3",
    align_model: str = "",
    language: str = "zh",
    chunk_size: int = 6,
    hug_token: str = "",
    initial_prompt: str = "",
    progress_callback: Optional[Callable[[int, str, Optional[datetime]], None]] = None,
):
    """
    Run WhisperX with progress tracking

    Args:
        audio_path: Path to audio file
        output_dir: Output directory for results
        model: WhisperX model to use
        align_model: Alignment model
        language: Language code
        chunk_size: Chunk size for processing
        hug_token: HuggingFace token
        initial_prompt: Initial prompt for transcription
        progress_callback: Callback function(progress: int, step: str, estimated_completion: datetime)
    """

    command = f"whisperx '{audio_path}' --model {model}"

    if align_model:
        command += f" --align_model {align_model}"

    command += " --diarize --min_speakers=2 --max_speakers=4"
    command += f" --chunk_size {chunk_size}"
    command += " --compute_type float32"

    if hug_token:
        command += f" --hf_token {hug_token}"

    # whisper parameters
    command += " --temperature 0.1"
    command += " --fp16 False"
    command += f" --language {language}"

    if initial_prompt:
        command += f" --initial_prompt '{initial_prompt}'"

    command += " --condition_on_previous_text False"
    command += f" --output_dir '{output_dir}'"
    command += " --output_format srt"
    command += " --print_progress True"

    print(f"Executing command: {command}")

    # Execute command with real-time output capture
    process = subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        bufsize=1,
    )

    start_time = datetime.now()
    total_duration = None
    current_progress = 0

    # Progress tracking patterns
    patterns = {
        "loading_model": re.compile(r"Loading model"),
        "model_loaded": re.compile(r"Model loaded"),
        "transcribing": re.compile(r"Transcribing"),
        "processing": re.compile(r"Processing segment"),
        "aligning": re.compile(r"Aligning"),
        "diarizing": re.compile(r"Diarizing"),
        "duration": re.compile(r"Duration:\s*([\d:.]+)"),
        "progress": re.compile(r"Progress:\s*([\d.]+)%"),
        "segment": re.compile(r"segment\s+(\d+)/(\d+)"),
    }

    steps_progress = {
        "loading_model": (0, 10, "Loading WhisperX model"),
        "model_loaded": (10, 15, "Model loaded"),
        "transcribing": (15, 60, "Transcribing audio"),
        "aligning": (60, 80, "Aligning transcription"),
        "diarizing": (80, 95, "Speaker diarization"),
        "complete": (95, 100, "Finalizing output"),
    }

    current_step = "loading_model"

    # Read output line by line
    for line in iter(process.stdout.readline, ""):
        if not line:
            break

        line = line.strip()
        if not line:
            continue

        print(f"WhisperX: {line}")

        # Extract duration if available
        duration_match = patterns["duration"].search(line)
        if duration_match and not total_duration:
            duration_str = duration_match.group(1)
            # Parse duration (HH:MM:SS.mmm or MM:SS.mmm)
            parts = duration_str.split(":")
            if len(parts) == 3:
                hours, minutes, seconds = parts
                total_duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
            elif len(parts) == 2:
                minutes, seconds = parts
                total_duration = int(minutes) * 60 + float(seconds)

        # Update progress based on output
        estimated_completion = None

        # Check for specific steps
        if patterns["model_loaded"].search(line):
            current_step = "model_loaded"
            current_progress = steps_progress[current_step][1]
        elif patterns["transcribing"].search(line):
            current_step = "transcribing"
            current_progress = steps_progress[current_step][0]
        elif patterns["aligning"].search(line):
            current_step = "aligning"
            current_progress = steps_progress[current_step][0]
        elif patterns["diarizing"].search(line):
            current_step = "diarizing"
            current_progress = steps_progress[current_step][0]

        # Check for percentage progress
        progress_match = patterns["progress"].search(line)
        if progress_match:
            percentage = float(progress_match.group(1))
            # If we see progress percentage, we're in transcribing phase
            if "Transcript:" in line or percentage > 0:
                current_step = "transcribing"
            # Map percentage to current step range
            if current_step in steps_progress:
                min_prog, max_prog, _ = steps_progress[current_step]
                current_progress = min_prog + int(
                    (max_prog - min_prog) * percentage / 100
                )

        # Check for segment progress
        segment_match = patterns["segment"].search(line)
        if segment_match:
            current_segment = int(segment_match.group(1))
            total_segments = int(segment_match.group(2))
            if current_step == "transcribing" and total_segments > 0:
                min_prog, max_prog, _ = steps_progress[current_step]
                current_progress = (
                    min_prog + (max_prog - min_prog) * current_segment // total_segments
                )

        # Estimate completion time
        if current_progress > 15:  # After initial loading
            elapsed = (datetime.now() - start_time).total_seconds()
            if current_progress > 0:
                estimated_total = elapsed * 100 / current_progress
                remaining = estimated_total - elapsed
                estimated_completion = datetime.now() + timedelta(seconds=remaining)

        # Call progress callback
        if progress_callback and current_step in steps_progress:
            progress_callback(
                current_progress, steps_progress[current_step][2], estimated_completion
            )

    # Wait for process to complete
    process.wait()

    if process.returncode != 0:
        raise Exception(f"WhisperX failed with return code {process.returncode}")

    # Final progress update
    if progress_callback:
        progress_callback(100, "Completed", datetime.now())

    print("WhisperX processing completed")
