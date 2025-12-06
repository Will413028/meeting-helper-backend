import re
from src.logger import logger


def replace_speaker_names(
    content: str, name_changes: list[tuple[str, str]], context_name: str = "text"
) -> str:
    """
    Replace multiple speaker names in content string using smart patterns for English and CJK.

    Args:
        content: The text to update
        name_changes: List of (old_name, new_name) tuples
        context_name: Name of the content being updated (for logging), e.g., "SRT" or "summary"

    Returns:
        Updated content string
    """
    if not content or not name_changes:
        return content

    updated_content = content

    for old_name, new_name in name_changes:
        logger.debug(
            f"Attempting to replace '{old_name}' with '{new_name}' in {context_name}"
        )

        # Pattern 1: Match exact name with word boundaries (for English/alphanumeric)
        pattern1 = r"\b" + re.escape(old_name) + r"\b"

        # Pattern 2: Match Chinese format like "講者4" or other CJK characters
        # This pattern looks for the name followed by common Chinese punctuation or whitespace
        pattern2 = re.escape(old_name) + r"(?=[\s，。、：；！？）」』]|$)"

        # Pattern 3: Match name preceded by common Chinese punctuation
        pattern3 = r"(?<=[\s，。、：；！？（「『])" + re.escape(old_name)

        temp_content = updated_content

        # Try all patterns
        updated_content = re.sub(pattern1, new_name, updated_content)
        updated_content = re.sub(pattern2, new_name, updated_content)
        updated_content = re.sub(pattern3, new_name, updated_content)

        if temp_content != updated_content:
            logger.info(
                f"Successfully replaced '{old_name}' with '{new_name}' in {context_name}"
            )
        else:
            logger.warning(f"No matches found for '{old_name}' in {context_name}")

    return updated_content
