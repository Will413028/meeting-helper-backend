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

# Run the server in HTTPS mode
./run-nohup.sh start --prod --https

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

### API test with curl

```bash
curl -X POST "https://114.34.174.244:8701/api/v1/transcribe?language=zh" \
  -H 'accept: application/json' \
  -H 'Content-Type: multipart/form-data' \
  -F "file=@test1.mp3" \
  | python -m json.tool
```
