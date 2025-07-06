# Transcript Segments API Documentation

This document describes the API endpoints for managing interactive transcript segments with speaker identification and real-time synchronization support.

## Overview

The Transcript Segments API provides full CRUD operations for managing transcript segments, speakers, and export functionality. It supports:

- Automatic initialization from existing SRT files
- Real-time segment lookup for audio synchronization
- Speaker management with custom names and colors
- Segment editing, merging, and splitting
- Multiple export formats (SRT, VTT, TXT, JSON)
- Bulk operations for efficiency

## Database Schema

### New Tables

1. **speakers** - Stores speaker information per transcription
   - `speaker_id` (PK)
   - `transcription_id` (FK)
   - `speaker_identifier` (e.g., "SPEAKER_00")
   - `display_name` (e.g., "講者1" or custom name)
   - `color` (hex color for UI)
   - `order_index`

2. **transcript_segments** - Stores individual transcript segments
   - `segment_id` (PK)
   - `transcription_id` (FK)
   - `speaker_id` (FK)
   - `sequence_number`
   - `start_time` / `end_time` (SRT format)
   - `start_seconds` / `end_seconds` (numeric)
   - `content` (transcript text)
   - `is_edited` (boolean)

## API Endpoints

### 1. Get Transcript Segments

```http
GET /api/v1/transcription/{transcription_id}/segments
```

Query Parameters:
- `include_speakers` (boolean, default: true) - Include speaker information
- `start_time` (float, optional) - Filter segments from this time (seconds)
- `end_time` (float, optional) - Filter segments until this time (seconds)

Response:
```json
{
  "data": {
    "transcription_id": 123,
    "speakers": [
      {
        "speaker_id": 1,
        "transcription_id": 123,
        "speaker_identifier": "SPEAKER_00",
        "display_name": "講者1",
        "color": "#6366f1",
        "order_index": 0,
        "created_at": "2025-07-05T15:00:00",
        "updated_at": "2025-07-05T15:00:00"
      }
    ],
    "segments": [
      {
        "segment_id": 1,
        "transcription_id": 123,
        "speaker_id": 1,
        "sequence_number": 1,
        "start_time": "00:00:02,000",
        "end_time": "00:00:08,000",
        "start_seconds": 2.0,
        "end_seconds": 8.0,
        "content": "逐字稿內容...",
        "is_edited": false,
        "created_at": "2025-07-05T15:00:00",
        "updated_at": "2025-07-05T15:00:00"
      }
    ],
    "total_segments": 50
  }
}
```

### 2. Update Segment Content

```http
PUT /api/v1/transcription/{transcription_id}/segment/{segment_id}
```

Request Body:
```json
{
  "content": "Updated transcript text",
  "speaker_id": 2  // optional
}
```

### 3. Update Speaker Information

```http
PUT /api/v1/transcription/{transcription_id}/speaker/{speaker_id}
```

Request Body:
```json
{
  "display_name": "張三",
  "color": "#10b981"
}
```

### 4. Merge Segments

```http
POST /api/v1/transcription/{transcription_id}/segments/merge
```

Request Body:
```json
{
  "segment_ids": [1, 2, 3]  // Must be consecutive segments
}
```

### 5. Split Segment

```http
POST /api/v1/transcription/{transcription_id}/segment/{segment_id}/split
```

Request Body:
```json
{
  "split_at_seconds": 5.5,
  "split_text_at": 25  // optional, character position
}
```

### 6. Get Segment at Time (for real-time sync)

```http
GET /api/v1/transcription/{transcription_id}/segment/at-time/{seconds}
```

Response:
```json
{
  "data": {
    "segment": { /* current segment */ },
    "previous_segment": { /* previous segment */ },
    "next_segment": { /* next segment */ }
  }
}
```

### 7. Bulk Update Segments

```http
PUT /api/v1/transcription/{transcription_id}/segments/bulk-update
```

Request Body:
```json
{
  "segments": [
    {"segment_id": 1, "content": "Updated text", "speaker_id": 2},
    {"segment_id": 2, "content": "Another update"},
    {"segment_id": 3, "speaker_id": 1}
  ]
}
```

### 8. Export Transcript

```http
GET /api/v1/transcription/{transcription_id}/export?format=srt
```

Query Parameters:
- `format` - Export format: `srt`, `vtt`, `txt`, or `json`

## Frontend Integration Guide

### 1. Initial Load

```javascript
// Load transcript segments when component mounts
const response = await fetch(`/api/v1/transcription/${transcriptionId}/segments`);
const { data } = await response.json();
const { speakers, segments } = data;
```

### 2. Real-time Audio Sync

```javascript
// Update current segment as audio plays
audioPlayer.addEventListener('timeupdate', async (e) => {
  const currentTime = e.target.currentTime;
  const response = await fetch(
    `/api/v1/transcription/${transcriptionId}/segment/at-time/${currentTime}`
  );
  const { data } = await response.json();
  highlightSegment(data.segment);
});
```

### 3. Click to Seek

```javascript
// Jump to segment time when clicked
function onSegmentClick(segment) {
  audioPlayer.currentTime = segment.start_seconds;
  audioPlayer.play();
}
```

### 4. Inline Editing

```javascript
// Save segment changes
async function saveSegment(segmentId, newContent) {
  await fetch(`/api/v1/transcription/${transcriptionId}/segment/${segmentId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content: newContent })
  });
}
```

### 5. Speaker Management

```javascript
// Update speaker name and color
async function updateSpeaker(speakerId, displayName, color) {
  await fetch(`/api/v1/transcription/${transcriptionId}/speaker/${speakerId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ display_name: displayName, color: color })
  });
}
```

## Migration Notes

1. Run the database migration to create new tables:
   ```bash
   alembic upgrade head
   ```

2. Existing transcriptions will automatically initialize segments from SRT files on first access

3. The original SRT files are preserved and can be regenerated from segments

## Performance Considerations

1. **Indexes**: The schema includes indexes on `transcription_id`, `start_seconds`, and `sequence_number` for fast queries

2. **Bulk Operations**: Use bulk update endpoint when modifying multiple segments

3. **Caching**: Consider caching segment data on the frontend and using WebSocket for real-time updates in collaborative scenarios

4. **Pagination**: For very long transcripts, implement virtual scrolling or pagination on the frontend

## Error Handling

All endpoints return standard HTTP status codes:
- `200` - Success
- `404` - Resource not found
- `400` - Bad request (invalid parameters)
- `500` - Server error

Error response format:
```json
{
  "detail": "Error message"
}