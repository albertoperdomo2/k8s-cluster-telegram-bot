# k8s-cluster-telegram-bot 

A Telegram bot that provides interactive Kubernetes/OpenShift cluster management through chat interface. Deploy directly into your cluster and manage resources with simple commands and interactive buttons.

## ✨ Features

- **📦 Pod Management** - List pods, view logs, get details with interactive navigation
- **🚀 Resource Scaling** - Scale deployments and machinesets with unified command interface
- **🌐 Resource Overview** - Services, nodes, namespaces with real-time status
- **📊 Cluster Dashboard** - Interactive cluster overview with quick actions
- **⚡ Async Execution** - Execute commands with notifications for long-running tasks
- **📄 Manifest Management** - Apply YAML/JSON manifests with preview and confirmation
- **📁 File Operations** - Copy files from pods with automatic type detection
- **🔧 Machine Management** - List and scale machinesets up/down with safety confirmations
- **📋 Resource Description** - Detailed information about pods, nodes, deployments, and machinesets
- **🔒 Secure Access** - User authentication and RBAC integration
- **🏥 Health Monitoring** - Built-in health checks and monitoring endpoints

## 🚀 Quick Install

### Prerequisites

- OpenShift/Kubernetes cluster with admin access
- Telegram bot token from [@BotFather](https://t.me/BotFather)
- Your Telegram user ID from [@userinfobot](https://t.me/userinfobot)

### Step 1: Create Telegram Bot

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Use `/newbot` command to create a new bot
3. Save the bot token (format: `123456789:ABCdefGhIjKlMnOpQrStUvWxYz`)

### Step 2: Get Your User ID

1. Message [@userinfobot](https://t.me/userinfobot) on Telegram
2. Note your user ID (numeric value)

### Step 3: Deploy to OpenShift

```bash
# Clone the repository
git clone https://github.com/albertoperdomo2/k8s-cluster-telegram-bot.git
cd k8s-cluster-telegram-bot

# Build and push image (replace with your registry)
REGISTRY=quay.io/your-username ./deploy.sh build

# Deploy with Helm
helm install telegram-bot ./helm/telegram-bot \
  --set image.repository="quay.io/your-username/k8s-cluster-telegram-bot" \
  --set image.tag="latest" \
  --set secrets.botToken="YOUR_BOT_TOKEN" \
  --set secrets.authorizedUsers="YOUR_USER_ID"

# Check deployment
oc get pods -n telegram-bot
```

### Step 4: Start Using

1. Find your bot on Telegram and send `/start`
2. Try `/cluster` for interactive cluster overview
3. Use `/pods` to explore pod management
4. Try `/deployments` to list deployments
5. Use `/scale` to scale deployments and machinesets
6. Upload YAML files with `/apply` for manifest deployment
7. Use `/exec_notif` for async command execution
8. Copy files from pods with `/cp`
9. List machinesets with `/machinesets`
10. Get detailed resource information with `/describe`

## 📱 Available Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome and bot overview |
| `/help` | Detailed command help |
| `/cluster` | Interactive cluster dashboard |
| `/pods [namespace]` | List pods with interactive buttons |
| `/deployments [namespace]` | List and scale deployments |
| `/services [namespace]` | List services |
| `/nodes` | Show cluster nodes |
| `/namespaces` | List all namespaces |
| `/logs <pod> [namespace] [lines]` | Get pod logs |
| `/scale <resource_type> <resource_name> <namespace> <replicas>` | Scale deployments and machinesets |
| `/exec_notif <pod> <namespace> <command>` | Execute command asynchronously with notification |
| `/apply` | Apply YAML/JSON manifests (upload file after command) |
| `/cp <pod> <namespace> <file_path>` | Copy file from pod |
| `/describe <type> <name> [namespace]` | Describe Kubernetes resources |
| `/machinesets [namespace]` | List machinesets |
| `/status` | Bot and cluster status |

## 🎯 Scaling Examples

The `/scale` command provides unified scaling for multiple resource types:

### Deployment Scaling
```bash
# Scale a deployment to 3 replicas
/scale deployment web-app default 3

# Scale down to 1 replica
/scale deployment api-service production 1
```

### Machineset Scaling
```bash
# Scale up worker nodes
/scale machineset worker-nodes openshift-machine-api 5

# Scale down (requires confirmation for 0)
/scale machineset test-nodes openshift-machine-api 0
```

**⚠️ Note**: Scaling machinesets to 0 requires typing `CONFIRM` to proceed, as this terminates cluster nodes.

## 🔘 Interactive Features

- **Namespace Navigation** - Click buttons to browse pods by namespace
- **Pod Actions** - View logs and details directly from chat
- **Resource Scaling** - Scale deployments and machinesets with command interface and safety confirmations
- **Manifest Preview** - Review YAML/JSON before applying with confirmation
- **Async Notifications** - Get notified when long-running commands complete
- **File Type Detection** - Automatic handling of text, images, and binary files
- **Quick Navigation** - Back buttons to move between views

## 🔧 Configuration

### Update Bot Token or Users

```bash
# Update via Helm
helm upgrade telegram-bot ./helm/telegram-bot \
  --set secrets.botToken="NEW_TOKEN" \
  --set secrets.authorizedUsers="USER_ID_1,USER_ID_2"
```

### Management Commands

```bash
# Check status
oc get pods -n telegram-bot
oc logs -f deployment/telegram-bot -n telegram-bot

# Restart deployment
oc rollout restart deployment/telegram-bot -n telegram-bot

# Uninstall
helm uninstall telegram-bot
```

## 🐛 Troubleshooting

### Common Issues

**Bot not responding:**
```bash
oc logs deployment/telegram-bot -n telegram-bot
oc describe pod -l app=telegram-bot -n telegram-bot
```

**Permission errors:**
```bash
oc describe clusterrolebinding telegram-bot
oc auth can-i get pods --as=system:serviceaccount:telegram-bot:telegram-bot
```

**Image pull errors:**
```bash
# Rebuild and redeploy
REGISTRY=quay.io/your-username ./deploy.sh build
oc rollout restart deployment/telegram-bot -n telegram-bot
```

## 🔒 Security

The bot uses RBAC with minimal required permissions:
- **Pods**: get, list, watch, logs
- **Deployments**: get, list, watch, patch, scale
- **Services**: get, list, watch
- **Nodes/Namespaces**: get, list, watch
- **Machinesets**: get, list, watch, patch, update (OpenShift)

**Note**: `/exec` command requires additional OpenShift security permissions and may show permission errors in restricted environments.

## 🛠️ Development

```bash
# Local development
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Set environment variables
export BOT_TOKEN="your-token"
export AUTHORIZED_USERS="your-user-id"

# Run locally
python -m src.bot.main
```

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details.

---

**⚠️ Security Notice**: This bot has cluster-wide access. Only authorize trusted users and use at your own risk.
