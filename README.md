# Meeting Helper Backend

A FastAPI backend service for audio file transcription with speaker diarization. This service can upload audio recordings, identify different speakers in the conversation, and generate transcripts for each speaker.

## Features

- **Audio File Upload**: Support for multiple audio formats (MP3, WAV, M4A, FLAC, OGG, MP4, WebM)
- **Speaker Diarization**: Automatically identify and separate different speakers in the audio
- **Speech-to-Text**: Generate accurate transcripts using OpenAI Whisper
- **Speaker-based Transcripts**: Get transcripts organized by speaker with timestamps
- **File Management**: Store uploaded files locally and list all uploaded files

## Prerequisites

- Python 3.13+
- [uv](https://github.com/astral-sh/uv) for package management
- FFmpeg (for audio processing)
- GPU with CUDA support (optional, for faster processing)

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd meeting-helper-backend
```

2. Install FFmpeg:
```bash
# Ubuntu/Debian
sudo apt update && sudo apt install ffmpeg
```

3. Install dependencies using uv:
```bash
uv sync
```

4. (Optional) Set up environment variables:
```bash
make setup-env
# Edit .env file if needed for custom configurations
```

## Running the Server

1. Start the FastAPI server:
```bash
uv run uvicorn src.main:app --reload
```

Or using the Python module directly:
```bash
uv run python src/main.py
```

2. The API will be available at `http://localhost:8000`

3. Access the interactive API documentation at `http://localhost:8000/docs`

## API Endpoints

### 1. Health Check
- **GET** `/health`
- Returns the status of the API and loaded models

### 2. Upload Audio File
- **POST** `/upload`
- Upload an audio file for transcription and speaker diarization
- **Request**: Multipart form data with audio file
- **Response**: 
  ```json
  {
    "file_id": "unique-file-id",
    "filename": "original-filename.mp3",
    "file_size": 1234567,
    "saved_as": "20240108_120000_uuid.mp3",
    "transcription": {
      "full_transcript": "Complete transcript text",
      "segments_by_speaker": [
        {
          "speaker": "SPEAKER_00",
          "start": 0.0,
          "end": 5.2,
          "text": "Hello, how are you?"
        },
        {
          "speaker": "SPEAKER_01",
          "start": 5.5,
          "end": 8.3,
          "text": "I'm fine, thank you!"
        }
      ],
      "speaker_summary": {
        "SPEAKER_00": 5,
        "SPEAKER_01": 4
      },
      "language": "zh"
    },
    "speakers_detected": true
  }
  ```

### 3. List Uploaded Files
- **GET** `/files`
- Returns a list of all uploaded audio files
- **Response**:
  ```json
  {
    "count": 2,
    "files": [
      {
        "filename": "20240108_120000_uuid.mp3",
        "size": 1234567,
        "created": "2024-01-08T12:00:00"
      }
    ]
  }
  ```

## Testing

Use the provided test script to test the API:

```bash
# Test health check and list files
uv run python test_api.py

# Test with an audio file
# Edit test_api.py and uncomment the test_upload line with your audio file path
```

## Configuration

The following settings can be modified in `src/main.py`:

- `UPLOAD_DIR`: Directory for storing uploaded files (default: "uploads")
- `ALLOWED_EXTENSIONS`: Supported audio file formats
- `MAX_FILE_SIZE`: Maximum upload file size (default: 500MB)
- Whisper model size: Change `"base"` to `"small"`, `"medium"`, `"large"` for better accuracy

## Notes

1. **First Run**: The first time you run the server, it will download the Whisper model and speaker embedding models, which may take some time.

2. **GPU Support**: If you have a CUDA-capable GPU, the models will automatically use it for faster processing.

3. **Language**: The transcription is currently set to Chinese (`language="zh"`). Modify this in the `transcribe_audio` function for other languages or set to `None` for auto-detection.

## Troubleshooting

1. **Missing FFmpeg**: If you get audio processing errors, ensure FFmpeg is installed and in your PATH.

2. **Speaker Diarization Issues**: If speaker diarization fails:
   - Ensure all dependencies are properly installed
   - Check that you have sufficient RAM (at least 8GB recommended)
   - The fallback VAD-based diarization will be used automatically

3. **Memory Issues**: Large audio files may require significant RAM. Consider using smaller Whisper models or processing files in chunks.

## test
uv run ./src/whisperx_diarize.py 


curl -X POST "http://localhost:8000/transcribe/" \
  -F "file=@audio.mp4" \
  -F "model=large-v3" \
  -F "language=zh" \
  | python -m json.tool