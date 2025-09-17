import asyncio
import logging
import os
import sys
from datetime import datetime
from typing import Dict, List

from aiohttp import web
from telegram.ext import Application

from .handlers.commands import CommandHandlers
from .handlers.callbacks import CallbackHandlers
from .handlers.messages import MessageHandlers
from .kubernetes.client import KubernetesClient
from .utils.auth import is_authorized
from .utils.job_manager import JobManager

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


class K8sClusterTelegramBot:
    def __init__(self):
        self.bot_token = os.getenv("BOT_TOKEN")
        if not self.bot_token:
            logger.error("BOT_TOKEN environment variable is required")
            sys.exit(1)

        authorized_users_str = os.getenv("AUTHORIZED_USERS", "")
        try:
            self.authorized_users = [
                int(user_id.strip())
                for user_id in authorized_users_str.split(",")
                if user_id.strip()
            ]
        except ValueError:
            logger.error(
                "Invalid AUTHORIZED_USERS format. Should be comma-separated user IDs"
            )
            sys.exit(1)

        if not self.authorized_users:
            logger.error("AUTHORIZED_USERS environment variable is required")
            sys.exit(1)

        # Initialize Kubernetes client
        self.k8s_client = KubernetesClient()

        # Initialize job manager for async exec commands
        self.job_manager = JobManager()

        # Command history storage (in-memory)
        self.command_history: Dict[int, List[Dict]] = {}

        # Bot startup time
        self.start_time = datetime.now()

        # Initialize Telegram application
        self.application = Application.builder().token(self.bot_token).build()
        self.setup_handlers()

    def setup_handlers(self):
        """Setup all command and callback handlers"""
        command_handlers = CommandHandlers(self)
        callback_handlers = CallbackHandlers(self)
        message_handlers = MessageHandlers(self)

        # Add command handlers
        command_handlers.register_handlers(self.application)

        # Add callback handlers
        callback_handlers.register_handlers(self.application)

        # Add message handlers
        message_handlers.register_handlers(self.application)

        # Store message handlers for access from callbacks
        self.message_handlers = message_handlers

    async def unauthorized_handler(self, update, context):
        """Handle messages from unauthorized users"""
        user_id = update.effective_user.id
        if not is_authorized(user_id, self.authorized_users):
            username = update.effective_user.username or "Unknown"
            logger.warning(
                f"Unauthorized access attempt from user {username} (ID: {user_id})"
            )
            await update.message.reply_text(
                "🚫 Access denied. You are not authorized to use this bot."
            )

    async def health_check(self, request):
        """Health check endpoint for Kubernetes liveness probe"""
        try:
            # Basic health check - ensure bot is responsive
            return web.Response(text="OK", status=200)
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return web.Response(text="ERROR", status=503)

    async def readiness_check(self, request):
        """Readiness check endpoint for Kubernetes readiness probe"""
        try:
            # Check if Kubernetes client is working
            self.k8s_client.v1.list_namespace(limit=1)
            return web.Response(text="READY", status=200)
        except Exception as e:
            logger.error(f"Readiness check failed: {e}")
            return web.Response(text="NOT_READY", status=503)

    async def start_health_server(self):
        """Start health check HTTP server"""
        app = web.Application()
        app.router.add_get("/health", self.health_check)
        app.router.add_get("/ready", self.readiness_check)

        port = int(os.getenv("HEALTH_CHECK_PORT", 8080))
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info(f"Health check server started on port {port}")

    async def run(self):
        """Run the bot"""
        logger.info("Starting k8s-cluster-telegram-bot...")

        # Start health check server
        await self.start_health_server()

        # Start the bot
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()

        logger.info("Bot is running. Press Ctrl+C to stop.")

        # Start job cleanup task
        cleanup_task = asyncio.create_task(self._cleanup_jobs_periodically())

        try:
            # Keep running
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("Received shutdown signal")
        finally:
            logger.info("Shutting down...")
            cleanup_task.cancel()
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()

    async def _cleanup_jobs_periodically(self):
        """Periodically clean up old completed jobs."""
        while True:
            try:
                await asyncio.sleep(3600)  # Run cleanup every hour
                self.job_manager.cleanup_old_jobs(max_age_hours=24)
                logger.info("Completed periodic job cleanup")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in job cleanup: {e}")


def main():
    bot = K8sClusterTelegramBot()
    asyncio.run(bot.run())


if __name__ == "__main__":
    main()
