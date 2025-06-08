from typing import Union
import os
import tempfile
import shutil
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from src.whisperx_diarize import whisperx_diarize

app = FastAPI()


@app.get("/")
def read_root():
    return {"Hello": "World"}

@app.post("/transcribe/")
async def transcribe_audio(
    file: UploadFile = File(...),
    model: str = "large-v3",
    language: str = "zh",
    hf_token: str = None
):
    """
    Upload an audio file and get SRT transcription using WhisperX
    
    Args:
        file: Audio file (mp3, wav, mp4, etc.)
        model: WhisperX model to use (default: large-v3)
        language: Language code (default: zh for Chinese)
        hf_token: HuggingFace token for speaker diarization
    
    Returns:
        SRT file with transcription
    """
    # Validate file extension
    allowed_extensions = ['.mp3', '.wav', '.mp4', '.m4a', '.flac', '.ogg', '.webm']
    file_extension = Path(file.filename).suffix.lower()
    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File type not supported. Allowed types: {', '.join(allowed_extensions)}"
        )
    
    # Save uploaded file in current directory
    audio_filename = f"{Path(file.filename).stem}{file_extension}"
    audio_path = os.path.join(os.getcwd(), audio_filename)
    with open(audio_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Set output directory to current directory
    output_dir = os.getcwd()
    
    try:
        # Process audio with WhisperX
        whisperx_diarize(
            audio_path=audio_path,
            output_dir=output_dir,
            model=model,
            align_model="WAV2VEC2_ASR_LARGE_LV60K_960H" if language == "zh" else "",
            language=language,
            chunk_size=6,
            hug_token="your_huggingface_token_here",
            initial_prompt=""
        )
        
        # Check if SRT file was generated
        # WhisperX generates output file with the same base name as input
        srt_filename = f"{Path(file.filename).stem}.srt"
        srt_file_path = os.path.join(output_dir, srt_filename)
        
        if not os.path.exists(srt_file_path):
            # Try alternative naming pattern
            alt_srt_path = os.path.join(output_dir, f"{Path(audio_filename).stem}.srt")
            if os.path.exists(alt_srt_path):
                srt_file_path = alt_srt_path
                srt_filename = os.path.basename(alt_srt_path)
            else:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to generate SRT file"
                )
        
        # Return success response with file info
        return {
            "status": "success",
            "message": "Transcription completed successfully",
            "audio_file": audio_filename,
            "srt_file": srt_filename,
            "srt_path": srt_file_path
        }
        
    except Exception as e:
        # Clean up audio file on error
        if os.path.exists(audio_path):
            os.remove(audio_path)
        raise HTTPException(
            status_code=500,
            detail=f"Error processing audio: {str(e)}"
        )
