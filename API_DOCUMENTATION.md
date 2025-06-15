# Audio Transcription API Documentation

## Overview

This API provides endpoints to upload audio files and receive SRT (SubRip Subtitle) files generated using WhisperX with speaker diarization capabilities. It supports both synchronous and asynchronous transcription with progress tracking.

## Endpoints

### 1. POST /transcribe/ (Synchronous)

Upload an audio file and receive an SRT transcription with speaker diarization.

#### Request

- **Method**: POST
- **Content-Type**: multipart/form-data

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| file | File | Yes | - | Audio file to transcribe. Supported formats: .mp3, .wav, .mp4, .m4a, .flac, .ogg, .webm |
| model | string | No | "large-v3" | WhisperX model to use. Options: "tiny", "base", "small", "medium", "large", "large-v2", "large-v3" |
| language | string | No | "zh" | Language code for transcription. Examples: "zh" (Chinese), "en" (English), "ja" (Japanese) |
| hf_token | string | No | None | HuggingFace token for speaker diarization. Required for using the latest diarization models |

#### Response

- **Success (200)**: Returns an SRT file with the transcription
  - Content-Type: application/x-subrip
  - The file will be named based on the original filename with .srt extension

- **Error (400)**: Invalid file type
  ```json
  {
    "detail": "File type not supported. Allowed types: .mp3, .wav, .mp4, .m4a, .flac, .ogg, .webm"
  }
  ```

- **Error (500)**: Processing error
  ```json
  {
    "detail": "Error processing audio: [error message]"
  }
  ```

## Example Usage

### Using curl

```bash
# Basic usage (Chinese transcription)
curl -X POST "http://localhost:8000/transcribe/" \
  -F "file=@audio.mp4" \
  -o output.srt

# With custom parameters
curl -X POST "http://localhost:8000/transcribe/" \
  -F "file=@audio.mp4" \
  -F "model=large-v3" \
  -F "language=en" \
  -F "hf_token=your_huggingface_token" \
  -o output.srt
```

### Using Python

```python
import requests

# Basic usage
with open('audio.mp4', 'rb') as f:
    files = {'file': ('audio.mp4', f, 'audio/mp4')}
    response = requests.post('http://localhost:8000/transcribe/', files=files)
    
    if response.status_code == 200:
        with open('output.srt', 'wb') as out:
            out.write(response.content)
```

### Using the test script

```bash
# Basic usage
python test_transcribe.py audio.mp4

# With HuggingFace token for better speaker diarization
python test_transcribe.py audio.mp4 hf_your_token_here
```

## SRT Output Format

The generated SRT file will contain:
- Sequential subtitle numbers
- Timestamps in format: HH:MM:SS,mmm --> HH:MM:SS,mmm
- Transcribed text with speaker labels (if diarization is enabled)

Example:
```
1
00:00:00,000 --> 00:00:02,500
[SPEAKER_00] 你好，今天我們來討論一下

2
00:00:02,500 --> 00:00:05,000
[SPEAKER_01] 好的，我準備好了
```

### 2. POST /transcribe (Asynchronous with Progress Tracking)

Upload an audio file and start asynchronous transcription with progress tracking and estimated completion time.

#### Request

- **Method**: POST
- **Content-Type**: multipart/form-data

#### Parameters

Same as the synchronous endpoint.

#### Response

- **Success (200)**: Returns task information
  ```json
  {
    "task_id": "uuid-string",
    "message": "Transcription task started",
    "status_url": "/task/{task_id}"
  }
  ```

### 3. GET /task/{task_id}

Get the status and progress of a transcription task.

#### Response

```json
{
  "task_id": "uuid-string",
  "filename": "audio.mp4",
  "status": "processing",  // "pending", "processing", "completed", "failed"
  "progress": 45,  // 0-100
  "current_step": "Transcribing audio",
  "created_at": "2024-01-08T12:00:00",
  "started_at": "2024-01-08T12:00:05",
  "completed_at": null,
  "estimated_completion_time": "2024-01-08T12:05:00",
  "result": null  // Contains file paths when completed
}
```

### 4. POST /task/{task_id}/cancel

Cancel a running transcription task.

#### Request

- **Method**: POST
- **Path Parameter**: task_id (string) - The ID of the task to cancel

#### Response

- **Success (200)**: Task cancelled successfully
  ```json
  {
    "task_id": "uuid-string",
    "message": "Task cancelled successfully",
    "status": "cancelled"
  }
  ```

- **Error (404)**: Task not found
  ```json
  {
    "detail": "Task not found"
  }
  ```

- **Error (400)**: Task cannot be cancelled
  ```json
  {
    "detail": "Task cannot be cancelled. Current status: completed"
  }
  ```

#### Notes

- Only tasks with status "pending" or "processing" can be cancelled
- Cancelling a task will:
  - Stop the transcription process
  - Update the task status to "cancelled"
  - Clean up the uploaded audio file
  - Update the database record

### 5. GET /tasks

List all transcription tasks.

#### Response

```json
{
  "count": 2,
  "tasks": [
    {
      "task_id": "uuid-string",
      "filename": "audio.mp4",
      "status": "completed",
      "progress": 100,
      // ... other task fields
    }
  ]
}
```

### 6. GET /disk-space

Get remaining disk space information in GB.

#### Response

- **Success (200)**: Returns disk space information
  ```json
  {
    "total_gb": 250.5,
    "used_gb": 150.3,
    "free_gb": 100.2,
    "percent_used": 60.0,
    "mount_point": "/"
  }
  ```

- **Error (500)**: Error getting disk space
  ```json
  {
    "detail": "Error getting disk space: [error message]"
  }
  ```

#### Example Usage

```bash
# Using curl
curl "http://localhost:8000/disk-space" | jq

# Using Python
import requests

response = requests.get('http://localhost:8000/disk-space')
if response.status_code == 200:
    disk_info = response.json()
    print(f"Free space: {disk_info['free_gb']} GB")
    print(f"Used: {disk_info['percent_used']}%")
```

## Example Usage - Async Transcription

### Using curl with progress tracking

```bash
# 1. Start transcription
RESPONSE=$(curl -X POST "http://localhost:8000/transcribe" \
  -F "file=@audio.mp4" \
  -F "model=large-v3" \
  -F "language=zh")

# Extract task_id
TASK_ID=$(echo $RESPONSE | jq -r '.task_id')

# 2. Check progress
curl "http://localhost:8000/task/$TASK_ID" | jq

# 3. Poll until complete
while true; do
  STATUS=$(curl -s "http://localhost:8000/task/$TASK_ID" | jq -r '.status')
  if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ]; then
    break
  fi
  sleep 2
done

# 4. Cancel a running task
curl -X POST "http://localhost:8000/task/$TASK_ID/cancel" | jq
```

### Using the async test script

```bash
# Start async transcription with real-time progress tracking
python test_async_transcribe.py audio.mp4

# List all tasks
python test_async_transcribe.py --list
```

### Progress Tracking Features

The async endpoint provides:
- **Real-time progress updates** (0-100%)
- **Current processing step** (Loading model, Transcribing, Aligning, Speaker diarization, etc.)
- **Estimated completion time** based on current progress
- **Task history** to track all transcription jobs

## Notes

1. **Processing Time**: Transcription time depends on:
   - Audio file length
   - Selected model size (larger models are more accurate but slower)
   - Hardware (GPU acceleration significantly speeds up processing)

2. **Speaker Diarization**: 
   - Requires a HuggingFace token for the latest models
   - Automatically detects 2-4 speakers
   - Speaker labels are assigned as SPEAKER_00, SPEAKER_01, etc.

3. **Language Support**: 
   - Default is Chinese ('zh')
   - Supports all languages that Whisper supports
   - For auto-detection, omit the language parameter

4. **Model Selection**:
   - `tiny`: Fastest, least accurate
   - `base`: Fast, reasonable accuracy
   - `small`: Good balance
   - `medium`: Better accuracy
   - `large-v3`: Best accuracy (default)

5. **Progress Tracking**:
   - Progress is estimated based on processing steps
   - Estimated completion time becomes more accurate as processing continues
   - Multiple files can be processed concurrently (up to 4 by default)

## Database Integration

The backend now uses SQLite to persistently store transcription information. All transcription tasks are automatically saved to the database with the following information:

- Task ID and filename
- Audio and SRT file paths
- Model and language settings
- Processing status and progress
- Timestamps (created, started, completed)
- Error messages (if any)
- File metadata

### 7. GET /transcriptions

List all transcriptions from the database with pagination.

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| limit | int | No | 100 | Maximum number of records to return |
| offset | int | No | 0 | Number of records to skip |
| status | string | No | None | Filter by status: "pending", "processing", "completed", "failed" |

#### Response

```json
{
  "total": 150,
  "limit": 100,
  "offset": 0,
  "transcriptions": [
    {
      "id": 1,
      "task_id": "audio_20240108_120000",
      "filename": "meeting.mp4",
      "audio_path": "/app/output/meeting.mp4",
      "srt_path": "/app/output/meeting.srt",
      "model": "large-v3",
      "language": "zh",
      "status": "completed",
      "progress": 100,
      "current_step": "Completed",
      "created_at": "2024-01-08T12:00:00",
      "started_at": "2024-01-08T12:00:05",
      "completed_at": "2024-01-08T12:05:00",
      "metadata": {
        "file_size": 10485760,
        "srt_size": 4096
      }
    }
  ]
}
```

### 8. GET /transcription/{task_id}

Get a specific transcription record by task_id.

#### Response

```json
{
  "id": 1,
  "task_id": "audio_20240108_120000",
  "filename": "meeting.mp4",
  "audio_path": "/app/output/meeting.mp4",
  "srt_path": "/app/output/meeting.srt",
  "model": "large-v3",
  "language": "zh",
  "status": "completed",
  "progress": 100,
  "current_step": "Completed",
  "created_at": "2024-01-08T12:00:00",
  "started_at": "2024-01-08T12:00:05",
  "completed_at": "2024-01-08T12:05:00",
  "result": {
    "audio_file": "meeting.mp4",
    "srt_file": "meeting.srt",
    "srt_path": "/app/output/meeting.srt"
  },
  "metadata": {
    "file_size": 10485760,
    "srt_size": 4096
  }
}
```

### 9. GET /transcription/by-filename/{filename}

Get the most recent transcription for a specific filename.

#### Response

Same format as GET /transcription/{task_id}

### 10. DELETE /transcription/{task_id}

Delete a transcription record.

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| delete_files | bool | No | false | Whether to also delete associated audio and SRT files |

#### Response

```json
{
  "message": "Transcription deleted successfully",
  "task_id": "audio_20240108_120000",
  "files_deleted": [
    "/app/output/meeting.mp4",
    "/app/output/meeting.srt"
  ]
}
```

### 11. GET /v1/transcription/{transcription_id}/download

Download transcription audio and SRT files as a ZIP archive.

#### Request

- **Method**: GET
- **Path Parameter**: transcription_id (integer) - The ID of the transcription to download

#### Response

- **Success (200)**: Returns a ZIP file containing:
  - The original audio file (with cleaned filename)
  - The SRT subtitle file
  - Content-Type: application/zip
  - Content-Disposition: attachment; filename="transcription_{id}_{title}.zip"

- **Error (404)**: Transcription or files not found
  ```json
  {
    "detail": "Transcription not found" // or "Audio file not found" or "SRT file not found"
  }
  ```

- **Error (500)**: Failed to create archive
  ```json
  {
    "detail": "Failed to create download archive"
  }
  ```

#### Example Usage

```bash
# Download transcription files as ZIP
curl -O -J "http://localhost:8000/v1/transcription/123/download"

# Using wget
wget --content-disposition "http://localhost:8000/v1/transcription/123/download"

# Using Python
import requests

response = requests.get('http://localhost:8000/v1/transcription/123/download')
if response.status_code == 200:
    with open('transcription.zip', 'wb') as f:
        f.write(response.content)
```

### 12. POST /transcriptions/cleanup

Clean up transcriptions older than specified days.

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| days | int | No | 30 | Delete transcriptions older than this many days |
| delete_files | bool | No | false | Whether to also delete associated files |

#### Response

```json
{
  "message": "Cleaned up 25 transcriptions older than 30 days",
  "deleted_count": 25,
  "files_deleted": 50,
  "file_paths": [
    "/app/output/old_meeting1.mp4",
    "/app/output/old_meeting1.srt",
    // ... more files
  ]
}
```

### 13. GET /transcriptions/stats

Get statistics about transcriptions.

#### Response

```json
{
  "total_transcriptions": 150,
  "by_status": {
    "pending": 2,
    "processing": 1,
    "completed": 145,
    "failed": 2
  },
  "disk_usage": {
    "total_files": 290,
    "total_size_bytes": 5368709120,
    "total_size_mb": 5120.0,
    "total_size_gb": 5.0
  }
}
```

## Example Usage - Database Operations

### List all completed transcriptions

```bash
# Get completed transcriptions
curl "http://localhost:8000/transcriptions?status=completed&limit=50" | jq

# Get second page of results
curl "http://localhost:8000/transcriptions?offset=50&limit=50" | jq
```

### Search for a specific file

```bash
# Get transcription by filename
curl "http://localhost:8000/transcription/by-filename/meeting.mp4" | jq

# Get transcription by task ID
curl "http://localhost:8000/transcription/audio_20240108_120000" | jq
```

### Clean up old data

```bash
# Delete records older than 7 days (keep files)
curl -X POST "http://localhost:8000/transcriptions/cleanup?days=7" | jq

# Delete records and files older than 30 days
curl -X POST "http://localhost:8000/transcriptions/cleanup?days=30&delete_files=true" | jq
```

### Delete specific transcription

```bash
# Delete record only
curl -X DELETE "http://localhost:8000/transcription/audio_20240108_120000" | jq

# Delete record and associated files
curl -X DELETE "http://localhost:8000/transcription/audio_20240108_120000?delete_files=true" | jq
```

### Monitor disk usage

```bash
# Get transcription statistics including disk usage
curl "http://localhost:8000/transcriptions/stats" | jq

# Combined with system disk space
curl "http://localhost:8000/disk-space" | jq
```

## Database Location

The SQLite database file is stored at: `/app/output/meeting_helper.db`

This location ensures the database persists alongside the transcription files and can be easily backed up or accessed.

## Audio Streaming API

### 14. GET /v1/transcription/{transcription_id}/audio

Stream audio file with support for range requests. This endpoint is essential for audio players and waveform visualizers.

#### Request

- **Method**: GET
- **Path Parameter**: transcription_id (integer) - The ID of the transcription
- **Headers**:
  - Range (optional): Byte range for partial content requests (e.g., "bytes=0-1023")

#### Response

- **Success (200)**: Full audio file
  - Content-Type: Detected audio MIME type (audio/mpeg, audio/wav, etc.)
  - Headers:
    - Accept-Ranges: bytes
    - Content-Length: File size in bytes
    - Cache-Control: public, max-age=3600

- **Success (206)**: Partial content (when Range header is provided)
  - Content-Type: Detected audio MIME type
  - Headers:
    - Content-Range: bytes {start}-{end}/{total}
    - Accept-Ranges: bytes
    - Content-Length: Partial content length
    - Cache-Control: public, max-age=3600

- **Error (404)**: Transcription or audio file not found

#### Example Usage

```bash
# Stream entire audio file
curl "http://localhost:8000/v1/transcription/123/audio" -o audio.mp3

# Stream with range request (for seeking)
curl -H "Range: bytes=0-1048575" "http://localhost:8000/v1/transcription/123/audio"

# JavaScript example for audio element
const audio = new Audio(`http://localhost:8000/v1/transcription/123/audio`);
audio.play();
```

### 15. GET /v1/transcription/{transcription_id}/audio/info

Get audio file metadata without downloading the file.

#### Response

```json
{
  "transcription_id": 123,
  "filename": "meeting.mp4",
  "title": "Team Meeting 2024-01-08",
  "size_bytes": 10485760,
  "size_mb": 10.0,
  "duration": 300.5,
  "format": "mp4",
  "language": "zh",
  "created_at": "2024-01-08T12:00:00",
  "has_srt": true
}
```

### 16. GET /v1/transcription/{transcription_id}/srt

Get SRT subtitle content as plain text for synchronized playback.

#### Response

- **Success (200)**: SRT content as plain text
  - Content-Type: text/plain; charset=utf-8
  - Cache-Control: public, max-age=3600

- **Error (404)**: Transcription or SRT file not found

#### Example Usage

```bash
# Get SRT content
curl "http://localhost:8000/v1/transcription/123/srt"

# JavaScript example
fetch(`http://localhost:8000/v1/transcription/123/srt`)
  .then(res => res.text())
  .then(srtContent => {
    // Parse and display subtitles
    console.log(srtContent);
  });
```

## Frontend Integration Example

Here's how to use these endpoints with WaveSurfer.js:

```javascript
// Initialize WaveSurfer with the audio streaming endpoint
const wavesurfer = WaveSurfer.create({
  container: '#waveform',
  waveColor: '#4F4A85',
  progressColor: '#383351',
  backend: 'WebAudio'
});

// Load audio from the streaming endpoint
const audioUrl = `http://localhost:8000/v1/transcription/${transcriptionId}/audio`;
wavesurfer.load(audioUrl);

// Load and parse SRT subtitles
fetch(`http://localhost:8000/v1/transcription/${transcriptionId}/srt`)
  .then(res => res.text())
  .then(srtContent => {
    const subtitles = parseSRT(srtContent);
    // Sync subtitles with audio playback
  });
```
