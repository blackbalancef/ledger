"""Date parsing utilities for report date inputs."""

from datetime import datetime
from typing import Tuple
from loguru import logger


def parse_single_date(date_str: str) -> datetime:
    """
    Parse a single date in DD.MM.YYYY or DD.MM format.

    Args:
        date_str: Date string in DD.MM.YYYY or DD.MM format (DD.MM uses current year)

    Returns:
        datetime object

    Raises:
        ValueError: If date format is invalid or date is invalid
    """
    date_str = date_str.strip()
    
    try:
        # Try DD.MM.YYYY format first
        if date_str.count(".") == 2:
            date_obj = datetime.strptime(date_str, "%d.%m.%Y")
            return date_obj
        # Try DD.MM format (use current year)
        elif date_str.count(".") == 1:
            current_year = datetime.utcnow().year
            date_obj = datetime.strptime(f"{date_str}.{current_year}", "%d.%m.%Y")
            return date_obj
        else:
            raise ValueError("Invalid date format")
    except ValueError as e:
        logger.error(f"Failed to parse date '{date_str}': {e}")
        raise ValueError(
            f"Invalid date format. Please use DD.MM.YYYY or DD.MM format (e.g., 15.03.2024 or 15.09)."
        ) from e


def parse_date_range(date_str: str) -> Tuple[datetime, datetime]:
    """
    Parse a date range string.

    Supports:
    - DD.MM-DD.MM (uses current year for both dates)
    - DD.MM.YYYY - DD.MM.YYYY (full date range with year)

    Args:
        date_str: Date range string

    Returns:
        Tuple of (start_date, end_date) datetime objects

    Raises:
        ValueError: If date format is invalid or dates are invalid
    """
    date_str = date_str.strip()
    
    # Check if it contains a dash (date range)
    if "-" not in date_str:
        raise ValueError(
            "Invalid date range format. Please use DD.MM-DD.MM or "
            "DD.MM.YYYY - DD.MM.YYYY format."
        )
    
    # Split by dash
    parts = date_str.split("-", 1)
    if len(parts) != 2:
        raise ValueError(
            "Invalid date range format. Please use DD.MM-DD.MM or "
            "DD.MM.YYYY - DD.MM.YYYY format."
        )
    
    start_str = parts[0].strip()
    end_str = parts[1].strip()
    
    # Determine if year is included
    # If start_str has 2 dots, it includes year (DD.MM.YYYY)
    # If start_str has 1 dot, it's DD.MM format
    start_has_year = start_str.count(".") == 2
    end_has_year = end_str.count(".") == 2
    
    current_year = datetime.utcnow().year
    
    try:
        if start_has_year and end_has_year:
            # Both have years: DD.MM.YYYY - DD.MM.YYYY
            start_date = datetime.strptime(start_str, "%d.%m.%Y")
            end_date = datetime.strptime(end_str, "%d.%m.%Y")
        elif not start_has_year and not end_has_year:
            # Neither has year: DD.MM-DD.MM (use current year)
            start_date = datetime.strptime(f"{start_str}.{current_year}", "%d.%m.%Y")
            end_date = datetime.strptime(f"{end_str}.{current_year}", "%d.%m.%Y")
        else:
            raise ValueError(
                "Both dates in the range must have the same format. "
                "Use either DD.MM-DD.MM or DD.MM.YYYY - DD.MM.YYYY."
            )
        
        # Validate that start_date <= end_date
        if start_date > end_date:
            raise ValueError("Start date must be before or equal to end date.")
        
        # Set end_date to end of day (23:59:59)
        end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        return start_date, end_date
        
    except ValueError as e:
        # Re-raise with more context if it's our custom error
        if "Start date must be" in str(e) or "Both dates" in str(e):
            raise
        logger.error(f"Failed to parse date range '{date_str}': {e}")
        raise ValueError(
            f"Invalid date range format. Please use DD.MM-DD.MM or "
            f"DD.MM.YYYY - DD.MM.YYYY format (e.g., 01.03-15.03 or 01.03.2024 - 15.03.2024)."
        ) from e

