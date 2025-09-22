# VitaeX Agentic AI Platform - Deployment Guide

This guide provides step-by-step instructions for deploying the VitaeX Agentic AI Platform in both development and production environments.

## Prerequisites

### Required Software
- Python 3.11+ 
- Docker and Docker Compose
- kubectl (Kubernetes CLI)
- Helm 3.x (for Kafka/database deployments)
- Git

### Required Services
- Kubernetes cluster (local: kind/minikube, cloud: EKS/GKE/AKS)
- Domain name for production (e.g., `api.vitaex.health`)

### External API Credentials
You'll need credentials for:
- OpenAI API (for protocol generation)
- Spike API (for wearables integration)
- Omnos/Regenerus Labs API
- Your existing Supabase project

## Quick Start - Local Development

### Step 1: Environment Setup

```bash
# Clone the agentic platform (if not already done)
git clone <your-repo-url>
cd agentic-platform

# Create and activate Python virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
make install
```

### Step 2: Start Local Infrastructure

```bash
# Start local Kafka, PostgreSQL, and Neo4j using Docker Compose
cat > docker-compose.dev.yml << 'EOF'
version: '3.8'
services:
  kafka:
    image: confluentinc/cp-kafka:7.4.0
    environment:
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://localhost:9092
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
      KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR: 1
      KAFKA_TRANSACTION_STATE_LOG_MIN_ISR: 1
    ports:
      - "9092:9092"
    depends_on:
      - zookeeper

  zookeeper:
    image: confluentinc/cp-zookeeper:7.4.0
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181
    ports:
      - "2181:2181"

  timescaledb:
    image: timescale/timescaledb-ha:pg16-latest
    environment:
      POSTGRES_DB: vitaex
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: password
    ports:
      - "5432:5432"
    volumes:
      - timescale_data:/var/lib/postgresql/data

  neo4j:
    image: neo4j:5.20.0
    environment:
      NEO4J_AUTH: neo4j/password
    ports:
      - "7687:7687" # Bolt
      - "7474:7474" # HTTP
    volumes:
      - neo4j_data:/data

volumes:
  timescale_data:
  neo4j_data:
EOF

# Start services
docker-compose -f docker-compose.dev.yml up -d
```

### Step 3: Configure Environment

```bash
# Copy environment template and configure
cp .env.example .env
```

Edit `.env` with your specific values:

```bash
# Database connections
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
TIMESERIES_DSN=postgresql://postgres:password@localhost:5432/vitaex
VECTOR_DSN=postgresql://postgres:password@localhost:5432/vitaex

# API keys
OPENAI_API_KEY=sk-your-openai-key
JWT_SECRET=your-jwt-secret-here

# Spike API credentials
SPIKE_API_BASE_URL=https://app-api.spikeapi.com/v3
SPIKE_APP_ID=your-app-id
SPIKE_CLIENT_ID=your-client-id
SPIKE_CLIENT_SECRET=your-client-secret
SPIKE_SIGNING_SECRET=your-signing-secret
SPIKE_REDIRECT_URL=http://localhost:8080/callback

# Omnos credentials
OMNOS_BASE_URL=https://api.omnos.me/v1
OMNOS_TOKEN=your-omnos-token

# Development settings
CORS_ALLOW_ORIGINS=http://localhost:3000,http://localhost:8080
```

### Step 4: Initialize Databases

```bash
# Wait for services to be ready
sleep 30

# Initialize TimescaleDB with required extensions
docker exec $(docker ps -qf "name=timescaledb") psql -U postgres -d vitaex -c "
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS vector;
"

# Test database connections
python -c "
from common.persistence.timeseries_client import TimeseriesClient
from common.persistence.graph_client import GraphClient
from common.persistence.vector_client import VectorClient

ts = TimeseriesClient()
graph = GraphClient()
vector = VectorClient()

print('Database connections successful!')
"
```

### Step 5: Start the Agentic Platform

```bash
# Run the platform (starts all agents and API)
make run

# Verify it's working
curl http://localhost:8080/health
```

### Step 6: Import Knowledge Graph Data (Optional)

```bash
# In a separate terminal, import health knowledge graph data
cd ../health-knowledge-graph
python comprehensive_import.py

# The knowledge graph agent will automatically sync this to Neo4j
curl -X POST http://localhost:8080/orchestrator/research/import
```

## Production Deployment on Kubernetes

### Step 1: Prepare Kubernetes Cluster

```bash
# Create namespace and apply base resources
kubectl apply -f deployment/k8s/namespace.yaml

# Install Strimzi Operator for Kafka
kubectl create namespace kafka
kubectl apply -f 'https://strimzi.io/install/latest?namespace=kafka' -n kafka

# Install Istio (optional, for service mesh)
curl -L https://istio.io/downloadIstio | sh -
istioctl install --set values.defaultRevision=default -y
```

### Step 2: Deploy Infrastructure Services

```bash
# Deploy Kafka cluster
kubectl apply -f deployment/k8s/kafka/strimzi-kafka-cluster.yaml

# Wait for Kafka to be ready (2-5 minutes)
kubectl wait kafka/vitaex-kafka --for=condition=Ready --timeout=300s -n vitaex

# Deploy databases
kubectl apply -f deployment/k8s/neo4j/neo4j.yaml
kubectl apply -f deployment/k8s/postgres-timescale/postgres.yaml
```

### Step 3: Create Secrets

```bash
# Create database secrets
kubectl create secret generic graph-secrets \
  --from-literal=user=neo4j \
  --from-literal=password=your-neo4j-password \
  --from-literal=auth=neo4j/your-neo4j-password \
  -n vitaex

kubectl create secret generic ts-secrets \
  --from-literal=user=postgres \
  --from-literal=password=your-postgres-password \
  --from-literal=dsn="postgresql://postgres:your-postgres-password@timescale.vitaex.svc.cluster.local:5432/vitaex" \
  -n vitaex

kubectl create secret generic vec-secrets \
  --from-literal=dsn="postgresql://postgres:your-postgres-password@timescale.vitaex.svc.cluster.local:5432/vitaex" \
  -n vitaex

# Create OpenAI secret
kubectl create secret generic openai-secrets \
  --from-literal=api_key=your-openai-api-key \
  -n vitaex

# Create Spike API secrets
kubectl create secret generic spike-secrets \
  --from-literal=app_id=your-spike-app-id \
  --from-literal=client_id=your-spike-client-id \
  --from-literal=client_secret=your-spike-client-secret \
  --from-literal=signing_secret=your-spike-signing-secret \
  -n vitaex

# Create Omnos secret
kubectl create secret generic omnos-secrets \
  --from-literal=token=your-omnos-token \
  -n vitaex
```

### Step 4: Build and Push Container Image

```bash
# Create Dockerfile
cat > Dockerfile << 'EOF'
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user
RUN useradd --create-home --shell /bin/bash app && chown -R app:app /app
USER app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

EXPOSE 8080

CMD ["uvicorn", "api.service:app", "--host", "0.0.0.0", "--port", "8080"]
EOF

# Build and push image (replace with your registry)
docker build -t ghcr.io/your-org/vitaex-agentic-platform:latest .
docker push ghcr.io/your-org/vitaex-agentic-platform:latest
```

### Step 5: Deploy Application

```bash
# Update deployment with your image
sed -i 's|ghcr.io/vitaex/agentic-platform:latest|ghcr.io/your-org/vitaex-agentic-platform:latest|' \
  deployment/k8s/deployments/agentic-platform-deployment.yaml

# Deploy the application
kubectl apply -f deployment/k8s/deployments/agentic-platform-deployment.yaml

# Wait for deployment to be ready
kubectl rollout status deployment/agentic-platform -n vitaex
```

### Step 6: Configure Ingress and SSL

```bash
# Install cert-manager for SSL certificates (if using Istio)
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml

# Apply Istio Gateway and VirtualService
kubectl apply -f deployment/k8s/istio/gateway-virtualservice.yaml

# Or use a regular Ingress (alternative to Istio)
cat > ingress.yaml << 'EOF'
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: vitaex-ingress
  namespace: vitaex
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  tls:
  - hosts:
    - api.vitaex.health
    secretName: vitaex-tls
  rules:
  - host: api.vitaex.health
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: agentic-platform
            port:
              number: 80
EOF

kubectl apply -f ingress.yaml
```

### Step 7: Verify Deployment

```bash
# Check all pods are running
kubectl get pods -n vitaex

# Check services are accessible
kubectl port-forward svc/agentic-platform 8080:80 -n vitaex

# Test health endpoints
curl http://localhost:8080/health
curl http://localhost:8080/health/ready
```

## Configuration Management

### Environment Variables

Update the deployment with your environment-specific values:

```yaml
# In deployment/k8s/deployments/agentic-platform-deployment.yaml
env:
  - name: KAFKA_BOOTSTRAP_SERVERS
    value: vitaex-kafka-bootstrap.vitaex.svc.cluster.local:9092
  - name: SPIKE_REDIRECT_URL
    value: https://api.vitaex.health/api/spike/callback
  # Add other production URLs and settings
```

### Secrets Management

For production, use external secret management:

```bash
# Example with AWS Secrets Manager
kubectl apply -f - <<EOF
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: aws-secret-store
  namespace: vitaex
spec:
  provider:
    aws:
      service: SecretsManager
      region: us-west-2
---
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: api-secrets
  namespace: vitaex
spec:
  refreshInterval: 15s
  secretStoreRef:
    name: aws-secret-store
    kind: SecretStore
  target:
    name: openai-secrets
    creationPolicy: Owner
  data:
  - secretKey: api_key
    remoteRef:
      key: vitaex/openai-api-key
EOF
```

## Integration with Existing Components

### Health Knowledge Graph Integration

```bash
# Copy your existing health knowledge graph
cp -r ../health-knowledge-graph ./external/

# Mount as volume in Kubernetes (development)
kubectl create configmap health-kg-source \
  --from-file=../health-knowledge-graph \
  -n vitaex

# Update deployment to include volume mount
# Add to deployment/k8s/deployments/agentic-platform-deployment.yaml
```

### iOS App Integration

Update your iOS app to point to the new agentic platform endpoints:

```typescript
// In vitaex-ios/vitaex/src/api/spike.ts
const VITAEX_API_BASE_URL = 'https://api.vitaex.health/api/spike';
// All your existing spike.ts functions will work with the new backend
```

## Monitoring and Observability

### Step 1: Install Observability Stack

```bash
# Install Prometheus and Grafana
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install prometheus prometheus-community/kube-prometheus-stack -n vitaex

# Install OpenTelemetry Collector
kubectl apply -f - <<EOF
apiVersion: opentelemetry.io/v1alpha1
kind: OpenTelemetryCollector
metadata:
  name: otel-collector
  namespace: vitaex
spec:
  config: |
    receivers:
      otlp:
        protocols:
          grpc:
            endpoint: 0.0.0.0:4317
          http:
            endpoint: 0.0.0.0:4318
    processors:
      batch:
    exporters:
      prometheus:
        endpoint: "0.0.0.0:8889"
      logging:
        loglevel: debug
    service:
      pipelines:
        traces:
          receivers: [otlp]
          processors: [batch]
          exporters: [logging]
        metrics:
          receivers: [otlp]
          processors: [batch]
          exporters: [prometheus]
EOF
```

### Step 2: Configure Application Monitoring

The application is already instrumented with OpenTelemetry. Set the collector endpoint:

```bash
# Update deployment environment
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector.vitaex.svc.cluster.local:4318
```

## Testing and Verification

### Step 1: Basic Health Checks

```bash
# Test platform health
kubectl port-forward svc/agentic-platform 8080:80 -n vitaex
curl http://localhost:8080/health/ready

# Should return:
# {
#   "status": "ready",
#   "agents": ["orchestrator", "data_ingestion_agent", ...]
# }
```

### Step 2: Test Agent Communication

```bash
# Trigger research import
curl -X POST http://localhost:8080/orchestrator/research/import

# Check agent activity in logs
kubectl logs deployment/agentic-platform -n vitaex | grep "agent"
```

### Step 3: Test Data Ingestion

```bash
# Grant user consent for testing
curl -X POST http://localhost:8080/consent/grant \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test-user-123",
    "purpose": "data_processing",
    "scope": "wearables,labs"
  }'

# Test Omnos sync
curl -X POST http://localhost:8080/omnos/sync/test-user-123
```

### Step 4: Test Protocol Generation

```bash
# Generate a wellness protocol
curl -X POST http://localhost:8080/protocol/generate/test-user-123 \
  -H "Content-Type: application/json" \
  -d '{"context_ref": "daily_wellness"}'

# Check for protocol in logs
kubectl logs deployment/agentic-platform -n vitaex | grep "protocol"
```

## Scaling Configuration

### Horizontal Pod Autoscaling

```bash
# Apply HPA for the main service
kubectl apply -f - <<EOF
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: agentic-platform-hpa
  namespace: vitaex
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: agentic-platform
  minReplicas: 3
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
EOF
```

### Database Scaling

```bash
# For production, use managed services:
# - Amazon RDS/Aurora for TimescaleDB
# - Amazon MSK or Confluent Cloud for Kafka
# - Neo4j AuraDB for graph database

# Example RDS connection:
TIMESERIES_DSN=postgresql://username:password@vitaex-cluster.cluster-xxx.us-west-2.rds.amazonaws.com:5432/vitaex
```

## Security Configuration

### Network Policies

```bash
kubectl apply -f - <<EOF
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: vitaex-network-policy
  namespace: vitaex
spec:
  podSelector:
    matchLabels:
      app: agentic-platform
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: istio-system
    ports:
    - protocol: TCP
      port: 8080
  egress:
  - to:
    - namespaceSelector:
        matchLabels:
          name: vitaex
    ports:
    - protocol: TCP
      port: 9092  # Kafka
    - protocol: TCP
      port: 5432  # PostgreSQL
    - protocol: TCP
      port: 7687  # Neo4j
  - to: []
    ports:
    - protocol: TCP
      port: 443   # HTTPS for external APIs
EOF
```

### SSL/TLS Configuration

```bash
# Create TLS certificate (using cert-manager)
kubectl apply -f - <<EOF
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: vitaex-tls
  namespace: vitaex
spec:
  secretName: vitaex-tls-secret
  issuerRef:
    name: letsencrypt-prod
    kind: ClusterIssuer
  dnsNames:
  - api.vitaex.health
EOF
```

## Integration Testing

### Test Spike API Integration

```bash
# Test signature generation
curl -X POST http://localhost:8080/api/spike/generate-signature \
  -H "Content-Type: application/json" \
  -d '{"userId": "test-user-123"}'

# Test authentication
curl -X POST http://localhost:8080/api/spike/auth \
  -H "Content-Type: application/json" \
  -d '{"userId": "test-user-123"}'
```

### Test iOS App Connection

Update your iOS app configuration:

```typescript
// In vitaex-ios/vitaex/src/config/environment.ts
export const API_BASE_URL = 'https://api.vitaex.health';

// Your existing Spike integration will automatically use the new backend
```

## Troubleshooting

### Common Issues

1. **Kafka Connection Issues**
```bash
# Check Kafka cluster status
kubectl get kafka vitaex-kafka -n vitaex -o yaml

# Check topic creation
kubectl get kafkatopics -n vitaex
```

2. **Database Connection Issues** 
```bash
# Test database connectivity
kubectl exec deployment/agentic-platform -n vitaex -- python -c "
from common.persistence.timeseries_client import TimeseriesClient
ts = TimeseriesClient()
print('TimescaleDB connected!')
"
```

3. **Agent Communication Issues**
```bash
# Check agent status
curl http://localhost:8080/health/ready

# Monitor agent logs
kubectl logs deployment/agentic-platform -n vitaex -f | grep "agent"
```

### Log Analysis

```bash
# View all platform logs
kubectl logs deployment/agentic-platform -n vitaex --tail=100

# View specific agent activity
kubectl logs deployment/agentic-platform -n vitaex | grep "knowledge_graph_agent"

# Monitor events in real-time  
kubectl logs deployment/agentic-platform -n vitaex -f | grep "Published event"
```

## Performance Optimization

### Database Optimization

```sql
-- TimescaleDB optimizations
CREATE INDEX CONCURRENTLY idx_measurements_user_metric_time 
ON measurements (user_id, metric, ts DESC);

-- Vector database optimization  
SET ivfflat.probes = 10;
CREATE INDEX CONCURRENTLY ON embeddings 
USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

### Kafka Optimization

```yaml
# In strimzi-kafka-cluster.yaml, optimize for your workload:
spec:
  kafka:
    replicas: 3
    config:
      # High throughput settings
      num.network.threads: 8
      num.io.threads: 16
      socket.send.buffer.bytes: 102400
      socket.receive.buffer.bytes: 102400
      socket.request.max.bytes: 104857600
      num.partitions: 6
      default.replication.factor: 3
```

## Maintenance and Updates

### Backup Procedures

```bash
# Backup TimescaleDB
kubectl exec deployment/timescale -n vitaex -- pg_dump -U postgres vitaex > backup-$(date +%Y%m%d).sql

# Backup Neo4j
kubectl exec deployment/neo4j -n vitaex -- neo4j-admin backup --backup-dir=/backup

# Backup Kafka (use Strimzi backup operators)
kubectl apply -f https://strimzi.io/examples/latest/kafka/kafka-backup.yaml
```

### Update Procedures

```bash
# Update application
docker build -t ghcr.io/your-org/vitaex-agentic-platform:v1.1.0 .
docker push ghcr.io/your-org/vitaex-agentic-platform:v1.1.0

# Rolling update
kubectl set image deployment/agentic-platform api=ghcr.io/your-org/vitaex-agentic-platform:v1.1.0 -n vitaex
kubectl rollout status deployment/agentic-platform -n vitaex
```

## Migration from Existing System

### Step 1: Parallel Deployment

Run both systems in parallel initially:

```bash
# Deploy agentic platform to new namespace
kubectl create namespace vitaex-staging
# Deploy using staging configuration
```

### Step 2: Data Migration

```bash
# Migrate existing health graph data
kubectl exec deployment/agentic-platform -n vitaex -- python -c "
import sys
sys.path.append('/app/external/health-knowledge-graph')
from enhanced_import_system import main
main()  # This will sync existing data to Neo4j
"
```

### Step 3: Traffic Switching

Use Istio or ingress weighted routing to gradually shift traffic:

```yaml
# In VirtualService, add traffic splitting
http:
- match:
  - uri:
      prefix: /api/spike
  route:
  - destination:
      host: agentic-platform.vitaex.svc.cluster.local
    weight: 100  # Start with 100% to new system
  - destination:
      host: legacy-system.vitaex.svc.cluster.local  
    weight: 0    # Gradually decrease
```

## Support and Monitoring

### Alerting Rules

```yaml
# Prometheus alerts for critical issues
groups:
- name: vitaex-agents
  rules:
  - alert: AgentDown
    expr: up{job="agentic-platform"} == 0
    for: 1m
    annotations:
      summary: "VitaeX agent is down"
  
  - alert: HighErrorRate  
    expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.1
    annotations:
      summary: "High error rate detected"
```

Your agentic AI platform is now ready for deployment! The system will integrate seamlessly with your existing iOS app and health knowledge graph while providing the new multi-agent capabilities, B2B practitioner workflows, and compliance features you need.