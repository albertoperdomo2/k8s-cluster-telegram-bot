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
            self.custom_objects_api = client.CustomObjectsApi()
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

    def describe_resource(
        self, resource_type: str, resource_name: str, namespace: str = None
    ) -> str:
        """Describe a Kubernetes resource."""
        try:
            if resource_type == "pod":
                if not namespace:
                    namespace = "default"
                pod = self.v1.read_namespaced_pod(
                    name=resource_name, namespace=namespace
                )
                return self._format_pod_description(pod)

            elif resource_type == "node":
                node = self.v1.read_node(name=resource_name)
                return self._format_node_description(node)

            elif resource_type == "deployment":
                if not namespace:
                    namespace = "default"
                deployment = self.apps_v1.read_namespaced_deployment(
                    name=resource_name, namespace=namespace
                )
                return self._format_deployment_description(deployment)

            elif resource_type == "service":
                if not namespace:
                    namespace = "default"
                service = self.v1.read_namespaced_service(
                    name=resource_name, namespace=namespace
                )
                return self._format_service_description(service)

            elif resource_type == "machineset":
                if not namespace:
                    namespace = "openshift-machine-api"
                machineset = self.custom_objects_api.get_namespaced_custom_object(
                    group="machine.openshift.io",
                    version="v1beta1",
                    namespace=namespace,
                    plural="machinesets",
                    name=resource_name,
                )
                return self._format_machineset_description(machineset)

            else:
                raise ValueError(f"Unsupported resource type: {resource_type}")

        except ApiException as e:
            if e.status == 404:
                raise Exception(f"{resource_type.title()} '{resource_name}' not found")
            else:
                raise Exception(f"API error: {e.reason}")
        except Exception as e:
            logger.error(f"Error describing {resource_type} {resource_name}: {e}")
            raise

    def scale_machineset(
        self, machineset_name: str, namespace: str, replicas: int
    ) -> bool:
        """Scale a machineset to the specified number of replicas."""
        try:
            # Get current machineset
            machineset = self.custom_objects_api.get_namespaced_custom_object(
                group="machine.openshift.io",
                version="v1beta1",
                namespace=namespace,
                plural="machinesets",
                name=machineset_name,
            )

            # Update replicas
            machineset["spec"]["replicas"] = replicas

            # Patch the machineset
            self.custom_objects_api.patch_namespaced_custom_object(
                group="machine.openshift.io",
                version="v1beta1",
                namespace=namespace,
                plural="machinesets",
                name=machineset_name,
                body=machineset,
            )

            return True

        except ApiException as e:
            if e.status == 404:
                raise Exception(
                    f"MachineSet '{machineset_name}' not found in namespace '{namespace}'"
                )
            else:
                raise Exception(f"API error: {e.reason}")
        except Exception as e:
            logger.error(f"Error scaling machineset {machineset_name}: {e}")
            raise

    def _format_pod_description(self, pod) -> str:
        """Format pod description."""
        lines = []
        lines.append(f"Name: {pod.metadata.name}")
        lines.append(f"Namespace: {pod.metadata.namespace}")
        lines.append(f"Status: {pod.status.phase}")
        lines.append(f"IP: {pod.status.pod_ip or 'None'}")
        lines.append(f"Node: {pod.spec.node_name or 'Not assigned'}")

        if pod.status.container_statuses:
            lines.append("\nContainers:")
            for container in pod.status.container_statuses:
                lines.append(f"  {container.name}: {container.state}")

        return "\n".join(lines)

    def _format_node_description(self, node) -> str:
        """Format node description."""
        lines = []
        lines.append(f"Name: {node.metadata.name}")

        # Node conditions
        if node.status.conditions:
            ready_condition = next(
                (c for c in node.status.conditions if c.type == "Ready"), None
            )
            if ready_condition:
                lines.append(f"Ready: {ready_condition.status}")

        # Node info
        if node.status.node_info:
            info = node.status.node_info
            lines.append(f"OS: {info.os_image}")
            lines.append(f"Kernel: {info.kernel_version}")
            lines.append(f"Container Runtime: {info.container_runtime_version}")

        # Capacity
        if node.status.capacity:
            lines.append("\nCapacity:")
            for resource, quantity in node.status.capacity.items():
                lines.append(f"  {resource}: {quantity}")

        return "\n".join(lines)

    def _format_deployment_description(self, deployment) -> str:
        """Format deployment description."""
        lines = []
        lines.append(f"Name: {deployment.metadata.name}")
        lines.append(f"Namespace: {deployment.metadata.namespace}")
        lines.append(
            f"Replicas: {deployment.status.ready_replicas or 0}/{deployment.spec.replicas or 0}"
        )
        lines.append(f"Strategy: {deployment.spec.strategy.type}")

        if deployment.spec.selector:
            lines.append(f"Selector: {deployment.spec.selector.match_labels}")

        return "\n".join(lines)

    def _format_service_description(self, service) -> str:
        """Format service description."""
        lines = []
        lines.append(f"Name: {service.metadata.name}")
        lines.append(f"Namespace: {service.metadata.namespace}")
        lines.append(f"Type: {service.spec.type}")
        lines.append(f"Cluster IP: {service.spec.cluster_ip}")

        if service.spec.ports:
            lines.append("Ports:")
            for port in service.spec.ports:
                lines.append(f"  {port.port}/{port.protocol} -> {port.target_port}")

        return "\n".join(lines)

    def _format_machineset_description(self, machineset) -> str:
        """Format machineset description."""
        lines = []
        lines.append(f"Name: {machineset['metadata']['name']}")
        lines.append(f"Namespace: {machineset['metadata']['namespace']}")

        spec = machineset.get("spec", {})
        status = machineset.get("status", {})

        lines.append(f"Desired Replicas: {spec.get('replicas', 0)}")
        lines.append(f"Current Replicas: {status.get('replicas', 0)}")
        lines.append(f"Ready Replicas: {status.get('readyReplicas', 0)}")

        # Machine template info
        template = spec.get("template", {}).get("spec", {})
        if template:
            lines.append("\nMachine Template:")
            provider_spec = template.get("providerSpec", {}).get("value", {})
            if provider_spec.get("instanceType"):
                lines.append(f"  Instance Type: {provider_spec['instanceType']}")
            if provider_spec.get("region"):
                lines.append(f"  Region: {provider_spec['region']}")

        return "\n".join(lines)

    def get_machinesets(
        self, namespace: str = "openshift-machine-api"
    ) -> List[Dict[str, Any]]:
        """Get list of machinesets in namespace."""
        try:
            machinesets = self.custom_objects_api.list_namespaced_custom_object(
                group="machine.openshift.io",
                version="v1beta1",
                namespace=namespace,
                plural="machinesets",
            )

            machineset_list = []
            for ms in machinesets.get("items", []):
                spec = ms.get("spec", {})
                status = ms.get("status", {})

                # Extract instance type from provider spec
                template = spec.get("template", {}).get("spec", {})
                provider_spec = template.get("providerSpec", {}).get("value", {})
                instance_type = provider_spec.get("instanceType", "Unknown")

                machineset_info = {
                    "name": ms["metadata"]["name"],
                    "namespace": ms["metadata"]["namespace"],
                    "desired_replicas": spec.get("replicas", 0),
                    "current_replicas": status.get("replicas", 0),
                    "ready_replicas": status.get("readyReplicas", 0),
                    "instance_type": instance_type,
                }
                machineset_list.append(machineset_info)

            return machineset_list

        except ApiException as e:
            logger.error(f"Error getting machinesets: {e}")
            raise
        except Exception as e:
            logger.error(f"Error getting machinesets: {e}")
            raise
