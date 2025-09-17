import asyncio
import logging
import mimetypes
import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler
from ..utils.auth import is_authorized

logger = logging.getLogger(__name__)


class CommandHandlers:
    """Handles all command interactions."""

    def __init__(self, bot_instance):
        """Initialize command handlers with bot instance."""
        self.bot = bot_instance
        self.k8s_client = bot_instance.k8s_client

    def register_handlers(self, application):
        """Register all command handlers with the application."""
        logger.info("Registering command handlers")

        # Basic commands
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CommandHandler("status", self.status_command))

        # Pod management
        application.add_handler(CommandHandler("pods", self.pods_command))
        application.add_handler(CommandHandler("logs", self.logs_command))
        application.add_handler(CommandHandler("exec", self.exec_command))
        application.add_handler(CommandHandler("exec_notif", self.exec_notif_command))
        application.add_handler(CommandHandler("jobs", self.jobs_command))
        application.add_handler(CommandHandler("apply", self.apply_command))
        application.add_handler(CommandHandler("cp", self.cp_command))

        # Deployment management
        application.add_handler(CommandHandler("deployments", self.deployments_command))
        application.add_handler(CommandHandler("scale", self.scale_command))

        # Service and other resources
        application.add_handler(CommandHandler("services", self.services_command))
        application.add_handler(CommandHandler("nodes", self.nodes_command))
        application.add_handler(CommandHandler("namespaces", self.namespaces_command))

        # Cluster info
        application.add_handler(CommandHandler("cluster", self.cluster_command))

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        user_id = update.effective_user.id
        if not is_authorized(user_id, self.bot.authorized_users):
            await self.bot.unauthorized_handler(update, context)
            return

        welcome_message = """🤖 *K8s Cluster Telegram Bot*

Welcome! I can help you manage your Kubernetes cluster.

*Available Commands:*
📊 /status - Bot and cluster status
📋 /pods - List pods
📝 /logs - Get pod logs
💻 /exec - Execute commands in pods
🔔 /exec\\_notif - Execute commands with notifications
📋 /jobs - List your async jobs
📄 /apply - Apply YAML manifests to cluster
📥 /cp - Copy file from pod
🚀 /deployments - List deployments
⚖️ /scale - Scale deployments
🌐 /services - List services
🖥️ /nodes - List cluster nodes
📁 /namespaces - List namespaces
🏗️ /cluster - Cluster overview

Use /help for detailed command usage."""
        await update.message.reply_text(welcome_message, parse_mode="Markdown")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        user_id = update.effective_user.id
        if not is_authorized(user_id, self.bot.authorized_users):
            await self.bot.unauthorized_handler(update, context)
            return

        help_text = """
**📚 Command Help**

**Basic Commands:**
• `/start` - Welcome message
• `/help` - This help message
• `/status` - Show bot status

**Pod Management:**
• `/pods [namespace]` - List pods (all namespaces if none specified)
• `/logs <pod\\_name> [namespace] [lines]` - Get pod logs
• `/exec <pod\\_name> <namespace> <command>` - Execute command in pod
• `/exec\\_notif <pod\\_name> <namespace> <command>` - Execute command async with notification
• `/jobs` - List your async execution jobs
• `/apply` - Apply YAML manifests (upload file after command)
• `/cp <pod\\_name> <namespace> <file\\_path>` - Copy file from pod

**Deployment Management:**
• `/deployments [namespace]` - List deployments
• `/scale <deployment> <namespace> <replicas>` - Scale deployment

**Cluster Resources:**
• `/services [namespace]` - List services
• `/nodes` - List cluster nodes
• `/namespaces` - List all namespaces
• `/cluster` - Cluster overview

**Examples:**
• `/pods default` - Pods in default namespace
• `/logs my-pod default 100` - Last 100 lines from my-pod
• `/exec\\_notif my-pod default sleep 30` - Long-running command with notification
• `/apply` then upload deployment.yaml - Apply Kubernetes manifest
• `/cp my-pod default /var/log/app.log` - Copy log file from pod
• `/scale web-app default 3` - Scale web-app to 3 replicas
        """
        await update.message.reply_text(help_text, parse_mode="Markdown")

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command."""
        user_id = update.effective_user.id
        if not is_authorized(user_id, self.bot.authorized_users):
            await self.bot.unauthorized_handler(update, context)
            return

        try:
            uptime = datetime.now() - self.bot.start_time
            cluster_status = self.k8s_client.get_cluster_status()

            status_text = f"""
🤖 **Bot Status**
⏰ Uptime: {str(uptime).split(".")[0]}
👤 User: {update.effective_user.first_name}

🏗️ **Cluster Status**
🖥️ Nodes: {cluster_status["nodes"]["ready"]}/{cluster_status["nodes"]["total"]} ready
📦 Pods: {cluster_status["pods"]["running"]}/{cluster_status["pods"]["total"]} running
            """
            await update.message.reply_text(status_text, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Error in status command: {e}")
            await update.message.reply_text(f"❌ Error getting status: {str(e)}")

    async def pods_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /pods command."""
        user_id = update.effective_user.id
        if not is_authorized(user_id, self.bot.authorized_users):
            await self.bot.unauthorized_handler(update, context)
            return

        try:
            # Get namespace from arguments
            namespace = context.args[0] if context.args else None
            pods = self.k8s_client.get_pods(namespace)

            if not pods:
                await update.message.reply_text("No pods found.")
                return

            # Format pod list
            message = f"📦 **Pods** {'in ' + namespace if namespace else '(all namespaces)'}\n\n"

            for pod in pods[:20]:  # Limit to 20 pods to avoid message length limits
                status_emoji = "✅" if pod["status"] == "Running" else "❌"
                message += f"{status_emoji} `{pod['name']}`\n"
                message += f"   📍 {pod['namespace']} | {pod['ready']} | ↻{pod['restarts']} | {pod['age']}\n\n"

            if len(pods) > 20:
                message += f"... and {len(pods) - 20} more pods"

            await update.message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error in pods command: {e}")
            await update.message.reply_text(f"❌ Error getting pods: {str(e)}")

    async def logs_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /logs command."""
        user_id = update.effective_user.id
        if not is_authorized(user_id, self.bot.authorized_users):
            await self.bot.unauthorized_handler(update, context)
            return

        if len(context.args) < 1:
            await update.message.reply_text(
                "Usage: `/logs <pod\\_name> [namespace] [lines]`", parse_mode="Markdown"
            )
            return

        try:
            pod_name = context.args[0]
            namespace = context.args[1] if len(context.args) > 1 else "default"
            lines = int(context.args[2]) if len(context.args) > 2 else 50

            logs = self.k8s_client.get_pod_logs(pod_name, namespace, lines)

            # Truncate logs if too long for Telegram
            max_length = 4000
            if len(logs) > max_length:
                logs = logs[-max_length:] + "\n\n... (truncated)"

            message = (
                f"📝 **Logs for {pod_name}** (last {lines} lines)\n```\n{logs}\n```"
            )
            await update.message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error in logs command: {e}")
            await update.message.reply_text(f"❌ Error getting logs: {str(e)}")

    async def exec_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /exec command."""
        user_id = update.effective_user.id
        if not is_authorized(user_id, self.bot.authorized_users):
            await self.bot.unauthorized_handler(update, context)
            return

        if len(context.args) < 3:
            await update.message.reply_text(
                "Usage: `/exec <pod\\_name> <namespace> <command>`",
                parse_mode="Markdown",
            )
            return

        try:
            pod_name = context.args[0]
            namespace = context.args[1]
            command = context.args[2:]

            result = self.k8s_client.execute_command(pod_name, namespace, command)

            # Truncate output if too long
            max_length = 4000
            if len(result) > max_length:
                result = result[:max_length] + "\n\n... (truncated)"

            message = f"💻 **Command output from {pod_name}**\n```\n{result}\n```"
            await update.message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error in exec command: {e}")
            error_msg = str(e)
            if "forbidden" in error_msg.lower() or "403" in error_msg:
                await update.message.reply_text(
                    f"❌ **Permission Denied**\n\n"
                    f"The bot doesn't have sufficient permissions to execute commands in pods.\n\n"
                    f"**Required permissions:**\n"
                    f"• `pods/exec` access\n"
                    f"• Appropriate Security Context Constraints in OpenShift\n\n"
                    f"**Error details:** `{error_msg}`",
                    parse_mode="Markdown",
                )
            else:
                await update.message.reply_text(
                    f"❌ Error executing command: {error_msg}"
                )

    async def deployments_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Handle /deployments command."""
        user_id = update.effective_user.id
        if not is_authorized(user_id, self.bot.authorized_users):
            await self.bot.unauthorized_handler(update, context)
            return

        try:
            namespace = context.args[0] if context.args else None

            if namespace and namespace != "-A":
                deployments = self.k8s_client.apps_v1.list_namespaced_deployment(
                    namespace=namespace
                )
            else:
                deployments = (
                    self.k8s_client.apps_v1.list_deployment_for_all_namespaces()
                )

            if not deployments.items:
                await update.message.reply_text("No deployments found.")
                return

            message = f"🚀 **Deployments** {'in ' + namespace if namespace else '(all namespaces)'}\n\n"

            for deploy in deployments.items[:15]:
                ready = deploy.status.ready_replicas or 0
                desired = deploy.spec.replicas or 0
                available = deploy.status.available_replicas or 0

                status_emoji = "✅" if ready == desired and available > 0 else "⚠️"
                message += f"{status_emoji} `{deploy.metadata.name}`\n"
                message += (
                    f"   📍 {deploy.metadata.namespace} | {ready}/{desired} ready\n\n"
                )

            await update.message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error in deployments command: {e}")
            await update.message.reply_text(f"❌ Error getting deployments: {str(e)}")

    async def scale_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /scale command."""
        user_id = update.effective_user.id
        if not is_authorized(user_id, self.bot.authorized_users):
            await self.bot.unauthorized_handler(update, context)
            return

        if len(context.args) < 3:
            await update.message.reply_text(
                "Usage: `/scale <deployment> <namespace> <replicas>`",
                parse_mode="Markdown",
            )
            return

        try:
            deployment_name = context.args[0]
            namespace = context.args[1]
            replicas = int(context.args[2])

            success = self.k8s_client.scale_deployment(
                deployment_name, namespace, replicas
            )

            if success:
                await update.message.reply_text(
                    f"✅ Scaled deployment `{deployment_name}` to {replicas} replicas",
                    parse_mode="Markdown",
                )
            else:
                await update.message.reply_text("❌ Failed to scale deployment")

        except Exception as e:
            logger.error(f"Error in scale command: {e}")
            await update.message.reply_text(f"❌ Error scaling deployment: {str(e)}")

    async def services_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Handle /services command."""
        user_id = update.effective_user.id
        if not is_authorized(user_id, self.bot.authorized_users):
            await self.bot.unauthorized_handler(update, context)
            return

        try:
            namespace = context.args[0] if context.args else None

            if namespace and namespace != "-A":
                services = self.k8s_client.v1.list_namespaced_service(
                    namespace=namespace
                )
            else:
                services = self.k8s_client.v1.list_service_for_all_namespaces()

            if not services.items:
                await update.message.reply_text("No services found.")
                return

            message = f"🌐 **Services** {'in ' + namespace if namespace else '(all namespaces)'}\n\n"

            for svc in services.items[:15]:
                ports = []
                if svc.spec.ports:
                    ports = [f"{p.port}/{p.protocol}" for p in svc.spec.ports]

                message += f"🔗 `{svc.metadata.name}`\n"
                message += f"   📍 {svc.metadata.namespace} | {svc.spec.type}\n"
                if ports:
                    message += f"   🔌 {', '.join(ports)}\n"
                message += "\n"

            await update.message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error in services command: {e}")
            await update.message.reply_text(f"❌ Error getting services: {str(e)}")

    async def nodes_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /nodes command."""
        user_id = update.effective_user.id
        if not is_authorized(user_id, self.bot.authorized_users):
            await self.bot.unauthorized_handler(update, context)
            return

        try:
            nodes = self.k8s_client.v1.list_node()

            message = "🖥️ **Cluster Nodes**\n\n"

            for node in nodes.items:
                # Get node status
                ready = False
                for condition in node.status.conditions or []:
                    if condition.type == "Ready":
                        ready = condition.status == "True"
                        break

                status_emoji = "✅" if ready else "❌"

                # Get node info
                node_info = node.status.node_info
                message += f"{status_emoji} `{node.metadata.name}`\n"
                message += f"   🏷️ {node_info.os_image}\n"
                message += f"   🐳 {node_info.container_runtime_version}\n\n"

            await update.message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error in nodes command: {e}")
            await update.message.reply_text(f"❌ Error getting nodes: {str(e)}")

    async def namespaces_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Handle /namespaces command."""
        user_id = update.effective_user.id
        if not is_authorized(user_id, self.bot.authorized_users):
            await self.bot.unauthorized_handler(update, context)
            return

        try:
            namespaces = self.k8s_client.v1.list_namespace()

            message = "📁 **Namespaces**\n\n"

            for ns in namespaces.items:
                status_emoji = "✅" if ns.status.phase == "Active" else "❌"
                age = self.k8s_client._calculate_age(ns.metadata.creation_timestamp)

                message += f"{status_emoji} `{ns.metadata.name}` ({age})\n"

            await update.message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error in namespaces command: {e}")
            await update.message.reply_text(f"❌ Error getting namespaces: {str(e)}")

    async def cluster_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /cluster command."""
        user_id = update.effective_user.id
        if not is_authorized(user_id, self.bot.authorized_users):
            await self.bot.unauthorized_handler(update, context)
            return

        try:
            cluster_status = self.k8s_client.get_cluster_status()

            # Get additional cluster info
            nodes = self.k8s_client.v1.list_node()
            namespaces = self.k8s_client.v1.list_namespace()

            message = f"""
🏗️ **Cluster Overview**

**Nodes:**
🖥️ Total: {cluster_status["nodes"]["total"]}
✅ Ready: {cluster_status["nodes"]["ready"]}

**Pods:**
📦 Total: {cluster_status["pods"]["total"]}
🏃 Running: {cluster_status["pods"]["running"]}

**Namespaces:** {len(namespaces.items)}

**Quick Actions:**
• /pods - View all pods
• /deployments - View deployments
• /nodes - Node details
            """

            # Add interactive buttons
            keyboard = [
                [InlineKeyboardButton("📦 Pods", callback_data="list_pods_all")],
                [
                    InlineKeyboardButton(
                        "🚀 Deployments", callback_data="list_deployments_all"
                    )
                ],
                [InlineKeyboardButton("🖥️ Nodes", callback_data="list_nodes")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                message, parse_mode="Markdown", reply_markup=reply_markup
            )

        except Exception as e:
            logger.error(f"Error in cluster command: {e}")
            await update.message.reply_text(f"❌ Error getting cluster info: {str(e)}")

    async def exec_notif_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Handle /exec-notif command for async execution with notifications."""
        user_id = update.effective_user.id
        if not is_authorized(user_id, self.bot.authorized_users):
            await self.bot.unauthorized_handler(update, context)
            return

        if len(context.args) < 3:
            await update.message.reply_text(
                "Usage: `/exec\\_notif <pod\\_name> <namespace> <command>`",
                parse_mode="Markdown",
            )
            return

        try:
            pod_name = context.args[0]
            namespace = context.args[1]
            command = context.args[2:]

            # Create job
            job_id = self.bot.job_manager.create_job(
                user_id=user_id,
                chat_id=update.effective_chat.id,
                pod_name=pod_name,
                namespace=namespace,
                command=command,
            )

            # Send immediate response
            await update.message.reply_text(
                f"🔔 **Async Exec Started**\n\n"
                f"📋 **Job ID:** `{job_id}`\n"
                f"📦 **Pod:** `{pod_name}`\n"
                f"📍 **Namespace:** `{namespace}`\n"
                f"💻 **Command:** `{' '.join(command)}`\n\n"
                f"You'll be notified when the command completes. "
                f"Use `/jobs` to check status.",
                parse_mode="Markdown",
            )

            # Start async execution
            task = asyncio.create_task(
                self._execute_async_command(
                    job_id, pod_name, namespace, command, update.effective_chat.id
                )
            )
            self.bot.job_manager.start_job_task(job_id, task)

        except Exception as e:
            logger.error(f"Error in exec_notif command: {e}")
            await update.message.reply_text(f"❌ Error starting async exec: {str(e)}")

    async def _execute_async_command(
        self, job_id: str, pod_name: str, namespace: str, command: list, chat_id: int
    ):
        """Execute command asynchronously and send notification when done."""
        start_time = datetime.now()

        try:
            # Execute the command
            result = await self.k8s_client.execute_command_async(
                pod_name, namespace, command
            )
            end_time = datetime.now()
            duration = end_time - start_time

            # Truncate output if too long
            max_length = 3500  # Leave room for other text
            if len(result) > max_length:
                result = result[:max_length] + "\n\n... (output truncated)"

            # Update job status
            self.bot.job_manager.update_job_status(job_id, "completed", output=result)

            # Send completion notification
            message = (
                f"✅ **Async Exec Completed**\n\n"
                f"📋 **Job ID:** `{job_id}`\n"
                f"📦 **Pod:** `{pod_name}`\n"
                f"📍 **Namespace:** `{namespace}`\n"
                f"💻 **Command:** `{' '.join(command)}`\n"
                f"⏱️ **Duration:** {duration.total_seconds():.2f}s\n\n"
                f"**Output:**\n```\n{result}\n```"
            )

            await self.bot.application.bot.send_message(
                chat_id=chat_id, text=message, parse_mode="Markdown"
            )

        except Exception as e:
            end_time = datetime.now()
            duration = end_time - start_time
            error_msg = str(e)

            # Update job status with error
            self.bot.job_manager.update_job_status(job_id, "failed", error=error_msg)

            # Send error notification
            message = (
                f"❌ **Async Exec Failed**\n\n"
                f"📋 **Job ID:** `{job_id}`\n"
                f"📦 **Pod:** `{pod_name}`\n"
                f"📍 **Namespace:** `{namespace}`\n"
                f"💻 **Command:** `{' '.join(command)}`\n"
                f"⏱️ **Duration:** {duration.total_seconds():.2f}s\n\n"
                f"**Error:** `{error_msg}`"
            )

            await self.bot.application.bot.send_message(
                chat_id=chat_id, text=message, parse_mode="Markdown"
            )

    async def jobs_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /jobs command to list user's async execution jobs."""
        user_id = update.effective_user.id
        if not is_authorized(user_id, self.bot.authorized_users):
            await self.bot.unauthorized_handler(update, context)
            return

        try:
            user_jobs = self.bot.job_manager.get_user_jobs(user_id)

            if not user_jobs:
                await update.message.reply_text("📋 No async execution jobs found.")
                return

            message = "📋 **Your Async Execution Jobs**\n\n"

            # Sort by start time, most recent first
            user_jobs.sort(key=lambda x: x.start_time, reverse=True)

            for job in user_jobs[:10]:  # Show last 10 jobs
                status_emoji = {
                    "pending": "⏳",
                    "running": "🔄",
                    "completed": "✅",
                    "failed": "❌",
                }.get(job.status, "❓")

                duration = ""
                if job.end_time:
                    total_duration = job.end_time - job.start_time
                    duration = f" ({total_duration.total_seconds():.1f}s)"
                elif job.status == "running":
                    current_duration = datetime.now() - job.start_time
                    duration = f" ({current_duration.total_seconds():.1f}s so far)"

                message += (
                    f"{status_emoji} `{job.job_id}` - {job.status.title()}{duration}\n"
                )
                message += f"   📦 {job.pod_name} @ {job.namespace}\n"
                message += f"   💻 `{' '.join(job.command[:3])}{'...' if len(job.command) > 3 else ''}`\n\n"

            if len(user_jobs) > 10:
                message += f"... and {len(user_jobs) - 10} more jobs"

            await update.message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error in jobs command: {e}")
            await update.message.reply_text(f"❌ Error getting jobs: {str(e)}")

    async def apply_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /apply command for Kubernetes manifest application."""
        user_id = update.effective_user.id
        if not is_authorized(user_id, self.bot.authorized_users):
            await self.bot.unauthorized_handler(update, context)
            return

        message = (
            "📄 **Kubernetes Apply**\n\n"
            "Upload a YAML or JSON file containing Kubernetes manifests to apply to the cluster.\n\n"
            "**Supported formats:**\n"
            "• `.yaml` / `.yml` files\n"
            "• `.json` files\n"
            "• Multi-document YAML files\n\n"
            "**What happens next:**\n"
            "1. 📤 Upload your manifest file\n"
            "2. 🔍 Review the resources preview\n"
            "3. ✅ Confirm to apply or 🔍 run dry-run first\n\n"
            "⚠️ **Note:** You'll see a confirmation dialog before anything is applied to the cluster."
        )

        await update.message.reply_text(message, parse_mode="Markdown")

    async def cp_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /cp command for copying files from pods."""
        user_id = update.effective_user.id
        if not is_authorized(user_id, self.bot.authorized_users):
            await self.bot.unauthorized_handler(update, context)
            return

        if len(context.args) < 3:
            await update.message.reply_text(
                "Usage: `/cp <pod\\_name> <namespace> <file\\_path>`\n\n"
                "**Examples:**\n"
                "• `/cp my-pod default /var/log/app.log`\n"
                "• `/cp web-server production /etc/nginx/nginx.conf`\n"
                "• `/cp api-pod default /app/config.json`",
                parse_mode="Markdown",
            )
            return

        try:
            pod_name = context.args[0]
            namespace = context.args[1]
            file_path = context.args[2]

            # Send initial message
            status_message = await update.message.reply_text(
                f"📥 **Copying file from pod...**\n\n"
                f"📦 **Pod:** `{pod_name}`\n"
                f"📍 **Namespace:** `{namespace}`\n"
                f"📄 **File:** `{file_path}`\n\n"
                f"⏳ Please wait...",
                parse_mode="Markdown",
            )

            # Try to copy the file
            try:
                # First try the tar-based method
                result = self.k8s_client.copy_file_from_pod(
                    pod_name, namespace, file_path
                )
            except Exception as tar_error:
                logger.warning(f"Tar method failed: {tar_error}, trying cat fallback")
                try:
                    # Fallback to cat method for text files
                    result = self.k8s_client.copy_file_from_pod_simple(
                        pod_name, namespace, file_path
                    )
                except Exception as cat_error:
                    raise Exception(
                        f"Both copy methods failed. Tar: {tar_error}, Cat: {cat_error}"
                    )

            if not result.get("success"):
                raise Exception("File copy operation failed")

            # Get file information
            temp_path = result["temp_path"]
            file_name = result["file_name"]
            file_size = result["file_size"]

            # Check file size (Telegram limit is 50MB)
            max_size = 50 * 1024 * 1024  # 50MB
            if file_size > max_size:
                await status_message.edit_text(
                    f"❌ **File too large to send**\n\n"
                    f"📄 **File:** `{file_name}`\n"
                    f"📊 **Size:** {self._format_file_size(file_size)}\n"
                    f"🚫 **Limit:** 50MB\n\n"
                    f"The file is too large to send via Telegram.",
                    parse_mode="Markdown",
                )
                # Clean up temp file
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                return

            # Detect file type
            mime_type, _ = mimetypes.guess_type(file_name)

            # Determine how to send the file
            try:
                if self._is_text_file(file_name, result.get("content", b"")[:1024]):
                    # Send as text document for better preview
                    with open(temp_path, "rb") as f:
                        await update.message.reply_document(
                            document=f,
                            filename=file_name,
                            caption=f"📄 **{file_name}**\n"
                            f"📦 From: `{pod_name}` @ `{namespace}`\n"
                            f"📍 Path: `{file_path}`\n"
                            f"📊 Size: {self._format_file_size(file_size)}",
                            parse_mode="Markdown",
                        )
                elif self._is_image_file(file_name):
                    # Send as photo if it's an image
                    with open(temp_path, "rb") as f:
                        await update.message.reply_photo(
                            photo=f,
                            caption=f"🖼️ **{file_name}**\n"
                            f"📦 From: `{pod_name}` @ `{namespace}`\n"
                            f"📍 Path: `{file_path}`\n"
                            f"📊 Size: {self._format_file_size(file_size)}",
                            parse_mode="Markdown",
                        )
                else:
                    # Send as general document
                    with open(temp_path, "rb") as f:
                        await update.message.reply_document(
                            document=f,
                            filename=file_name,
                            caption=f"📁 **{file_name}**\n"
                            f"📦 From: `{pod_name}` @ `{namespace}`\n"
                            f"📍 Path: `{file_path}`\n"
                            f"📊 Size: {self._format_file_size(file_size)}",
                            parse_mode="Markdown",
                        )

                # Delete the status message since we sent the file
                await status_message.delete()

            except Exception as send_error:
                await status_message.edit_text(
                    f"❌ **Failed to send file**\n\n"
                    f"📄 **File:** `{file_name}`\n"
                    f"📊 **Size:** {self._format_file_size(file_size)}\n"
                    f"🚫 **Error:** {str(send_error)}\n\n"
                    f"The file was copied successfully but couldn't be sent via Telegram.",
                    parse_mode="Markdown",
                )

            # Clean up temporary file
            if os.path.exists(temp_path):
                os.unlink(temp_path)

        except Exception as e:
            logger.error(f"Error in cp command: {e}")
            error_msg = str(e)
            if "forbidden" in error_msg.lower() or "403" in error_msg:
                await update.message.reply_text(
                    f"❌ **Permission Denied**\n\n"
                    f"The bot doesn't have sufficient permissions to copy files from pods.\n\n"
                    f"**Required permissions:**\n"
                    f"• `pods/exec` access\n"
                    f"• Appropriate Security Context Constraints in OpenShift\n\n"
                    f"**Error details:** `{error_msg}`",
                    parse_mode="Markdown",
                )
            else:
                await update.message.reply_text(f"❌ Error copying file: {error_msg}")

    def _format_file_size(self, size_bytes: int) -> str:
        """Format file size in human readable format."""
        if size_bytes < 1024:
            return f"{size_bytes} bytes"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

    def _is_text_file(self, filename: str, content_sample: bytes) -> bool:
        """Check if file is likely a text file."""
        text_extensions = {
            ".txt",
            ".log",
            ".conf",
            ".config",
            ".yaml",
            ".yml",
            ".json",
            ".xml",
            ".html",
            ".css",
            ".js",
            ".py",
            ".java",
            ".c",
            ".cpp",
            ".h",
            ".hpp",
            ".sh",
            ".bash",
            ".zsh",
            ".fish",
            ".md",
            ".rst",
            ".sql",
            ".csv",
            ".ini",
            ".env",
            ".properties",
            ".toml",
        }

        file_ext = os.path.splitext(filename.lower())[1]
        if file_ext in text_extensions:
            return True

        # Check if content looks like text
        try:
            content_sample.decode("utf-8")
            # Check for binary indicators
            binary_chars = b"\x00\x01\x02\x03\x04\x05\x06\x0e\x0f"
            return not any(char in content_sample for char in binary_chars)
        except UnicodeDecodeError:
            return False

    def _is_image_file(self, filename: str) -> bool:
        """Check if file is an image."""
        image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp"}
        file_ext = os.path.splitext(filename.lower())[1]
        return file_ext in image_extensions
