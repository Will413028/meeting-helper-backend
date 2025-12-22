"""Service for interacting with Ollama API for summary generation"""

import aiohttp
import asyncio
from typing import Optional, Dict
from src.core.logger import logger
import re
from collections import Counter
from src.core.config import settings
import opencc

# Configuration
OLLAMA_GENERATE_TIMEOUT = 300  # 5 minutes for generation
OLLAMA_CHECK_TIMEOUT = 30  # 30 seconds for availability check

# Create a shared connector with connection pooling
_connector = None


def get_connector():
    """Get or create a shared aiohttp connector with connection pooling"""
    global _connector
    if _connector is None or _connector.closed:
        _connector = aiohttp.TCPConnector(
            limit=100,  # Total connection pool size
            limit_per_host=30,  # Per-host connection limit
            ttl_dns_cache=300,  # DNS cache timeout
            enable_cleanup_closed=True,
        )
    return _connector


async def _make_ollama_request(
    url: str,
    method: str = "POST",
    json_data: Optional[Dict] = None,
    timeout: int = OLLAMA_GENERATE_TIMEOUT,
    max_retries: int = 3,
    retry_delay: int = 1,
) -> tuple[Optional[Dict], Optional[str]]:
    """
    Shared helper to make requests to Ollama API with retry logic.

    Returns:
        tuple[Optional[Dict], Optional[str]]: (response_json, error_message)
    """
    last_error = None

    for attempt in range(max_retries):
        try:
            # Use connector_owner=False to prevent closing the shared connector
            async with aiohttp.ClientSession(
                connector=get_connector(), connector_owner=False
            ) as session:
                request_kwargs = {
                    "timeout": aiohttp.ClientTimeout(total=timeout),
                }
                if json_data:
                    request_kwargs["json"] = json_data

                logger.debug(f"Making Ollama request to {url} (Attempt {attempt + 1})")
                async with session.request(method, url, **request_kwargs) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.debug(f"Ollama request to {url} successful")
                        return data, None
                    else:
                        error_text = await response.text()
                        msg = f"Ollama API error: {response.status} - {error_text}"
                        logger.error(msg)
                        return None, msg

        except (aiohttp.ClientConnectionError, OSError, IOError) as e:
            last_error = f"Network error: {e}"
            if attempt < max_retries - 1:
                logger.warning(
                    f"Network error on attempt {attempt + 1}/{max_retries}, retrying in {retry_delay}s: {e}"
                )
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
                continue
            logger.error(f"Network error after {max_retries} attempts: {e}")
            return None, last_error

        except (
            aiohttp.ServerTimeoutError,
            aiohttp.ConnectionTimeoutError,
            aiohttp.SocketTimeoutError,
        ) as e:
            last_error = f"Timeout error: {e}"
            if attempt < max_retries - 1:
                logger.warning(
                    f"Timeout on attempt {attempt + 1}/{max_retries}, retrying in {retry_delay}s: {e}"
                )
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
                continue
            msg = f"Ollama API request timed out after {max_retries} attempts"
            logger.error(msg)
            return None, msg

        except aiohttp.ClientError as e:
            msg = f"HTTP client error interacting with Ollama: {e}"
            logger.error(msg)
            return None, msg
        except (ValueError, TypeError, KeyError) as e:
            msg = f"Data error interacting with Ollama: {e}"
            logger.error(msg)
            return None, msg
        except Exception as e:
            msg = f"Unexpected error interacting with Ollama: {type(e).__name__}: {e}"
            logger.error(msg)
            return None, msg

    return None, last_error or "Unknown error"


async def generate_summary(
    transcription_text: str,
    model: str,
    language: str = "zh",
    ollama_api_url: str = f"{settings.OLLAMA_API_URL}/api/generate",
) -> tuple[Optional[str], Optional[str]]:
    """
    Generate a summary of the transcription using Ollama API

    Args:
        transcription_text: The full transcription text to summarize
        model: The Ollama model to use
        language: Language for the summary (default: "zh" for Chinese, "en" for English)
        ollama_api_url: The Ollama API endpoint

    Returns:
        A tuple of (summary, error_message).
        If successful, summary is str and error_message is None.
        If failed, summary is None and error_message contains the reason.
    """

    # 根據語言選擇不同的 prompt 模板
    prompts = {
        "zh": f"""/nothink
你是專業的會議記錄摘要助手。請嚴格按照以下 Markdown 格式輸出會議摘要。

重要規則：
- 只能根據逐字稿內容進行摘要，禁止添加任何逐字稿中沒有提到的資訊
- 如果逐字稿中沒有提到某個區段的內容，請直接省略該區段
- 不要猜測或編造任何資訊

輸出格式要求：
- 必須使用繁體中文
- 必須使用 Markdown 標題 (##) 格式
- 歸納總結，不要逐字複述對話

請直接輸出以下格式的摘要（不要輸出其他內容）：

## 會議主題與目的

（用 1-2 段文字說明會議的主要目的和背景，約 100 字）

## 主要討論事項

1. **議題一標題**：用 2-3 句話說明討論內容和重點。
2. **議題二標題**：用 2-3 句話說明討論內容和重點。
3. **議題三標題**：用 2-3 句話說明討論內容和重點。

## 重要決議與結論

1. 說明具體的決定或結論
2. 說明具體的決定或結論

## 待辦事項與後續行動

1. 行動項目一：負責人、截止日期（如有提到）
2. 行動項目二：負責人、截止日期（如有提到）

## 其他重要資訊

補充說明其他相關的重要信息。

---

會議逐字稿如下：

{transcription_text}

---

請嚴格按照上述 Markdown 格式輸出摘要：""",
        "en": f"""/nothink
You are a professional meeting summary assistant. Please output the meeting summary strictly in the following Markdown format.

IMPORTANT RULES:
- Only summarize content that is explicitly mentioned in the transcript
- Do NOT add any information not present in the transcript
- If a section has no relevant content in the transcript, omit that section entirely
- Do NOT guess or fabricate any information

Output requirements:
- Must use Markdown headings (##)
- Summarize and synthesize, do not repeat dialogue verbatim

Please output the summary in the following format (no other content):

## Meeting Topic and Purpose

(1-2 paragraphs explaining the main purpose and background of the meeting, about 100 words)

## Main Discussion Points

1. **Topic One**: 2-3 sentences explaining the discussion content and key points.
2. **Topic Two**: 2-3 sentences explaining the discussion content and key points.
3. **Topic Three**: 2-3 sentences explaining the discussion content and key points.

## Important Decisions and Conclusions

1. Explain the specific decision or conclusion
2. Explain the specific decision or conclusion

## Action Items and Follow-ups

1. Action item one: Responsible person, deadline (if mentioned)
2. Action item two: Responsible person, deadline (if mentioned)

## Other Important Information

Supplementary notes on any other relevant important information.

---

Meeting transcript:

{transcription_text}

---

Please strictly follow the Markdown format above to output the summary:""",
    }

    # 獲取對應語言的 prompt
    prompt = prompts.get(language.lower(), prompts["zh"])

    # Prepare the request payload
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }

    result, error_msg = await _make_ollama_request(
        ollama_api_url, json_data=payload, timeout=OLLAMA_GENERATE_TIMEOUT
    )

    if result:
        summary = result.get("response", "").strip()
        if summary:
            if model == "qwen3:30b":
                # Remove thinking tags from Qwen3 models
                if "<think>" in summary:
                    if "</think>" in summary:
                        summary = summary.split("</think>")[-1].strip()
                    else:
                        summary = summary.split("<think>")[0].strip()
                
                # Remove any remaining XML-like tags
                summary = re.sub(r"<[^>]+>", "", summary).strip()
            
            if language.lower() == "zh" and summary:
                try:
                    converter = opencc.OpenCC("s2twp")
                    summary = converter.convert(summary)
                    logger.info("Converted summary to Traditional Chinese")
                except Exception as e:
                    logger.warning(f"Failed to convert summary to Traditional Chinese: {e}")

            logger.info(
                f"Successfully generated summary with {len(summary)} characters"
            )
            return summary, None
        else:
            msg = "Empty summary received from Ollama"
            logger.error(msg)
            return None, msg
    else:
        return None, error_msg


async def check_ollama_availability(
    ollama_api_url: str = f"{settings.OLLAMA_API_URL}/api/tags",
) -> bool:
    """
    Check if Ollama API is available and has models

    Args:
        ollama_api_url: The Ollama API endpoint for listing models

    Returns:
        True if Ollama is available, False otherwise
    """
    result, _ = await _make_ollama_request(
        ollama_api_url, method="GET", timeout=OLLAMA_CHECK_TIMEOUT
    )
    if result:
        models = result.get("models", [])
        if models:
            logger.info(f"Ollama is available with {len(models)} models")
            return True
        else:
            logger.warning("Ollama is available but no models found")
            return False
    return False


async def _generate_fallback_tags(
    transcription_text: str, max_tags: int = 8
) -> Optional[list]:
    """
    Generate fallback tags using simple keyword extraction when Ollama fails

    Args:
        transcription_text: The transcription text
        max_tags: Maximum number of tags to generate

    Returns:
        A list of fallback tags or None
    """
    try:
        # Common stop words in Chinese
        stop_words = {
            "的",
            "了",
            "在",
            "是",
            "我",
            "有",
            "和",
            "就",
            "不",
            "人",
            "都",
            "一",
            "一個",
            "這",
            "那",
            "大",
            "中",
            "上",
            "個",
            "地",
            "為",
            "子",
            "他",
            "來",
            "發",
            "說",
            "們",
            "到",
            "作",
            "要",
            "會",
            "用",
            "也",
            "去",
            "過",
            "很",
            "還",
            "可以",
            "這個",
            "那個",
            "什麼",
            "怎麼",
            "因為",
            "所以",
            "但是",
            "如果",
            "或者",
            "然後",
            "現在",
            "已經",
            "可能",
            "應該",
            "需要",
            "進行",
            "通過",
            "這樣",
        }

        # Extract Chinese words (2-4 characters)
        chinese_pattern = r"[\u4e00-\u9fff]{2,4}"
        words = re.findall(chinese_pattern, transcription_text)

        # Filter out stop words and count frequency
        word_counts = Counter(word for word in words if word not in stop_words)

        # Get most common words as tags
        tags = []
        for word, count in word_counts.most_common(max_tags * 2):
            if len(tags) >= max_tags:
                break
            if 2 <= len(word) <= 5:
                tags.append(word)

        if tags:
            logger.info(f"Generated {len(tags)} fallback tags: {tags}")
            return tags
        else:
            # If no tags found, return some generic tags
            return ["會議記錄", "討論內容"]

    except Exception as e:
        logger.error(f"Error generating fallback tags: {e}")
        return ["會議記錄"]


def _parse_tags_response(tags_text: str, max_tags: int = 8) -> Optional[list]:
    """
    Parse and clean tags from Ollama response text.

    Args:
        tags_text: Raw text response from Ollama
        max_tags: Maximum number of tags to keep

    Returns:
        List of cleaned tags or None if parsing fails
    """
    if not tags_text:
        return None

    # Clean up the response - remove any thinking process
    if "<think>" in tags_text:
        if "</think>" in tags_text:
            tags_text = tags_text.split("</think>")[-1].strip()
        else:
            tags_text = tags_text.split("<think>")[0].strip()

    # Remove any remaining XML-like tags
    tags_text = re.sub(r"<[^>]+>", "", tags_text).strip()

    # If response contains explanations, try to extract tags
    if "：" in tags_text or ":" in tags_text:
        parts = re.split(r"[:：]", tags_text)
        if len(parts) > 1:
            tags_text = parts[-1].strip()

    # Remove numbered lists
    tags_text = re.sub(r"\d+\.\s*", "", tags_text)

    # Extract only the first line if multiple lines
    lines = tags_text.strip().split("\n")
    tags_text = lines[0].strip()

    # Remove common explanation phrases
    explanation_patterns = [
        r"^.*?標籤[是為有]?[:：]?\s*",
        r"^.*?tags?[是為有]?[:：]?\s*",
        r"^.*?關鍵詞[是為有]?[:：]?\s*",
        r"^.*?主題[是為有]?[:：]?\s*",
    ]
    for pattern in explanation_patterns:
        tags_text = re.sub(pattern, "", tags_text, flags=re.IGNORECASE)

    # Parse tags from the response
    tags = []

    # Try different separators
    potential_tags = tags_text.split(",")
    if len(potential_tags) == 1 and "，" in tags_text:
        potential_tags = tags_text.split("，")
    if len(potential_tags) == 1 and "、" in tags_text:
        potential_tags = tags_text.split("、")

    for tag in potential_tags:
        tag = tag.strip()
        # Remove quotes
        tag = tag.strip('"\'""')

        # Skip if tag contains sentence-ending punctuation
        if any(p in tag for p in ["。", ".", "！", "!", "？", "?"]):
            continue

        # Count words
        if any("\u4e00" <= c <= "\u9fff" for c in tag):
            word_count = len(tag)
        else:
            word_count = len(tag.split())

        # Filter tags
        if tag and not tag.startswith("<") and 1 <= word_count <= 5 and len(tag) <= 20:
            tags.append(tag)

    if tags:
        return tags[:max_tags]
    return None


async def generate_tags(
    transcription_text: str,
    model: str = "llama3.2:latest",
    ollama_api_url: str = f"{settings.OLLAMA_API_URL}/api/generate",
    max_tags: int = 8,
) -> Optional[list]:
    """
    Generate tags for the transcription using Ollama API

    Args:
        transcription_text: The full transcription text to generate tags from
        model: The Ollama model to use
        ollama_api_url: The Ollama API endpoint
        max_tags: Maximum number of tags to generate (default: 8)

    Returns:
        A list of tags (1-5 words each) or None if failed
    """

    # Prepare the prompt for tag generation with very explicit instructions
    prompt = f"""你是一個標籤生成器。你的任務是為會議記錄生成標籤。

重要：只輸出標籤，用逗號分隔，不要輸出任何其他內容。
不要解釋，不要描述，只要標籤。

範例輸出格式：
會議討論, 專案進度, 技術問題, 預算規劃

要求：
- 生成 1 到 {max_tags} 個標籤
- 每個標籤 1-5 個字
- 使用繁體中文
- 不要標點符號

會議記錄：
{transcription_text[:1000]}...

標籤（只輸出標籤，逗號分隔）："""

    # Prepare the request payload
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": 50,
            "temperature": 0.1,
            "top_p": 0.9,
            "repeat_penalty": 1.1,
        },
    }

    result, _ = await _make_ollama_request(
        ollama_api_url, json_data=payload, timeout=OLLAMA_GENERATE_TIMEOUT
    )

    if result:
        tags_text = result.get("response", "").strip()
        logger.debug(f"Raw Ollama response for tags: {tags_text}")

        if tags_text:
            tags = _parse_tags_response(tags_text, max_tags)
            if tags:
                logger.info(f"Successfully generated {len(tags)} tags: {tags}")
                return tags
            else:
                logger.error(
                    f"No valid tags extracted from Ollama response: {tags_text[:200]}"
                )
                return await _generate_fallback_tags(transcription_text, max_tags)
        else:
            logger.error("Empty tags response received from Ollama")
            return None

    return None
