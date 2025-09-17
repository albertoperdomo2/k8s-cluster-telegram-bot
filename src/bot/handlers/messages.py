import logging
import tempfile
import yaml
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, MessageHandler, filters
from ..utils.auth import is_authorized

logger = logging.getLogger(__name__)


class MessageHandlers:
    """Handles all message interactions."""

    def __init__(self, bot_instance):
        """Initialize message handlers with bot instance."""
        self.bot = bot_instance
        self.k8s_client = bot_instance.k8s_client
        # Store pending apply operations per user
        self.pending_applies = {}

    def register_handlers(self, application):
        """Register all message handlers with the application."""
        logger.info("Registering message handlers")

        # Document handler for YAML files
        yaml_filter = (
            filters.Document.FileExtension("yaml")
            | filters.Document.FileExtension("yml")
            | filters.Document.FileExtension("json")
        )
        application.add_handler(MessageHandler(yaml_filter, self.handle_yaml_upload))

    async def handle_yaml_upload(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Handle YAML/JSON file uploads for kubectl apply."""
        user_id = update.effective_user.id
        if not is_authorized(user_id, self.bot.authorized_users):
            await self.bot.unauthorized_handler(update, context)
            return

        try:
            document = update.message.document
            file_name = document.file_name
            file_size = document.file_size

            # Check file size (limit to 1MB)
            if file_size > 1024 * 1024:
                await update.message.reply_text(
                    "❌ File too large. Please upload files smaller than 1MB."
                )
                return

            # Check if this looks like a Kubernetes manifest
            if not (file_name.endswith((".yaml", ".yml", ".json"))):
                await update.message.reply_text(
                    "ℹ️ This doesn't appear to be a Kubernetes manifest file. "
                    "Use `/apply` command first if you want to apply this file to the cluster."
                )
                return

            # Download file
            file = await context.bot.get_file(document.file_id)

            # Create temporary file
            with tempfile.NamedTemporaryFile(
                mode="w+b", delete=False, suffix=f"_{file_name}"
            ) as temp_file:
                await file.download_to_drive(temp_file.name)
                temp_file_path = temp_file.name

            try:
                # Read and parse the file
                with open(temp_file_path, "r", encoding="utf-8") as f:
                    content = f.read()

                # Parse YAML/JSON
                if file_name.endswith(".json"):
                    import json

                    parsed_docs = [json.loads(content)]
                else:
                    parsed_docs = list(yaml.safe_load_all(content))
                    # Filter out None documents
                    parsed_docs = [doc for doc in parsed_docs if doc is not None]

                if not parsed_docs:
                    await update.message.reply_text(
                        "❌ No valid Kubernetes resources found in file."
                    )
                    return

                # Validate documents
                resources_info = []
                for i, doc in enumerate(parsed_docs):
                    if not isinstance(doc, dict):
                        await update.message.reply_text(
                            f"❌ Invalid document format at position {i + 1}"
                        )
                        return

                    if "apiVersion" not in doc or "kind" not in doc:
                        await update.message.reply_text(
                            f"❌ Missing apiVersion or kind in document {i + 1}"
                        )
                        return

                    name = doc.get("metadata", {}).get("name", "unnamed")
                    namespace = doc.get("metadata", {}).get("namespace", "default")
                    resources_info.append(
                        {
                            "kind": doc["kind"],
                            "name": name,
                            "namespace": namespace,
                            "apiVersion": doc["apiVersion"],
                        }
                    )

                # Store for confirmation
                apply_id = f"{user_id}_{update.message.message_id}"
                self.pending_applies[apply_id] = {
                    "content": content,
                    "file_name": file_name,
                    "resources": resources_info,
                    "user_id": user_id,
                    "chat_id": update.effective_chat.id,
                }

                # Create preview message
                preview_message = f"📋 **Kubernetes Manifest Preview**\n\n"
                preview_message += f"📄 **File:** `{file_name}`\n"
                preview_message += (
                    f"📊 **Resources:** {len(resources_info)} item(s)\n\n"
                )

                for i, resource in enumerate(
                    resources_info[:10]
                ):  # Show max 10 resources
                    preview_message += (
                        f"**{i + 1}.** {resource['kind']}/{resource['name']}\n"
                    )
                    preview_message += f"   📍 Namespace: `{resource['namespace']}`\n"
                    preview_message += f"   🔗 API: `{resource['apiVersion']}`\n\n"

                if len(resources_info) > 10:
                    preview_message += (
                        f"... and {len(resources_info) - 10} more resources\n\n"
                    )

                preview_message += (
                    "⚠️ **Confirm to apply these resources to the cluster**"
                )

                # Create confirmation buttons
                keyboard = [
                    [
                        InlineKeyboardButton(
                            "✅ Apply", callback_data=f"apply_confirm_{apply_id}"
                        ),
                        InlineKeyboardButton(
                            "🔍 Dry Run", callback_data=f"apply_dryrun_{apply_id}"
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            "❌ Cancel", callback_data=f"apply_cancel_{apply_id}"
                        )
                    ],
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await update.message.reply_text(
                    preview_message, parse_mode="Markdown", reply_markup=reply_markup
                )

            finally:
                # Clean up temporary file
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)

        except yaml.YAMLError as e:
            await update.message.reply_text(f"❌ Invalid YAML format: {str(e)}")
        except Exception as e:
            logger.error(f"Error handling YAML upload: {e}")
            await update.message.reply_text(f"❌ Error processing file: {str(e)}")

    def get_pending_apply(self, apply_id: str):
        """Get pending apply operation."""
        return self.pending_applies.get(apply_id)

    def remove_pending_apply(self, apply_id: str):
        """Remove pending apply operation."""
        if apply_id in self.pending_applies:
            del self.pending_applies[apply_id]
