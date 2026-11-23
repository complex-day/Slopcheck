import logging

logger = logging.getLogger(__name__)


class CustomError(Exception):
    pass


def handle_with_care(data: str):
    # Proper logging
    try:
        value = int(data)
    except Exception as e:
        logger.exception("Failed to parse integer: %s", e)
        return None

    # Re-raising with context
    try:
        process(value)
    except Exception as e:
        raise CustomError("Processing failed") from e

    # Recovery handling
    try:
        result = compute(value)
    except Exception:
        result = fallback_value()
        return result

    # Cleanup with re-raise
    try:
        save(result)
    except Exception as e:
        logger.error("Saving failed: %s", e)
        raise
