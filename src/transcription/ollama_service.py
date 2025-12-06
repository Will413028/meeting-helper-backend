"""Service for interacting with Ollama API for summary generation"""

import aiohttp
import asyncio
from typing import Optional
from src.logger import logger
import re
from collections import Counter
from src.config import settings

# Configuration
OLLAMA_GENERATE_TIMEOUT = 1200  # 20 minutes for generation
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


async def generate_summary(
    transcription_text: str,
    language: str = "zh",
    model: str = "llama3.2:latest",
    ollama_api_url: str = f"{settings.OLLAMA_API_URL}/api/generate",
    max_tokens: int = 1500,
) -> Optional[str]:
    """
    Generate a summary of the transcription using Ollama API

    Args:
        transcription_text: The full transcription text to summarize
        language: Language for the summary (default: "zh" for Chinese, "en" for English)
        model: The Ollama model to use (default: llama3.2:latest)
        ollama_api_url: The Ollama API endpoint
        max_tokens: Maximum tokens for the summary

    Returns:
        The generated summary or None if failed
    """

    # 根據語言選擇不同的 prompt 模板
    prompts = {
        "zh": f"""你是一個專業的會議記錄摘要助手。請根據以下會議逐字稿生成一個結構化的摘要。

**重要規則：**
1. 使用繁體中文輸出
2. 摘要必須至少 500 字
3. 不要重複逐字稿的對話內容，要歸納總結
4. 使用結構化的條列式格式
5. 不要添加免責聲明、重要提醒、注意事項或任何額外的說明文字
6. 摘要結束後就停止，不要有任何補充說明
7. 不要說「本摘要僅供參考」、「如需更多資訊請參考原文」等話語

**必須包含的區段：**

## 會議主題與目的
[用 1-2 段文字說明會議的主要目的和背景]

## 主要討論事項
1. [議題一：用 2-3 句話說明討論內容和重點]
2. [議題二：用 2-3 句話說明討論內容和重點]
3. [議題三：用 2-3 句話說明討論內容和重點]

## 重要決議與結論
1. [決議一：說明具體的決定或結論]
2. [決議二：說明具體的決定或結論]

## 待辦事項與後續行動
1. [行動項目一：負責人、截止日期（如有提到）]
2. [行動項目二：負責人、截止日期（如有提到）]

## 其他重要資訊
[補充說明任何其他相關的重要信息]

---

**會議逐字稿：**
{transcription_text}

**嚴格按照上述格式生成摘要**""",
        "en": f"""You are a professional meeting summary assistant. Generate a structured summary based on the following meeting transcript.

**Important Rules:**
1. The summary must be at least 500 words
2. Do NOT repeat dialogue content from the transcript - summarize and synthesize
3. Use structured bullet point format
4. Do NOT add disclaimers, reminders, notes, or any additional explanatory text
5. Stop immediately after the summary ends
6. Do NOT say things like "This summary is for reference only" or "For more details, refer to the original"

**Required Sections:**

## Meeting Topic and Purpose
[1-2 paragraphs explaining the main purpose and background of the meeting]

## Main Discussion Points
1. [Topic 1: 2-3 sentences explaining the discussion content and key points]
2. [Topic 2: 2-3 sentences explaining the discussion content and key points]
3. [Topic 3: 2-3 sentences explaining the discussion content and key points]

## Important Decisions and Conclusions
1. [Decision 1: Explain the specific decision or conclusion]
2. [Decision 2: Explain the specific decision or conclusion]

## Action Items and Follow-ups
1. [Action item 1: Responsible person, deadline (if mentioned)]
2. [Action item 2: Responsible person, deadline (if mentioned)]

## Other Important Information
[Supplementary notes on any other relevant important information]

---

**Meeting Transcript:**
{transcription_text}

**Please strictly follow the format above and stop immediately after the summary without any additional notes:**""",
    }

    # 獲取對應語言的 prompt
    prompt = prompts.get(language.lower(), prompts["zh"])

    # Prepare the request payload
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": max_tokens,
            "temperature": 0.3,
            "top_p": 0.9,
            "repeat_penalty": 1.2,
        },
    }

    # Retry logic for transient network errors
    max_retries = 3
    retry_delay = 1

    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession(connector=get_connector()) as session:
                async with session.post(
                    ollama_api_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=OLLAMA_GENERATE_TIMEOUT),
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        summary = result.get("response", "").strip()

                        if summary:
                            # Check if summary meets minimum length requirement
                            if len(summary) < 100:
                                logger.warning(
                                    f"Generated summary is too short ({len(summary)} characters), regenerating..."
                                )
                                # 根據語言準備增強的提示詞
                                length_reminder = {
                                    "zh": "\n\n請注意：摘要必須至少500字以上，請提供更詳細的內容。記得使用繁體中文，不要添加任何提醒。",
                                    "en": "\n\nPlease note: The summary must be at least 100 words. Please provide more detailed content. Do not add any reminders.",
                                }
                                enhanced_prompt = prompt + length_reminder.get(
                                    language.lower(), length_reminder["zh"]
                                )

                                enhanced_payload = {
                                    "model": model,
                                    "prompt": enhanced_prompt,
                                    "stream": False,
                                    "options": {
                                        "num_predict": max_tokens * 2,
                                        "temperature": 0.3,
                                        "top_p": 0.9,
                                        "repeat_penalty": 1.2,
                                        "stop": payload["options"]["stop"],
                                    },
                                }
                                async with session.post(
                                    ollama_api_url,
                                    json=enhanced_payload,
                                    timeout=aiohttp.ClientTimeout(
                                        total=OLLAMA_GENERATE_TIMEOUT
                                    ),
                                ) as retry_response:
                                    if retry_response.status == 200:
                                        retry_result = await retry_response.json()
                                        summary = retry_result.get(
                                            "response", ""
                                        ).strip()

                            logger.info(
                                f"Successfully generated summary with {len(summary)} characters"
                            )
                            return summary
                        else:
                            logger.error("Empty summary received from Ollama")
                            return None
                    else:
                        error_text = await response.text()
                        logger.error(
                            f"Ollama API error: {response.status} - {error_text}"
                        )
                        return None

        except (aiohttp.ClientConnectionError, OSError, IOError) as e:
            if attempt < max_retries - 1:
                logger.warning(
                    f"Network error on attempt {attempt + 1}/{max_retries}, retrying in {retry_delay}s: {e}"
                )
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
                continue
            else:
                logger.error(f"Network error after {max_retries} attempts: {e}")
                return None
        except (
            aiohttp.ServerTimeoutError,
            aiohttp.ConnectionTimeoutError,
            aiohttp.SocketTimeoutError,
        ) as e:
            if attempt < max_retries - 1:
                logger.warning(
                    f"Timeout on attempt {attempt + 1}/{max_retries}, retrying in {retry_delay}s: {e}"
                )
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
                continue
            else:
                logger.error(
                    f"Ollama API request timed out after {max_retries} attempts"
                )
                return None
        except aiohttp.ClientError as e:
            logger.error(f"HTTP client error generating summary with Ollama: {e}")
            return None
        except (ValueError, TypeError, KeyError) as e:
            logger.error(f"Data error generating summary with Ollama: {e}")
            return None
        except Exception as e:
            logger.error(
                f"Unexpected error generating summary with Ollama: {type(e).__name__}: {e}"
            )
            return None


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
    try:
        async with aiohttp.ClientSession(connector=get_connector()) as session:
            async with session.get(
                ollama_api_url,
                timeout=aiohttp.ClientTimeout(total=OLLAMA_CHECK_TIMEOUT),
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    models = result.get("models", [])
                    if models:
                        logger.info(f"Ollama is available with {len(models)} models")
                        return True
                    else:
                        logger.warning("Ollama is available but no models found")
                        return False
                else:
                    logger.error(f"Ollama API returned status {response.status}")
                    return False

    except (
        aiohttp.ServerTimeoutError,
        aiohttp.ConnectionTimeoutError,
        aiohttp.SocketTimeoutError,
    ):
        logger.error("Timeout checking Ollama availability")
        return False
    except aiohttp.ClientError as e:
        logger.error(f"HTTP client error checking Ollama availability: {e}")
        return False
    except (OSError, IOError) as e:
        logger.error(f"Network error checking Ollama availability: {e}")
        return False
    except Exception as e:
        logger.error(
            f"Unexpected error checking Ollama availability: {type(e).__name__}: {e}"
        )
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

    # Retry logic for transient network errors
    max_retries = 3
    retry_delay = 1

    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession(connector=get_connector()) as session:
                async with session.post(
                    ollama_api_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=OLLAMA_GENERATE_TIMEOUT),
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        tags_text = result.get("response", "").strip()
                        logger.debug(f"Raw Ollama response for tags: {tags_text}")

                        if tags_text:
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
                                tags_text = re.sub(
                                    pattern, "", tags_text, flags=re.IGNORECASE
                                )

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
                                if any(
                                    p in tag for p in ["。", ".", "！", "!", "？", "?"]
                                ):
                                    continue

                                # Count words
                                if any("\u4e00" <= c <= "\u9fff" for c in tag):
                                    word_count = len(tag)
                                else:
                                    word_count = len(tag.split())

                                # Filter tags
                                if (
                                    tag
                                    and not tag.startswith("<")
                                    and 1 <= word_count <= 5
                                    and len(tag) <= 20
                                ):
                                    tags.append(tag)

                            # Limit to max_tags
                            if tags:
                                tags = tags[:max_tags]
                                logger.info(
                                    f"Successfully generated {len(tags)} tags: {tags}"
                                )
                                return tags
                            else:
                                logger.error(
                                    f"No valid tags extracted from Ollama response: {tags_text[:200]}"
                                )
                                return await _generate_fallback_tags(
                                    transcription_text, max_tags
                                )
                        else:
                            logger.error("Empty tags response received from Ollama")
                            return None
                    else:
                        error_text = await response.text()
                        logger.error(
                            f"Ollama API error: {response.status} - {error_text}"
                        )
                        return None

        except (aiohttp.ClientConnectionError, OSError, IOError) as e:
            if attempt < max_retries - 1:
                logger.warning(
                    f"Network error on attempt {attempt + 1}/{max_retries}, retrying in {retry_delay}s: {e}"
                )
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
                continue
            else:
                logger.error(f"Network error after {max_retries} attempts: {e}")
                return None
        except (
            aiohttp.ServerTimeoutError,
            aiohttp.ConnectionTimeoutError,
            aiohttp.SocketTimeoutError,
        ) as e:
            if attempt < max_retries - 1:
                logger.warning(
                    f"Timeout on attempt {attempt + 1}/{max_retries}, retrying in {retry_delay}s: {e}"
                )
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
                continue
            else:
                logger.error(
                    f"Ollama API request timed out after {max_retries} attempts"
                )
                return None
        except aiohttp.ClientError as e:
            logger.error(f"HTTP client error generating tags with Ollama: {e}")
            return None
        except (ValueError, TypeError, KeyError) as e:
            logger.error(f"Data error generating tags with Ollama: {e}")
            return None
        except Exception as e:
            logger.error(
                f"Unexpected error generating tags with Ollama: {type(e).__name__}: {e}"
            )
            return None
