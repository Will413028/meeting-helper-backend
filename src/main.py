import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import torch
import whisper
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydub import AudioSegment

# Import local speaker diarization
from speaker_diarization import LocalSpeakerDiarization, simple_vad_diarization

# Try to load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, use system environment variables

app = FastAPI(title="Meeting Helper API", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
ALLOWED_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".mp4", ".webm"}
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB

# Initialize models
whisper_model = None
diarization_pipeline = None


def init_models():
    """Initialize ML models"""
    global whisper_model, diarization_pipeline
    
    # Initialize Whisper model
    if whisper_model is None:
        print("Loading Whisper model...")
        device = "cuda" if torch.cuda.is_available() else "cpu"
        whisper_model = whisper.load_model("base", device=device)
        print(f"Whisper model loaded on {device}")
    
    # Initialize local speaker diarization
    if diarization_pipeline is None:
        print("Initializing local speaker diarization...")
        try:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            diarization_pipeline = LocalSpeakerDiarization(device=device)
            print(f"Local speaker diarization initialized on {device}")
        except Exception as e:
            print(f"Warning: Could not initialize speaker diarization: {e}")
            print("Using simple VAD-based diarization as fallback")
            diarization_pipeline = None


@app.on_event("startup")
async def startup_event():
    """Initialize models on startup"""
    init_models()


@app.get("/")
def read_root():
    return {
        "message": "Meeting Helper API",
        "endpoints": {
            "/upload": "Upload audio file for transcription",
            "/health": "Check API health status"
        }
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "models": {
            "whisper": whisper_model is not None,
            "diarization": diarization_pipeline is not None
        }
    }


def convert_to_wav(input_path: Path) -> Path:
    """Convert audio file to WAV format for processing"""
    output_path = input_path.with_suffix(".wav")
    
    if input_path.suffix.lower() == ".wav":
        return input_path
    
    audio = AudioSegment.from_file(str(input_path))
    audio.export(str(output_path), format="wav")
    
    return output_path


def perform_diarization(audio_path: Path) -> Optional[Dict]:
    """Perform speaker diarization on audio file"""
    try:
        if diarization_pipeline is not None:
            # Use LocalSpeakerDiarization
            speakers = diarization_pipeline.diarize(audio_path)
            return speakers
        else:
            # Fallback to simple VAD-based diarization
            print("Using simple VAD-based diarization")
            speakers = simple_vad_diarization(audio_path)
            return speakers
    except Exception as e:
        print(f"Diarization error: {e}")
        # Try simple fallback
        try:
            print("Attempting simple VAD-based diarization as final fallback")
            return simple_vad_diarization(audio_path)
        except Exception as e2:
            print(f"Simple diarization also failed: {e2}")
            return None


def transcribe_audio(audio_path: Path, speakers: Optional[Dict] = None) -> Dict:
    """Transcribe audio file with optional speaker segments"""
    if whisper_model is None:
        raise HTTPException(status_code=500, detail="Whisper model not loaded")
    
    # Transcribe the entire audio
    result = whisper_model.transcribe(str(audio_path), language="zh")
    
    # If no speaker diarization, return simple transcript
    if speakers is None:
        return {
            "full_transcript": result["text"],
            "segments": result["segments"],
            "language": result.get("language", "unknown")
        }
    
    # Combine transcription with speaker information
    transcript_with_speakers = []
    
    for segment in result["segments"]:
        segment_start = segment["start"]
        segment_end = segment["end"]
        segment_text = segment["text"]
        
        # Find which speaker this segment belongs to
        assigned_speaker = None
        max_overlap = 0
        
        for speaker, time_ranges in speakers.items():
            for time_range in time_ranges:
                # Calculate overlap between segment and speaker time range
                overlap_start = max(segment_start, time_range["start"])
                overlap_end = min(segment_end, time_range["end"])
                overlap_duration = max(0, overlap_end - overlap_start)
                
                if overlap_duration > max_overlap:
                    max_overlap = overlap_duration
                    assigned_speaker = speaker
        
        transcript_with_speakers.append({
            "speaker": assigned_speaker or "Unknown",
            "start": segment_start,
            "end": segment_end,
            "text": segment_text.strip()
        })
    
    # Group consecutive segments by speaker
    grouped_transcript = []
    current_speaker = None
    current_text = []
    current_start = None
    current_end = None
    
    for segment in transcript_with_speakers:
        if segment["speaker"] != current_speaker:
            if current_speaker is not None:
                grouped_transcript.append({
                    "speaker": current_speaker,
                    "start": current_start,
                    "end": current_end,
                    "text": " ".join(current_text)
                })
            current_speaker = segment["speaker"]
            current_text = [segment["text"]]
            current_start = segment["start"]
        else:
            current_text.append(segment["text"])
        current_end = segment["end"]
    
    # Add the last group
    if current_speaker is not None:
        grouped_transcript.append({
            "speaker": current_speaker,
            "start": current_start,
            "end": current_end,
            "text": " ".join(current_text)
        })
    
    return {
        "full_transcript": result["text"],
        "segments_by_speaker": grouped_transcript,
        "speaker_summary": {
            speaker: len([s for s in grouped_transcript if s["speaker"] == speaker])
            for speaker in set(s["speaker"] for s in grouped_transcript)
        },
        "language": result.get("language", "unknown")
    }


@app.post("/upload")
async def upload_audio(file: UploadFile = File(...)):
    """Upload audio file for transcription and speaker diarization"""
    
    # Validate file extension
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
    # Generate unique filename
    file_id = str(uuid.uuid4())
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_filename = f"{timestamp}_{file_id}{file_ext}"
    file_path = UPLOAD_DIR / safe_filename
    
    try:
        # Save uploaded file
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Check file size
        file_size = file_path.stat().st_size
        if file_size > MAX_FILE_SIZE:
            file_path.unlink()
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB"
            )
        
        # Convert to WAV if needed
        wav_path = convert_to_wav(file_path)
        
        # Perform speaker diarization
        print("Performing speaker diarization...")
        speakers = perform_diarization(wav_path)
        
        # Transcribe audio
        print("Transcribing audio...")
        transcription = transcribe_audio(wav_path, speakers)
        
        # Clean up WAV file if it was converted
        if wav_path != file_path and wav_path.exists():
            wav_path.unlink()
        
        return JSONResponse(
            status_code=200,
            content={
                "file_id": file_id,
                "filename": file.filename,
                "file_size": file_size,
                "saved_as": safe_filename,
                "transcription": transcription,
                "speakers_detected": speakers is not None
            }
        )
        
    except Exception as e:
        # Clean up files on error
        if file_path.exists():
            file_path.unlink()
        if 'wav_path' in locals() and wav_path.exists() and wav_path != file_path:
            wav_path.unlink()
        
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/files")
def list_uploaded_files():
    """List all uploaded audio files"""
    files = []
    for file_path in UPLOAD_DIR.iterdir():
        if file_path.is_file():
            files.append({
                "filename": file_path.name,
                "size": file_path.stat().st_size,
                "created": datetime.fromtimestamp(file_path.stat().st_ctime).isoformat()
            })
    
    return {
        "count": len(files),
        "files": sorted(files, key=lambda x: x["created"], reverse=True)
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
