#!/bin/bash

# VitaeX Agentic AI Platform - Deployment Script
# Supports both local development and production Kubernetes deployment

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
DEPLOYMENT_TYPE=${1:-"local"}  # local, staging, production
PROJECT_NAME="vitaex-agentic-platform"
NAMESPACE="vitaex"

echo -e "${BLUE}🚀 VitaeX Agentic AI Platform Deployment${NC}"
echo -e "${BLUE}Deployment type: $DEPLOYMENT_TYPE${NC}"
echo "================================================"

# Function to print status messages
log_info() {
    echo -e "${GREEN}ℹ️  $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to detect docker compose command
get_docker_compose_cmd() {
    if command -v docker-compose >/dev/null 2>&1; then
        echo "docker-compose"
    elif docker compose version >/dev/null 2>&1; then
        echo "docker compose"
    else
        log_error "Neither docker-compose nor docker compose available"
        log_error "Please install Docker Desktop from: https://docs.docker.com/desktop/install/mac-install/"
        exit 1
    fi
}

# Function to wait for service to be ready
wait_for_service() {
    local service=$1
    local max_wait=${2:-60}
    local check_command=$3
    local waited=0
    
    log_info "Waiting for $service to be ready..."
    
    while [ $waited -lt $max_wait ]; do
        if eval "$check_command" >/dev/null 2>&1; then
            log_info "$service is ready!"
            return 0
        fi
        sleep 5
        waited=$((waited + 5))
    done
    
    log_error "$service failed to start within ${max_wait}s" 
    return 1
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check Python
    if ! command_exists python; then
        log_error "Python is required but not installed"
        exit 1
    fi
    
    python_version=$(python --version 2>&1 | cut -d' ' -f2)
    if [[ ! "$python_version" =~ ^3\.1[1-9] ]]; then
        log_warning "Python 3.11+ recommended, found $python_version"
    fi
    
    # Check Docker for local deployment
    if [ "$DEPLOYMENT_TYPE" = "local" ]; then
        if ! command_exists docker; then
            log_error "Docker is required for local deployment"
            exit 1
        fi
        
        if ! docker info >/dev/null 2>&1; then
            log_error "Docker daemon is not running"
            exit 1
        fi
    fi
    
    # Check kubectl for Kubernetes deployment
    if [ "$DEPLOYMENT_TYPE" != "local" ]; then
        if ! command_exists kubectl; then
            log_error "kubectl is required for Kubernetes deployment"
            exit 1
        fi
        
        if ! kubectl cluster-info >/dev/null 2>&1; then
            log_error "kubectl not connected to a cluster"
            exit 1
        fi
    fi
    
    log_info "✓ Prerequisites check passed"
}

# Setup Python environment
setup_python_env() {
    log_info "Setting up Python environment..."
    
    if [ ! -d "venv" ]; then
        python -m venv venv
    fi
    
    source venv/bin/activate
    pip install -U pip
    pip install -r requirements.txt
    
    log_info "✓ Python environment ready"
}

# Setup local development environment
deploy_local() {
    log_info "Deploying local development environment..."
    
    # Check environment file first
    if [ ! -f ".env" ]; then
        log_warning "No .env file found, copying from template"
        cp .env.example .env
        log_error "Please edit .env with your API keys before running"
        exit 1
    fi
    
    # Detect the correct docker compose command for M2 Mac
    COMPOSE_CMD=$(get_docker_compose_cmd)
    log_info "Using Docker Compose command: $COMPOSE_CMD"
    
    # Start infrastructure services
    log_info "Starting infrastructure services..."
    $COMPOSE_CMD -f docker-compose.dev.yml up -d
    
    # Wait for services to be ready
    wait_for_service "PostgreSQL" 60 "docker exec vitaex-timescaledb pg_isready -U postgres"
    wait_for_service "Kafka" 90 "docker exec vitaex-kafka kafka-topics --bootstrap-server localhost:9092 --list"
    wait_for_service "Neo4j" 60 "docker exec vitaex-neo4j cypher-shell -u neo4j -p password 'RETURN 1'"
    
    # Initialize databases - extensions are handled by init script
    log_info "Verifying database extensions..."
    
    # Verify TimescaleDB extensions
    docker exec vitaex-timescaledb psql -U postgres -d vitaex -c "
        SELECT extname FROM pg_extension WHERE extname IN ('timescaledb', 'vector');
    "
    
    # Create Kafka topics safely
    log_info "Creating Kafka topics..."
    chmod +x scripts/create-kafka-topics.sh
    
    # Copy script into container and execute to avoid command injection
    docker cp scripts/create-kafka-topics.sh vitaex-kafka:/tmp/create-kafka-topics.sh
    docker exec vitaex-kafka bash /tmp/create-kafka-topics.sh
    
    # Start the agentic platform
    log_info "Starting agentic platform..."
    source venv/bin/activate
    
    # Run in background with PID tracking
    nohup uvicorn api.service:app --host 0.0.0.0 --port 8080 --reload > platform.log 2>&1 &
    PLATFORM_PID=$!
    
    # Save PID for cleanup
    echo $PLATFORM_PID > platform.pid
    
    # Verify PID is valid
    if ! kill -0 $PLATFORM_PID 2>/dev/null; then
        log_error "Failed to start platform process"
        exit 1
    fi
    
    # Wait for platform to start
    wait_for_service "Agentic Platform" 30 "curl -s http://localhost:8080/health"
    
    log_info "✅ Local deployment completed successfully!"
    echo ""
    echo -e "${GREEN}🎉 VitaeX Agentic Platform is running locally:${NC}"
    echo "  • API: http://localhost:8080"
    echo "  • Health: http://localhost:8080/health"
    echo "  • API Docs: http://localhost:8080/docs"
    echo "  • Kafka UI: http://localhost:8081"
    echo "  • Neo4j Browser: http://localhost:7474"
    echo ""
    echo -e "${YELLOW}📝 Next steps:${NC}"
    echo "  1. Test with: curl http://localhost:8080/health/ready"
    echo "  2. Import knowledge graph: curl -X POST http://localhost:8080/orchestrator/research/import"
    echo "  3. View logs: tail -f platform.log"
    echo "  4. Stop with: ./deploy.sh cleanup"
}

# Deploy to Kubernetes
deploy_kubernetes() {
    log_info "Deploying to Kubernetes cluster..."
    
    local context=$(kubectl config current-context)
    log_info "Using Kubernetes context: $context"
    
    # Create namespace
    log_info "Creating namespace..."
    kubectl apply -f deployment/k8s/namespace.yaml
    
    # Check if using Istio
    if kubectl get pods -n istio-system >/dev/null 2>&1; then
        log_info "Istio detected, enabling service mesh"
        kubectl label namespace $NAMESPACE istio-injection=enabled --overwrite
    fi
    
    # Deploy Strimzi operator if not exists
    if ! kubectl get crd kafkas.kafka.strimzi.io >/dev/null 2>&1; then
        log_info "Installing Strimzi Kafka operator..."
        kubectl create namespace kafka --dry-run=client -o yaml | kubectl apply -f -
        kubectl apply -f 'https://strimzi.io/install/latest?namespace=kafka' -n kafka
        
        # Wait for operator to be ready
        kubectl wait deployment/strimzi-cluster-operator --for=condition=Available --timeout=300s -n kafka
    fi
    
    # Deploy Kafka cluster
    log_info "Deploying Kafka cluster..."
    kubectl apply -f deployment/k8s/kafka/strimzi-kafka-cluster.yaml
    
    # Wait for Kafka to be ready
    kubectl wait kafka/vitaex-kafka --for=condition=Ready --timeout=600s -n $NAMESPACE
    
    # Deploy databases
    log_info "Deploying databases..."
    kubectl apply -f deployment/k8s/neo4j/neo4j.yaml
    kubectl apply -f deployment/k8s/postgres-timescale/postgres.yaml
    
    # Wait for databases to be ready
    kubectl wait deployment/neo4j --for=condition=Available --timeout=300s -n $NAMESPACE
    kubectl wait deployment/timescale --for=condition=Available --timeout=300s -n $NAMESPACE
    
    # Create secrets (prompt user for values)
    create_k8s_secrets
    
    # Deploy application
    log_info "Deploying agentic platform application..."
    kubectl apply -f deployment/k8s/deployments/agentic-platform-deployment.yaml
    
    # Wait for application to be ready
    kubectl rollout status deployment/agentic-platform -n $NAMESPACE --timeout=300s
    
    # Deploy Istio gateway if available
    if kubectl get pods -n istio-system >/dev/null 2>&1; then
        kubectl apply -f deployment/k8s/istio/gateway-virtualservice.yaml
    fi
    
    log_info "✅ Kubernetes deployment completed successfully!"
    
    # Show connection information
    show_k8s_info
}

# Create Kubernetes secrets interactively
create_k8s_secrets() {
    log_info "Creating Kubernetes secrets..."
    
    # Check if secrets already exist
    if kubectl get secret graph-secrets -n $NAMESPACE >/dev/null 2>&1; then
        log_info "Secrets already exist, skipping creation"
        return 0
    fi
    
    log_warning "Creating secrets - you'll be prompted for credentials"
    
    # Neo4j secrets
    read -p "Neo4j password: " -s neo4j_password
    echo ""
    kubectl create secret generic graph-secrets \
        --from-literal=user=neo4j \
        --from-literal=password="$neo4j_password" \
        --from-literal=auth="neo4j/$neo4j_password" \
        -n $NAMESPACE
    
    # PostgreSQL secrets  
    read -p "PostgreSQL password: " -s pg_password
    echo ""
    kubectl create secret generic ts-secrets \
        --from-literal=user=postgres \
        --from-literal=password="$pg_password" \
        --from-literal=dsn="postgresql://postgres:$pg_password@timescale.vitaex.svc.cluster.local:5432/vitaex" \
        -n $NAMESPACE
    
    kubectl create secret generic vec-secrets \
        --from-literal=dsn="postgresql://postgres:$pg_password@timescale.vitaex.svc.cluster.local:5432/vitaex" \
        -n $NAMESPACE
    
    # OpenAI API key
    read -p "OpenAI API key: " -s openai_key
    echo ""
    kubectl create secret generic openai-secrets \
        --from-literal=api_key="$openai_key" \
        -n $NAMESPACE
    
    log_info "✓ Secrets created successfully"
}

# Show Kubernetes deployment information
show_k8s_info() {
    echo ""
    echo -e "${GREEN}🎉 Kubernetes deployment information:${NC}"
    
    # Get service endpoints
    echo "Services:"
    kubectl get svc -n $NAMESPACE
    
    echo ""
    echo "Pods:"
    kubectl get pods -n $NAMESPACE
    
    echo ""
    echo -e "${YELLOW}📝 Connection information:${NC}"
    
    # Port forward instructions
    echo "To access services locally:"
    echo "  kubectl port-forward svc/agentic-platform 8080:80 -n $NAMESPACE"
    echo "  kubectl port-forward svc/neo4j 7474:7474 -n $NAMESPACE" 
    echo "  kubectl port-forward svc/timescale 5432:5432 -n $NAMESPACE"
    
    # Get external IPs if available
    external_ip=$(kubectl get svc istio-ingressgateway -n istio-system -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "")
    if [ -n "$external_ip" ]; then
        echo ""
        echo "External access (via Istio):"
        echo "  API: http://$external_ip/api"
        echo "  Health: http://$external_ip/health"
    fi
}

# Verification and testing
run_verification() {
    log_info "Running deployment verification..."
    
    if [ "$DEPLOYMENT_TYPE" = "local" ]; then
        base_url="http://localhost:8080"
    else
        # For Kubernetes, use port-forward
        kubectl port-forward svc/agentic-platform 8080:80 -n $NAMESPACE >/dev/null 2>&1 &
        PORT_FORWARD_PID=$!
        sleep 5
        base_url="http://localhost:8080"
    fi
    
    # Test health endpoints
    echo "Testing health endpoints..."
    
    if curl -sf "$base_url/health" >/dev/null; then
        log_info "✓ Basic health check passed"
    else
        log_error "✗ Basic health check failed"
        return 1
    fi
    
    if curl -sf "$base_url/health/ready" >/dev/null; then
        log_info "✓ Readiness check passed"
    else
        log_warning "⚠ Readiness check failed - agents may still be starting"
    fi
    
    # Test API documentation
    if curl -sf "$base_url/docs" >/dev/null; then
        log_info "✓ API documentation accessible"
    else
        log_warning "⚠ API documentation not accessible"
    fi
    
    # Clean up port forward if created
    if [ -n "$PORT_FORWARD_PID" ]; then
        kill $PORT_FORWARD_PID >/dev/null 2>&1 || true
    fi
    
    log_info "✅ Verification completed"
}

# Cleanup function
cleanup_local() {
    log_info "Cleaning up local environment..."
    
    # Stop platform if running
    if [ -f "platform.pid" ]; then
        local pid=$(cat platform.pid)
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" >/dev/null 2>&1 || true
            log_info "Stopped platform process (PID: $pid)"
        fi
        rm platform.pid
    fi
    
    # Stop Docker services using the correct command
    COMPOSE_CMD=$(get_docker_compose_cmd)
    $COMPOSE_CMD -f docker-compose.dev.yml down
    
    log_info "✓ Local environment cleaned up"
}

# Main deployment logic
main() {
    case "$DEPLOYMENT_TYPE" in
        "local")
            check_prerequisites
            setup_python_env
            deploy_local
            run_verification
            ;;
        "staging"|"production")
            check_prerequisites
            deploy_kubernetes
            run_verification
            ;;
        "cleanup")
            cleanup_local
            ;;
        *)
            echo "Usage: $0 {local|staging|production|cleanup}"
            echo ""
            echo "Examples:"
            echo "  $0 local     # Deploy for local development"
            echo "  $0 staging   # Deploy to staging Kubernetes"  
            echo "  $0 production # Deploy to production Kubernetes"
            echo "  $0 cleanup   # Clean up local environment"
            exit 1
            ;;
    esac
}

# Error handling with informative messages
trap 'log_error "Deployment failed at line $LINENO"; exit 1' ERR

# Run main function
main "$@"