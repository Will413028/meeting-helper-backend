"""Service for interacting with Ollama API for summary generation"""

import aiohttp
import asyncio
from typing import Optional
from src.logger import logger

# Configuration
OLLAMA_GENERATE_TIMEOUT = 900  # 15 minutes for generation
OLLAMA_CHECK_TIMEOUT = 10  # 10 seconds for availability check

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
    model: str = "deepseek-r1:14b",
    ollama_api_url: str = "http://localhost:11435/api/generate",
    max_tokens: int = 500,
) -> Optional[str]:
    """
    Generate a summary of the transcription using Ollama API

    Args:
        transcription_text: The full transcription text to summarize
        model: The Ollama model to use (default: llama3.2:latest)
        ollama_api_url: The Ollama API endpoint
        max_tokens: Maximum tokens for the summary

    Returns:
        The generated summary or None if failed
    """

    # Prepare the prompt for summary generation
    prompt = f"""請為以下會議記錄生成一個簡潔的摘要，包含主要討論點和決議事項：

{transcription_text}

摘要："""

    # Prepare the request payload
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": max_tokens,
            "temperature": 0.7,
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
                retry_delay *= 2  # Exponential backoff
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
                retry_delay *= 2  # Exponential backoff
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
    ollama_api_url: str = "http://localhost:11435/api/tags",
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
