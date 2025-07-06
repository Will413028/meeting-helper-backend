# Meeting Helper Backend

A FastAPI backend service for audio file transcription with speaker diarization. This service can upload audio recordings, identify different speakers in the conversation, and generate transcripts for each speaker.

## Features

- **Audio File Upload**: Support for multiple audio formats (MP3, WAV, M4A, FLAC, OGG, MP4, WebM)
- **Speaker Diarization**: Automatically identify and separate different speakers in the audio
- **Speech-to-Text**: Generate accurate transcripts using OpenAI Whisper
- **Speaker-based Transcripts**: Get transcripts organized by speaker with timestamps
- **File Management**: Store uploaded files locally and list all uploaded files
- **SQLite Database**: Persistent storage of transcription history and metadata
- **Progress Tracking**: Real-time progress updates for async transcriptions
- **Task Management**: Track and manage multiple concurrent transcription tasks

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

### HTTP Mode (Default)

1. Start the FastAPI server:
```bash
make run
# Or manually:
uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8701
```

2. The API will be available at `http://localhost:8701`

3. Access the interactive API documentation at `http://localhost:8701/docs`

### HTTPS Mode

#### Quick Setup (Development)
```bash
# Run the setup script
./setup-https.sh

# Or manually:
# 1. Generate self-signed certificate
make generate-cert

# 2. Run with HTTPS
make run-https
```

#### Production Setup with Docker
```bash
# 1. Generate or obtain SSL certificates
# 2. Run with Docker Compose
docker-compose -f docker-compose.https.yml up -d
```

For detailed HTTPS setup instructions, see [HTTPS_SETUP.md](HTTPS_SETUP.md)

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

## Database Integration

The backend now includes SQLAlchemy ORM with SQLite for persistent storage of transcription data:

### Features
- **SQLAlchemy ORM**: Uses SQLAlchemy for database operations with proper models and sessions
- **Automatic Recording**: All transcriptions are automatically saved to the database
- **Metadata Storage**: File paths, processing status, timestamps, and file sizes stored as JSON
- **Search Capabilities**: Search by filename, task ID, or filter by status
- **Cleanup Tools**: Remove old records and optionally delete associated files
- **Statistics**: Track disk usage and transcription statistics
- **Type Safety**: Proper model definitions with SQLAlchemy declarative base

### Database Location
The SQLite database is stored at: `meeting_helper.db` (in the current working directory)

### Database Model
The `Transcription` model includes:
- `id`: Primary key
- `task_id`: Unique task identifier
- `filename`: Original filename
- `audio_path`: Path to audio file
- `srt_path`: Path to SRT file
- `model`: Whisper model used
- `language`: Language code
- `status`: Processing status (pending, processing, completed, failed)
- `progress`: Progress percentage
- `timestamps`: created_at, started_at, completed_at
- `extra_metadata`: JSON field for additional information

### Database Migrations with Alembic

The project uses Alembic for database migrations:

```bash
# Create a new migration
alembic revision --autogenerate -m "Description of changes"

# Apply migrations
alembic upgrade head

# Downgrade to previous version
alembic downgrade -1

# View migration history
alembic history

# View current version
alembic current
```

### Migrating from Raw SQLite

If you have an existing database from the previous raw SQLite implementation:

```bash
# Backup existing database
cp meeting_helper.db meeting_helper.db.backup

# Run the migration script
python migrate_to_sqlalchemy.py
```

### Testing Database Features
```bash
# Test database operations
python test_database.py

# Test with an audio file
python test_database.py audio.mp4
```

### Example Database Queries
```bash
# Get transcription statistics
curl http://localhost:8000/transcriptions/stats | jq

# List recent transcriptions
curl "http://localhost:8000/transcriptions?limit=10" | jq

# Search by filename
curl "http://localhost:8000/transcription/by-filename/meeting.mp4" | jq

# Clean up old records (older than 30 days)
curl -X POST "http://localhost:8000/transcriptions/cleanup?days=30" | jq
```

## Test Examples

### Basic transcription test
```bash
uv run ./src/whisperx_diarize.py 
```

### API test with curl
```bash
curl -X POST "http://localhost:8701/api/v1/transcribe" \
  -F "file=@audio.mp4" \
  -F "model=large-v3" \
  -F "language=zh" \
  | python -m json.tool
```

### Async transcription with progress tracking
```bash
python test_async_transcribe.py audio.mp4
```

For complete API documentation, see [API_DOCUMENTATION.md](API_DOCUMENTATION.md)
