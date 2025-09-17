import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from ..utils.auth import is_authorized

logger = logging.getLogger(__name__)


class CallbackHandlers:
    """Handles all callback interactions."""

    def __init__(self, bot_instance):
        """Initialize callback handlers with bot instance."""
        self.bot = bot_instance
        self.k8s_client = bot_instance.k8s_client

    def register_handlers(self, application):
        """Register all callback handlers with the application."""
        logger.info("Registering callback handlers")
        application.add_handler(CallbackQueryHandler(self.handle_callback))

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle all callback query interactions."""
        query = update.callback_query
        user_id = update.effective_user.id

        if not is_authorized(user_id, self.bot.authorized_users):
            await query.answer(
                "🚫 Access denied. You are not authorized to use this bot."
            )
            return

        await query.answer()

        # Route callback to appropriate handler
        callback_data = query.data

        if callback_data == "list_pods_all":
            await self.list_pods_callback(update, context)
        elif callback_data == "list_deployments_all":
            await self.list_deployments_callback(update, context)
        elif callback_data == "list_nodes":
            await self.list_nodes_callback(update, context)
        elif callback_data.startswith("pod_details_"):
            await self.pod_details_callback(update, context, callback_data)
        elif callback_data.startswith("deployment_details_"):
            await self.deployment_details_callback(update, context, callback_data)
        elif callback_data.startswith("pod_logs_"):
            await self.pod_logs_callback(update, context, callback_data)
        elif callback_data.startswith("namespace_pods_"):
            await self.namespace_pods_callback(update, context, callback_data)
        elif callback_data.startswith("scale_deployment_"):
            await self.scale_deployment_callback(update, context, callback_data)
        elif callback_data.startswith("scale_to_"):
            await self.scale_to_callback(update, context, callback_data)
        elif callback_data.startswith("apply_"):
            await self.apply_callback(update, context, callback_data)
        else:
            await query.edit_message_text("❌ Unknown action")

    async def list_pods_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Handle listing all pods via callback."""
        query = update.callback_query

        try:
            pods = self.k8s_client.get_pods()

            if not pods:
                await query.edit_message_text("No pods found.")
                return

            # Group pods by namespace for better organization
            namespaces = {}
            for pod in pods:
                if pod["namespace"] not in namespaces:
                    namespaces[pod["namespace"]] = []
                namespaces[pod["namespace"]].append(pod)

            message = "📦 **All Pods by Namespace**\n\n"

            # Create buttons for each namespace
            keyboard = []
            for ns, ns_pods in list(namespaces.items())[
                :10
            ]:  # Limit to avoid button overflow
                running_pods = len([p for p in ns_pods if p["status"] == "Running"])
                total_pods = len(ns_pods)

                message += f"📁 **{ns}**: {running_pods}/{total_pods} running\n"

                # Ensure callback data doesn't exceed Telegram's 64-byte limit
                callback_data = f"namespace_pods_{ns}"
                if len(callback_data.encode("utf-8")) > 64:
                    # Truncate namespace to fit within limit
                    max_ns_length = 64 - len("namespace_pods_")
                    truncated_ns = ns[:max_ns_length]
                    callback_data = f"namespace_pods_{truncated_ns}"
                    logger.warning(
                        f"Truncated namespace '{ns}' to '{truncated_ns}' for callback data"
                    )

                keyboard.append(
                    [
                        InlineKeyboardButton(
                            f"📦 {ns} ({total_pods})",
                            callback_data=callback_data,
                        )
                    ]
                )

            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                message, parse_mode="Markdown", reply_markup=reply_markup
            )

        except Exception as e:
            logger.error(f"Error in list_pods_callback: {e}")
            await query.edit_message_text(f"❌ Error getting pods: {str(e)}")

    async def namespace_pods_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: str
    ):
        """Handle listing pods in a specific namespace."""
        query = update.callback_query

        # Extract namespace from callback data, handle potential parsing issues
        try:
            namespace = callback_data.replace("namespace_pods_", "")
            if not namespace:
                raise ValueError("Empty namespace")
        except Exception as e:
            logger.error(
                f"Error parsing namespace from callback_data '{callback_data}': {e}"
            )
            await query.edit_message_text("❌ Invalid namespace data")
            return

        try:
            pods = self.k8s_client.get_pods(namespace)

            if not pods:
                await query.edit_message_text(
                    f"No pods found in namespace '{namespace}'."
                )
                return

            message = f"📦 **Pods in {namespace}**\n\n"

            keyboard = []
            for pod in pods[:15]:  # Limit to avoid message length limits
                status_emoji = "✅" if pod["status"] == "Running" else "❌"
                message += f"{status_emoji} `{pod['name']}`\n"
                message += f"   {pod['ready']} | ↻{pod['restarts']} | {pod['age']}\n\n"

                # Add action buttons for each pod
                # Ensure callback data doesn't exceed Telegram's 64-byte limit
                logs_callback = f"pod_logs_{namespace}_{pod['name']}"
                details_callback = f"pod_details_{namespace}_{pod['name']}"

                # Truncate if needed (simplified approach - truncate pod name)
                if len(logs_callback.encode("utf-8")) > 64:
                    max_pod_name = 64 - len(f"pod_logs_{namespace}_")
                    truncated_pod = pod["name"][:max_pod_name]
                    logs_callback = f"pod_logs_{namespace}_{truncated_pod}"

                if len(details_callback.encode("utf-8")) > 64:
                    max_pod_name = 64 - len(f"pod_details_{namespace}_")
                    truncated_pod = pod["name"][:max_pod_name]
                    details_callback = f"pod_details_{namespace}_{truncated_pod}"

                keyboard.append(
                    [
                        InlineKeyboardButton(
                            "📝 Logs",
                            callback_data=logs_callback,
                        ),
                        InlineKeyboardButton(
                            "ℹ️ Details",
                            callback_data=details_callback,
                        ),
                    ]
                )

            if len(pods) > 15:
                message += f"... and {len(pods) - 15} more pods"

            reply_markup = InlineKeyboardMarkup(keyboard[:10])  # Limit buttons
            await query.edit_message_text(
                message, parse_mode="Markdown", reply_markup=reply_markup
            )

        except Exception as e:
            logger.error(f"Error in namespace_pods_callback: {e}")
            await query.edit_message_text(f"❌ Error getting pods: {str(e)}")

    async def pod_logs_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: str
    ):
        """Handle getting pod logs via callback."""
        query = update.callback_query
        _, _, namespace, pod_name = callback_data.split("_", 3)

        try:
            logs = self.k8s_client.get_pod_logs(pod_name, namespace, 50)

            # Truncate logs if too long for Telegram
            max_length = 4000
            if len(logs) > max_length:
                logs = logs[-max_length:] + "\n\n... (truncated)"

            message = f"📝 **Logs for {pod_name}** (last 50 lines)\n```\n{logs}\n```"

            # Add back button
            keyboard = [
                [
                    InlineKeyboardButton(
                        "🔙 Back to Pods", callback_data=f"namespace_pods_{namespace}"
                    )
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                message, parse_mode="Markdown", reply_markup=reply_markup
            )

        except Exception as e:
            logger.error(f"Error in pod_logs_callback: {e}")
            await query.edit_message_text(f"❌ Error getting logs: {str(e)}")

    async def pod_details_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: str
    ):
        """Handle getting detailed pod information."""
        query = update.callback_query
        _, _, namespace, pod_name = callback_data.split("_", 3)

        try:
            # Get detailed pod info
            pod = self.k8s_client.v1.read_namespaced_pod(
                name=pod_name, namespace=namespace
            )

            # Format pod details
            message = f"ℹ️ **Pod Details: {pod_name}**\n\n"
            message += f"📍 **Namespace:** {namespace}\n"
            message += f"🏷️ **Status:** {pod.status.phase}\n"

            if pod.status.pod_ip:
                message += f"🌐 **IP:** {pod.status.pod_ip}\n"

            if pod.spec.node_name:
                message += f"🖥️ **Node:** {pod.spec.node_name}\n"

            # Container info
            if pod.spec.containers:
                message += f"\n📦 **Containers:**\n"
                for container in pod.spec.containers:
                    message += f"• `{container.name}` - {container.image}\n"

            # Creation time
            age = self.k8s_client._calculate_age(pod.metadata.creation_timestamp)
            message += f"\n⏰ **Age:** {age}\n"

            # Add action buttons
            keyboard = [
                [
                    InlineKeyboardButton(
                        "📝 View Logs", callback_data=f"pod_logs_{namespace}_{pod_name}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🔙 Back to Pods", callback_data=f"namespace_pods_{namespace}"
                    )
                ],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                message, parse_mode="Markdown", reply_markup=reply_markup
            )

        except Exception as e:
            logger.error(f"Error in pod_details_callback: {e}")
            await query.edit_message_text(f"❌ Error getting pod details: {str(e)}")

    async def list_deployments_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Handle listing all deployments via callback."""
        query = update.callback_query

        try:
            deployments = self.k8s_client.apps_v1.list_deployment_for_all_namespaces()

            if not deployments.items:
                await query.edit_message_text("No deployments found.")
                return

            message = "🚀 **All Deployments**\n\n"

            keyboard = []
            for deploy in deployments.items[:10]:  # Limit to avoid button overflow
                ready = deploy.status.ready_replicas or 0
                desired = deploy.spec.replicas or 0

                status_emoji = "✅" if ready == desired else "⚠️"
                message += f"{status_emoji} `{deploy.metadata.name}`\n"
                message += (
                    f"   📍 {deploy.metadata.namespace} | {ready}/{desired} ready\n\n"
                )

                keyboard.append(
                    [
                        InlineKeyboardButton(
                            f"⚖️ Scale",
                            callback_data=f"scale_deployment_{deploy.metadata.namespace}_{deploy.metadata.name}",
                        ),
                        InlineKeyboardButton(
                            f"ℹ️ Details",
                            callback_data=f"deployment_details_{deploy.metadata.namespace}_{deploy.metadata.name}",
                        ),
                    ]
                )

            if len(deployments.items) > 10:
                message += f"... and {len(deployments.items) - 10} more deployments"

            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                message, parse_mode="Markdown", reply_markup=reply_markup
            )

        except Exception as e:
            logger.error(f"Error in list_deployments_callback: {e}")
            await query.edit_message_text(f"❌ Error getting deployments: {str(e)}")

    async def deployment_details_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: str
    ):
        """Handle getting detailed deployment information."""
        query = update.callback_query
        _, _, namespace, deployment_name = callback_data.split("_", 3)

        try:
            deploy = self.k8s_client.apps_v1.read_namespaced_deployment(
                name=deployment_name, namespace=namespace
            )

            ready = deploy.status.ready_replicas or 0
            desired = deploy.spec.replicas or 0
            available = deploy.status.available_replicas or 0

            message = f"🚀 **Deployment Details: {deployment_name}**\n\n"
            message += f"📍 **Namespace:** {namespace}\n"
            message += (
                f"📊 **Replicas:** {ready}/{desired} ready, {available} available\n"
            )

            # Image info
            if deploy.spec.template.spec.containers:
                message += f"\n📦 **Containers:**\n"
                for container in deploy.spec.template.spec.containers:
                    message += f"• `{container.name}` - {container.image}\n"

            # Creation time
            age = self.k8s_client._calculate_age(deploy.metadata.creation_timestamp)
            message += f"\n⏰ **Age:** {age}\n"

            # Add action buttons
            keyboard = [
                [
                    InlineKeyboardButton(
                        "⚖️ Scale",
                        callback_data=f"scale_deployment_{namespace}_{deployment_name}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🔙 Back to Deployments", callback_data="list_deployments_all"
                    )
                ],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                message, parse_mode="Markdown", reply_markup=reply_markup
            )

        except Exception as e:
            logger.error(f"Error in deployment_details_callback: {e}")
            await query.edit_message_text(
                f"❌ Error getting deployment details: {str(e)}"
            )

    async def scale_deployment_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: str
    ):
        """Handle scaling deployment via callback."""
        query = update.callback_query
        _, _, namespace, deployment_name = callback_data.split("_", 3)

        # For now, provide scaling options
        message = f"⚖️ **Scale Deployment: {deployment_name}**\n\n"
        message += f"Choose number of replicas:\n"

        keyboard = [
            [
                InlineKeyboardButton(
                    "0", callback_data=f"scale_to_{namespace}_{deployment_name}_0"
                ),
                InlineKeyboardButton(
                    "1", callback_data=f"scale_to_{namespace}_{deployment_name}_1"
                ),
                InlineKeyboardButton(
                    "2", callback_data=f"scale_to_{namespace}_{deployment_name}_2"
                ),
            ],
            [
                InlineKeyboardButton(
                    "3", callback_data=f"scale_to_{namespace}_{deployment_name}_3"
                ),
                InlineKeyboardButton(
                    "5", callback_data=f"scale_to_{namespace}_{deployment_name}_5"
                ),
                InlineKeyboardButton(
                    "10", callback_data=f"scale_to_{namespace}_{deployment_name}_10"
                ),
            ],
            [
                InlineKeyboardButton(
                    "🔙 Back",
                    callback_data=f"deployment_details_{namespace}_{deployment_name}",
                )
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            message, parse_mode="Markdown", reply_markup=reply_markup
        )

    async def list_nodes_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Handle listing cluster nodes via callback."""
        query = update.callback_query

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
                message += f"   🐳 {node_info.container_runtime_version}\n"
                message += f"   ⚙️ {node_info.kubelet_version}\n\n"

            # Add back button
            keyboard = [
                [
                    InlineKeyboardButton(
                        "🔙 Back to Cluster", callback_data="cluster_overview"
                    )
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                message, parse_mode="Markdown", reply_markup=reply_markup
            )

        except Exception as e:
            logger.error(f"Error in list_nodes_callback: {e}")
            await query.edit_message_text(f"❌ Error getting nodes: {str(e)}")

    async def scale_to_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: str
    ):
        """Handle scaling deployment to specific replica count."""
        query = update.callback_query
        _, _, namespace, deployment_name, replicas = callback_data.split("_", 4)

        try:
            success = self.k8s_client.scale_deployment(
                deployment_name, namespace, int(replicas)
            )

            if success:
                message = (
                    f"✅ Successfully scaled `{deployment_name}` to {replicas} replicas"
                )
                keyboard = [
                    [
                        InlineKeyboardButton(
                            "🔙 Back to Deployment",
                            callback_data=f"deployment_details_{namespace}_{deployment_name}",
                        )
                    ]
                ]
            else:
                message = f"❌ Failed to scale `{deployment_name}`"
                keyboard = [
                    [
                        InlineKeyboardButton(
                            "🔙 Back",
                            callback_data=f"scale_deployment_{namespace}_{deployment_name}",
                        )
                    ]
                ]

            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                message, parse_mode="Markdown", reply_markup=reply_markup
            )

        except Exception as e:
            logger.error(f"Error in scale_to_callback: {e}")
            await query.edit_message_text(f"❌ Error scaling deployment: {str(e)}")

    async def apply_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: str
    ):
        """Handle apply confirmation callbacks."""
        query = update.callback_query
        user_id = update.effective_user.id

        if not is_authorized(user_id, self.bot.authorized_users):
            await query.answer(
                "🚫 Access denied. You are not authorized to use this bot."
            )
            return

        try:
            # Parse callback data: apply_action_applyid
            parts = callback_data.split("_", 2)
            if len(parts) < 3:
                await query.edit_message_text("❌ Invalid callback data")
                return

            action = parts[1]  # confirm, dryrun, or cancel
            apply_id = parts[2]

            # Get pending apply operation
            apply_data = self.bot.message_handlers.get_pending_apply(apply_id)
            if not apply_data:
                await query.edit_message_text("❌ Apply operation not found or expired")
                return

            if action == "cancel":
                # Cancel the operation
                self.bot.message_handlers.remove_pending_apply(apply_id)
                await query.edit_message_text("❌ Apply operation cancelled")
                return

            # Get YAML content and file info
            yaml_content = apply_data["content"]
            file_name = apply_data["file_name"]
            resources = apply_data["resources"]

            if action == "dryrun":
                # Perform dry run
                await query.edit_message_text("🔍 **Running dry-run validation...**")

                try:
                    result = self.k8s_client.apply_yaml(yaml_content, dry_run=True)

                    message = f"🔍 **Dry Run Results for {file_name}**\n\n"

                    if result["applied"]:
                        message += "**✅ Resources validated:**\n"
                        for item in result["applied"]:
                            message += f"• {item['resource']}\n"
                        message += "\n"

                    if result["failed"]:
                        message += "**❌ Validation errors:**\n"
                        for item in result["failed"]:
                            message += f"• {item['resource']}: {item['error']}\n"
                        message += "\n"

                    message += "The resources above would be applied to the cluster."

                    # Add buttons to proceed or cancel
                    keyboard = [
                        [
                            InlineKeyboardButton(
                                "✅ Apply Now",
                                callback_data=f"apply_confirm_{apply_id}",
                            ),
                            InlineKeyboardButton(
                                "❌ Cancel", callback_data=f"apply_cancel_{apply_id}"
                            ),
                        ]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)

                    await query.edit_message_text(
                        message, parse_mode="Markdown", reply_markup=reply_markup
                    )

                except Exception as e:
                    await query.edit_message_text(f"❌ Dry run failed: {str(e)}")

            elif action == "confirm":
                # Actually apply the resources
                await query.edit_message_text("⚙️ **Applying resources to cluster...**")

                try:
                    result = self.k8s_client.apply_yaml(yaml_content, dry_run=False)

                    # Remove from pending applies
                    self.bot.message_handlers.remove_pending_apply(apply_id)

                    message = f"📄 **Apply Results for {file_name}**\n\n"

                    if result["applied"]:
                        message += "**✅ Successfully applied:**\n"
                        for item in result["applied"]:
                            action_text = item.get("action", "applied")
                            message += f"• {item['resource']} - {action_text}\n"
                        message += "\n"

                    if result["failed"]:
                        message += "**❌ Failed to apply:**\n"
                        for item in result["failed"]:
                            message += f"• {item['resource']}: {item['error']}\n"
                        message += "\n"

                    if result["warnings"]:
                        message += "**⚠️ Warnings:**\n"
                        for warning in result["warnings"]:
                            message += f"• {warning}\n"
                        message += "\n"

                    success_count = len(result["applied"])
                    failure_count = len(result["failed"])

                    if failure_count == 0:
                        message += (
                            f"🎉 All {success_count} resources applied successfully!"
                        )
                    else:
                        message += (
                            f"⚠️ {success_count} succeeded, {failure_count} failed"
                        )

                    await query.edit_message_text(message, parse_mode="Markdown")

                except Exception as e:
                    logger.error(f"Error applying YAML: {e}")
                    await query.edit_message_text(f"❌ Apply failed: {str(e)}")

        except Exception as e:
            logger.error(f"Error in apply_callback: {e}")
            await query.edit_message_text(
                f"❌ Error processing apply request: {str(e)}"
            )
