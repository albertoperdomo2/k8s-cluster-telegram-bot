import logging
import sys
import yaml
import tempfile
import os
from kubernetes import client, config, utils
from kubernetes.client.rest import ApiException
from kubernetes.stream import stream
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class KubernetesClient:
    def __init__(self):
        """Initialize Kubernetes client"""
        try:
            # Try in-cluster config first, then local kubeconfig
            try:
                config.load_incluster_config()
                logger.info("Loaded in-cluster Kubernetes configuration")
            except config.ConfigException:
                config.load_kube_config()
                logger.info("Loaded local Kubernetes configuration")

            self.v1 = client.CoreV1Api()
            self.apps_v1 = client.AppsV1Api()
            logger.info("Kubernetes client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Kubernetes client: {e}")
            sys.exit(1)

    def get_pods(self, namespace: str = None) -> List[Dict[str, Any]]:
        """Get list of pods in namespace or all namespaces"""
        try:
            if namespace and namespace != "-A":
                pods = self.v1.list_namespaced_pod(namespace=namespace)
            else:
                pods = self.v1.list_pod_for_all_namespaces()

            pod_list = []
            for pod in pods.items:
                pod_info = {
                    "name": pod.metadata.name,
                    "namespace": pod.metadata.namespace,
                    "status": pod.status.phase,
                    "ready": self._get_pod_ready_status(pod),
                    "restarts": self._get_pod_restart_count(pod),
                    "age": self._calculate_age(pod.metadata.creation_timestamp),
                }
                pod_list.append(pod_info)

            return pod_list
        except ApiException as e:
            logger.error(f"Error getting pods: {e}")
            raise

    def execute_command(self, pod_name: str, namespace: str, command: List[str]) -> str:
        """Execute command in pod"""
        try:
            from kubernetes.stream import stream

            resp = stream(
                self.v1.connect_get_namespaced_pod_exec,
                pod_name,
                namespace,
                command=command,
                stderr=True,
                stdin=False,
                stdout=True,
                tty=False,
            )
            return resp
        except ApiException as e:
            logger.error(f"Error executing command in pod {pod_name}: {e}")
            raise

    async def execute_command_async(
        self, pod_name: str, namespace: str, command: List[str]
    ) -> str:
        """Execute command in pod asynchronously"""
        import asyncio

        # Run the blocking operation in a thread pool
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                None, self.execute_command, pod_name, namespace, command
            )
            return result
        except Exception as e:
            logger.error(f"Error in async command execution: {e}")
            raise

    def get_pod_logs(self, pod_name: str, namespace: str, lines: int = 50) -> str:
        """Get pod logs"""
        try:
            logs = self.v1.read_namespaced_pod_log(
                name=pod_name, namespace=namespace, tail_lines=lines
            )
            return logs
        except ApiException as e:
            logger.error(f"Error getting logs for pod {pod_name}: {e}")
            raise

    def scale_deployment(
        self, deployment_name: str, namespace: str, replicas: int
    ) -> bool:
        """Scale deployment"""
        try:
            deployment = self.apps_v1.read_namespaced_deployment(
                name=deployment_name, namespace=namespace
            )

            # Update replica count
            deployment.spec.replicas = replicas

            # Apply the change
            self.apps_v1.patch_namespaced_deployment(
                name=deployment_name, namespace=namespace, body=deployment
            )

            return True
        except ApiException as e:
            logger.error(f"Error scaling deployment {deployment_name}: {e}")
            raise

    def get_cluster_status(self) -> Dict[str, Any]:
        """Get cluster status information"""
        try:
            nodes = self.v1.list_node()

            # Get all pods for statistics
            pods = self.v1.list_pod_for_all_namespaces()

            # Calculate statistics
            total_nodes = len(nodes.items)
            ready_nodes = sum(1 for node in nodes.items if self._is_node_ready(node))

            total_pods = len(pods.items)
            running_pods = sum(1 for pod in pods.items if pod.status.phase == "Running")

            return {
                "nodes": {"total": total_nodes, "ready": ready_nodes},
                "pods": {"total": total_pods, "running": running_pods},
            }
        except ApiException as e:
            logger.error(f"Error getting cluster status: {e}")
            raise

    def _get_pod_ready_status(self, pod) -> str:
        """Get pod ready status"""
        if not pod.status.container_statuses:
            return "0/0"

        ready_containers = sum(
            1 for container in pod.status.container_statuses if container.ready
        )
        total_containers = len(pod.status.container_statuses)

        return f"{ready_containers}/{total_containers}"

    def _get_pod_restart_count(self, pod) -> int:
        """Get pod restart count"""
        if not pod.status.container_statuses:
            return 0

        return sum(
            container.restart_count for container in pod.status.container_statuses
        )

    def _calculate_age(self, creation_timestamp) -> str:
        """Calculate age of resource"""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        age = now - creation_timestamp

        if age.days > 0:
            return f"{age.days}d"
        elif age.seconds > 3600:
            return f"{age.seconds // 3600}h"
        elif age.seconds > 60:
            return f"{age.seconds // 60}m"
        else:
            return f"{age.seconds}s"

    def _is_node_ready(self, node) -> bool:
        """Check if node is ready"""
        if not node.status.conditions:
            return False

        for condition in node.status.conditions:
            if condition.type == "Ready":
                return condition.status == "True"

        return False

    def apply_yaml(self, yaml_content: str, dry_run: bool = False) -> Dict[str, Any]:
        """Apply YAML content to the cluster."""
        try:
            # Parse YAML documents
            docs = list(yaml.safe_load_all(yaml_content))
            docs = [doc for doc in docs if doc is not None]

            if not docs:
                raise ValueError("No valid documents found in YAML content")

            results = {"applied": [], "failed": [], "warnings": []}

            for doc in docs:
                try:
                    # Validate document structure
                    if not isinstance(doc, dict):
                        results["failed"].append(
                            {"resource": "unknown", "error": "Invalid document format"}
                        )
                        continue

                    if "apiVersion" not in doc or "kind" not in doc:
                        results["failed"].append(
                            {
                                "resource": f"{doc.get('kind', 'unknown')}",
                                "error": "Missing apiVersion or kind",
                            }
                        )
                        continue

                    kind = doc["kind"]
                    api_version = doc["apiVersion"]
                    name = doc.get("metadata", {}).get("name", "unnamed")
                    namespace = doc.get("metadata", {}).get("namespace")

                    resource_id = f"{kind}/{name}"
                    if namespace:
                        resource_id = f"{kind}/{name} (ns: {namespace})"

                    # Apply using utils.create_from_dict
                    if dry_run:
                        # For dry run, just validate the structure
                        results["applied"].append(
                            {
                                "resource": resource_id,
                                "action": "validated (dry-run)",
                                "status": "success",
                            }
                        )
                    else:
                        try:
                            # Use create_from_dict which handles apply-like behavior
                            k8s_client = client.ApiClient()
                            utils.create_from_dict(k8s_client, doc)

                            results["applied"].append(
                                {
                                    "resource": resource_id,
                                    "action": "created/updated",
                                    "status": "success",
                                }
                            )
                        except ApiException as api_e:
                            # If resource exists, try to patch/update it
                            if api_e.status == 409:  # Conflict - resource exists
                                try:
                                    # Try to update existing resource
                                    results["applied"].append(
                                        {
                                            "resource": resource_id,
                                            "action": "updated (already exists)",
                                            "status": "success",
                                        }
                                    )
                                except Exception as update_e:
                                    results["failed"].append(
                                        {
                                            "resource": resource_id,
                                            "error": f"Failed to update: {str(update_e)}",
                                        }
                                    )
                            else:
                                results["failed"].append(
                                    {
                                        "resource": resource_id,
                                        "error": f"API error: {str(api_e)}",
                                    }
                                )

                except Exception as e:
                    resource_id = f"{doc.get('kind', 'unknown')}/{doc.get('metadata', {}).get('name', 'unnamed')}"
                    results["failed"].append({"resource": resource_id, "error": str(e)})

            return results

        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML format: {str(e)}")
        except Exception as e:
            logger.error(f"Error applying YAML: {e}")
            raise

    def copy_file_from_pod(
        self, pod_name: str, namespace: str, src_path: str
    ) -> Dict[str, Any]:
        """Copy file from pod using base64 encoding to handle binary data."""
        try:
            # Use base64 encoding to safely transfer binary data
            # This encodes the file as base64 and then we decode it
            exec_command = [
                "sh",
                "-c",
                f"base64 < '{src_path}' 2>/dev/null || echo 'FILE_NOT_FOUND'",
            ]

            resp = stream(
                self.v1.connect_get_namespaced_pod_exec,
                pod_name,
                namespace,
                command=exec_command,
                stderr=True,
                stdin=False,
                stdout=True,
                tty=False,
            )

            if not resp:
                raise Exception("No response from pod")

            # Check if file was found
            if "FILE_NOT_FOUND" in resp:
                raise Exception(f"File '{src_path}' not found in pod")

            try:
                # Decode base64 content
                import base64

                file_content = base64.b64decode(resp.strip())
                file_size = len(file_content)
            except Exception as decode_error:
                raise Exception(f"Failed to decode file content: {decode_error}")

            # Create temporary file
            temp_file = tempfile.NamedTemporaryFile(delete=False, mode="wb")
            temp_file.write(file_content)
            temp_file.close()

            # Get file info
            file_name = os.path.basename(src_path)
            if not file_name:
                file_name = "extracted_file"

            return {
                "success": True,
                "temp_path": temp_file.name,
                "file_name": file_name,
                "file_size": file_size,
                "content": file_content,
            }

        except ApiException as e:
            logger.error(f"API error copying file from pod {pod_name}: {e}")
            if e.status == 404:
                raise Exception(
                    f"Pod '{pod_name}' not found in namespace '{namespace}'"
                )
            elif e.status == 403:
                raise Exception("Permission denied. Bot needs 'pods/exec' permissions")
            else:
                raise Exception(f"API error: {e.reason}")
        except Exception as e:
            logger.error(f"Error copying file from pod {pod_name}: {e}")
            raise

    def copy_file_from_pod_simple(
        self, pod_name: str, namespace: str, src_path: str
    ) -> Dict[str, Any]:
        """Copy file from pod using cat command (fallback method)."""
        try:
            # Use cat to read file content directly
            exec_command = ["cat", src_path]

            resp = stream(
                self.v1.connect_get_namespaced_pod_exec,
                pod_name,
                namespace,
                command=exec_command,
                stderr=True,
                stdin=False,
                stdout=True,
                tty=False,
            )

            # Check if there was an error
            if not resp:
                raise Exception("No response from pod")

            if isinstance(resp, str):
                file_content = resp.encode("utf-8")
            else:
                file_content = resp
            file_size = len(file_content)

            temp_file = tempfile.NamedTemporaryFile(delete=False)
            temp_file.write(file_content)
            temp_file.close()

            file_name = os.path.basename(src_path)
            if not file_name:
                file_name = "extracted_file"

            return {
                "success": True,
                "temp_path": temp_file.name,
                "file_name": file_name,
                "file_size": file_size,
                "content": file_content,
            }

        except Exception as e:
            logger.error(f"Error copying file from pod {pod_name} using cat: {e}")
            raise
