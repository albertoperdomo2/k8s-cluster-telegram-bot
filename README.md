# k8s-cluster-telegram-bot 

A Telegram bot that provides interactive Kubernetes/OpenShift cluster management through chat interface. Deploy directly into your cluster and manage resources with simple commands and interactive buttons.

## ✨ Features

- **📦 Pod Management** - List pods, view logs, get details with interactive navigation
- **🚀 Deployment Control** - Scale deployments with clickable buttons (0, 1, 2, 3, 5, 10 replicas)
- **🌐 Resource Overview** - Services, nodes, namespaces with real-time status
- **📊 Cluster Dashboard** - Interactive cluster overview with quick actions
- **⚡ Async Execution** - Execute commands with notifications for long-running tasks
- **📄 Manifest Management** - Apply YAML/JSON manifests with preview and confirmation
- **📁 File Operations** - Copy files from pods with automatic type detection
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
4. Try `/deployments` for scaling operations
5. Upload YAML files with `/apply` for manifest deployment
6. Use `/exec_notif` for async command execution
7. Copy files from pods with `/cp`

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
| `/scale <deployment> <namespace> <replicas>` | Scale deployment |
| `/exec_notif <pod> <namespace> <command>` | Execute command asynchronously with notification |
| `/apply` | Apply YAML/JSON manifests (upload file after command) |
| `/cp <pod> <namespace> <file_path>` | Copy file from pod |
| `/status` | Bot and cluster status |

## 🔘 Interactive Features

- **Namespace Navigation** - Click buttons to browse pods by namespace
- **Pod Actions** - View logs and details directly from chat
- **Deployment Scaling** - Scale with clickable buttons (0, 1, 2, 3, 5, 10)
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
