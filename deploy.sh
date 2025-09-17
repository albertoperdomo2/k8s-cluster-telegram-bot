#!/bin/bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

BOT_NAME="k8s-cluster-telegram-bot"
NAMESPACE="telegram-bot"
DEPLOYMENT_NAME="telegram-bot"
SECRET_NAME="telegram-bot-secret"
CONFIGMAP_NAME="telegram-bot-config"
IMAGE_NAME="${TELEGRAM_IMAGE:-k8s-cluster-telegram-bot}"
IMAGE_TAG="${TELEGRAM_IMAGE_VERSION:-latest}"

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${CYAN}=== $1 ===${NC}"
}

detect_platform() {
    if command -v oc &> /dev/null; then
        KUBE_CLI="oc"
        PLATFORM="openshift"
        print_status "Detected OpenShift environment"
    elif command -v kubectl &> /dev/null; then
        KUBE_CLI="kubectl"
        PLATFORM="kubernetes"
        print_status "Detected Kubernetes environment"
    else
        print_error "Neither 'kubectl' nor 'oc' command found. Please install Kubernetes/OpenShift CLI tools."
        exit 1
    fi
}

detect_container_cli() {
    if [ -n "$CONTAINER_CLI" ]; then
        # User explicitly set CONTAINER_CLI, validate it exists
        if ! command -v "$CONTAINER_CLI" &> /dev/null; then
            print_error "Specified CONTAINER_CLI '$CONTAINER_CLI' not found"
            exit 1
        fi
    elif command -v podman &> /dev/null; then
        CONTAINER_CLI="podman"
    else
        if [ "$PLATFORM" != "openshift" ]; then
            print_error "podman not found. Required for building images."
            print_error "Install podman or set CONTAINER_CLI environment variable."
            exit 1
        fi
        CONTAINER_CLI=""
    fi
}

check_cluster() {
    if ! $KUBE_CLI cluster-info &> /dev/null; then
        print_error "Cannot connect to Kubernetes cluster. Please check your cluster configuration."
        exit 1
    fi
}

check_namespace() {
    if ! $KUBE_CLI get namespace $NAMESPACE &> /dev/null; then
        print_error "Namespace '$NAMESPACE' not found. Is the bot deployed?"
        exit 1
    fi
}

get_pod_name() {
    POD_NAME=$($KUBE_CLI get pods -n $NAMESPACE -l app.kubernetes.io/name=$BOT_NAME -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    if [ -z "$POD_NAME" ]; then
        print_error "No bot pods found in namespace '$NAMESPACE'"
        exit 1
    fi
    echo $POD_NAME
}

build_image_name() {
    if [ -z "$REGISTRY" ]; then
        print_error "REGISTRY environment variable is required"
        print_error "Please set REGISTRY to your container registry (e.g., docker.io/username, quay.io/username)"
        exit 1
    fi

    if [[ "$IMAGE_NAME" == */* ]]; then
        # IMAGE_NAME already includes registry/username
        echo "$IMAGE_NAME:$IMAGE_TAG"
    else
        # IMAGE_NAME is just the repo name
        echo "$REGISTRY/$IMAGE_NAME:$IMAGE_TAG"
    fi
}

check_container_login() {
    if [ -z "$REGISTRY" ]; then
        print_error "REGISTRY environment variable is required"
        exit 1
    fi

    local registry_host=$(echo "$REGISTRY" | cut -d'/' -f1)

    if ! $CONTAINER_CLI login --get-login $registry_host >/dev/null 2>&1; then
        print_status "Please login to $registry_host:"
        $CONTAINER_CLI login $registry_host
    fi
}

collect_credentials() {
    print_status "Collecting bot credentials..."

    if [ -z "$BOT_TOKEN" ]; then
        echo -n "Enter your Telegram bot token: "
        read -s BOT_TOKEN
        echo
    fi

    if [ -z "$BOT_TOKEN" ]; then
        print_error "Bot token is required"
        exit 1
    fi

    if [ -z "$AUTHORIZED_USERS" ]; then
        echo -n "Enter authorized user IDs (comma-separated): "
        read AUTHORIZED_USERS
    fi

    if [ -z "$AUTHORIZED_USERS" ]; then
        print_error "At least one authorized user ID is required"
        exit 1
    fi

    print_success "Credentials collected"
}

check_prerequisites() {
    print_status "Checking prerequisites..."
    detect_platform
    detect_container_cli
    check_cluster
    print_success "Prerequisites check completed"
}

show_usage() {
    echo "k8s-cluster-telegram-bot deployment script"
    echo "Usage: $0 [COMMAND]"
    echo ""
    echo "Commands:"
    echo "  helm      Deploy using Helm (default)"
    echo "  build     Build the container image only"
    echo "  clean     Remove the deployment"
    echo "  logs      Show bot logs"
    echo "  status    Show deployment status"
    echo "  help      Show this help message"
    echo ""
    echo "Environment Variables:"
    echo "  TELEGRAM_IMAGE         Container image name (default: k8s-cluster-telegram-bot)"
    echo "  TELEGRAM_IMAGE_VERSION Image version (default: latest)"
    echo "  REGISTRY              Container registry URL (REQUIRED, e.g., quay.io/username)"
    echo "  CONTAINER_CLI         Container CLI to use (default: podman)"
    echo "  BOT_TOKEN             Telegram bot token"
    echo "  AUTHORIZED_USERS      Comma-separated user IDs"
    echo ""
    echo "Examples:"
    echo "  REGISTRY=quay.io/username ./deploy.sh helm    # Deploy with registry"
    echo "  REGISTRY=quay.io/username BOT_TOKEN=xxx AUTHORIZED_USERS=123 ./deploy.sh helm"
    echo "  REGISTRY=quay.io/username ./deploy.sh build   # Build image only"
    echo "  ./deploy.sh status                            # Check deployment status"
    echo ""
}

deploy_with_helm() {
    print_status "Deploying with Helm..."

    if ! command -v helm &> /dev/null; then
        print_error "Helm is not installed. Please install Helm first:"
        echo "curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash"
        exit 1
    fi

    collect_credentials
    build_image

    local full_image=$(build_image_name)
    local registry_part=${full_image%:*}
    local tag_part=${full_image##*:}

    print_status "Deploying with Helm..."
    helm upgrade --install $BOT_NAME ./helm/telegram-bot \
        --set image.repository="${registry_part}" \
        --set image.tag="${tag_part}" \
        --set secrets.botToken="${BOT_TOKEN}" \
        --set secrets.authorizedUsers="${AUTHORIZED_USERS}" \
        --wait

    print_success "Helm deployment completed successfully"

    print_header "Deployment Summary"
    helm status $BOT_NAME
    echo ""
    print_status "Pod status:"
    $KUBE_CLI get pods -n $NAMESPACE
}

build_image() {
    print_status "Building container image..."

    if [ "$PLATFORM" = "openshift" ] && [ -z "$CONTAINER_CLI" ]; then
        print_status "Using OpenShift BuildConfig for image building"

        if ! $KUBE_CLI get bc $IMAGE_NAME -n $NAMESPACE &> /dev/null; then
            cat <<EOF | $KUBE_CLI apply -f -
apiVersion: build.openshift.io/v1
kind: BuildConfig
metadata:
  name: $IMAGE_NAME
  namespace: $NAMESPACE
  labels:
    app: $BOT_NAME
spec:
  source:
    type: Binary
  strategy:
    type: Docker
    dockerStrategy:
      dockerfilePath: build/Dockerfile
  output:
    to:
      kind: ImageStreamTag
      name: $IMAGE_NAME:$IMAGE_TAG
EOF
        fi

        if ! $KUBE_CLI get is $IMAGE_NAME -n $NAMESPACE &> /dev/null; then
            $KUBE_CLI create imagestream $IMAGE_NAME -n $NAMESPACE
        fi

        $KUBE_CLI start-build $IMAGE_NAME --from-dir=. --follow -n $NAMESPACE
    else
        print_status "Building image with $CONTAINER_CLI"

        local full_image=$(build_image_name)
        $CONTAINER_CLI build --platform linux/amd64 -f build/Dockerfile -t $full_image .

        print_status "Pushing image to registry: $full_image"
        check_container_login
        $CONTAINER_CLI push $full_image
    fi

    print_success "Image build completed"
}

show_status() {
    print_header "k8s-cluster-telegram-bot Status"

    echo "Pods:"
    $KUBE_CLI get pods -n $NAMESPACE -l app.kubernetes.io/name=$BOT_NAME
    echo ""
    echo "Services:"
    $KUBE_CLI get svc -n $NAMESPACE -l app.kubernetes.io/name=$BOT_NAME
    echo ""
    echo "Deployment:"
    $KUBE_CLI get deployment -n $NAMESPACE $DEPLOYMENT_NAME
    echo ""

    print_status "Testing health endpoint..."
    if POD_NAME=$(get_pod_name 2>/dev/null); then
        if $KUBE_CLI exec -n $NAMESPACE $POD_NAME -- curl -f http://localhost:8080/health &> /dev/null; then
            print_success "Health check passed"
        else
            print_warning "Health check failed"
        fi
    else
        print_warning "No pods found"
    fi
}

show_logs() {
    print_status "Showing bot logs..."
    local pod_name=$(get_pod_name)
    $KUBE_CLI logs -f -n $NAMESPACE $pod_name
}

clean_deployment() {
    print_status "Cleaning up k8s-cluster-telegram-bot deployment..."

    if command -v helm &> /dev/null; then
        if helm list -q | grep -q "^$BOT_NAME$"; then
            print_status "Removing Helm release..."
            helm uninstall $BOT_NAME
        fi
    fi

    if $KUBE_CLI get namespace $NAMESPACE &> /dev/null; then
        print_status "Removing namespace..."
        $KUBE_CLI delete namespace $NAMESPACE
        print_success "Deployment cleaned up successfully"
    else
        print_warning "Namespace $NAMESPACE not found"
    fi
}

# Main command handling
case "${1:-help}" in
    "helm")
        check_prerequisites
        deploy_with_helm
        ;;
    "build")
        check_prerequisites
        build_image
        ;;
    "clean")
        check_prerequisites
        clean_deployment
        ;;
    "logs")
        check_prerequisites
        show_logs
        ;;
    "status")
        check_prerequisites
        show_status
        ;;
    "help"|"-h"|"--help")
        show_usage
        ;;
    *)
        print_error "Unknown command: $1"
        show_usage
        exit 1
        ;;
esac
