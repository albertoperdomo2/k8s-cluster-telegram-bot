import logging
from functools import wraps
from typing import List
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


def require_authorization(authorized_users: List[int]):
    """Decorator to check if user is authorized to use bot commands"""

    def decorator(func):
        @wraps(func)
        async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
            user_id = update.effective_user.id
            username = update.effective_user.username or "Unknown"

            if user_id not in authorized_users:
                logger.warning(
                    f"Unauthorized access attempt from user {username} (ID: {user_id})"
                )
                await update.message.reply_text(
                    "🚫 Access denied. You are not authorized to use this bot."
                )
                return

            logger.info(
                f"Authorized command from user {username} (ID: {user_id}): {update.message.text}"
            )
            return await func(self, update, context)

        return wrapper

    return decorator


def is_authorized(user_id: int, authorized_users: List[int]) -> bool:
    """Check if user is authorized"""
    return user_id in authorized_users
