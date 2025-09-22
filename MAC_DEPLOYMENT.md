# VitaeX Agentic AI Platform - M2 Mac Deployment Guide

This guide provides M2 Mac-specific instructions for testing and deploying your agentic AI platform alongside your existing Health Knowledge Graph and iOS app.

## Prerequisites for M2 Mac

### Required Software
```bash
# Install Homebrew if not already installed
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install required tools
brew install python@3.11 docker kubectl helm

# Verify Python version
python3.11 --version  # Should be 3.11.x
```

### Docker Desktop for M2 Mac
```bash
# Download and install Docker Desktop for Apple Silicon
# From: https://docs.docker.com/desktop/install/mac-install/
# Make sure to get the "Mac with Apple chip" version

# Start Docker Desktop and enable Kubernetes (optional for local testing)
# Settings → Kubernetes → Enable Kubernetes
```

## Quick Setup for Testing (30 minutes)

### Step 1: Setup the Agentic Platform

```bash
# Navigate to your project directory (assuming parallel to vitaex-ios)
cd agentic-platform

# Create Python virtual environment using Python 3.11
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies 
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 2: Configure Environment

```bash
# Copy and customize environment file
cp .env.example .env

# Edit .env with your existing credentials
# You can use your existing Spike and Omnos credentials from vitaex-ios
```

**Sample .env configuration for your setup:**
```bash
# Database connections (local Docker)
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
TIMESERIES_DSN=postgresql://postgres:password@localhost:5432/vitaex
VECTOR_DSN=postgresql://postgres:password@localhost:5432/vitaex

# API Keys (use your existing ones from vitaex-ios)
OPENAI_API_KEY=sk-your-existing-openai-key
JWT_SECRET=your-jwt-secret-here

# Spike API (copy from vitaex-ios environment)
SPIKE_API_BASE_URL=https://app-api.spikeapi.com/v3
SPIKE_APP_ID=your-app-id
SPIKE_CLIENT_ID=your-client-id
SPIKE_CLIENT_SECRET=your-client-secret
SPIKE_SIGNING_SECRET=your-signing-secret
SPIKE_REDIRECT_URL=http://localhost:8080/api/spike/callback

# Omnos (copy from vitaex-ios)
OMNOS_BASE_URL=https://api.omnos.me/v1
OMNOS_TOKEN=your-omnos-token

# Local development
CORS_ALLOW_ORIGINS=http://localhost:3000,http://localhost:8080
```

### Step 3: Start Local Infrastructure (M2 Mac optimized)

```bash
# Use the provided Docker Compose with M2 Mac optimizations
docker-compose -f docker-compose.dev.yml up -d

# Wait for services to start (M2 Mac may need more time)
sleep 45

# Verify services are running
docker ps
```

### Step 4: Initialize Databases

```bash
# The init script runs automatically, but verify extensions
docker exec vitaex-timescaledb psql -U postgres -d vitaex -c "
  SELECT extname, extversion FROM pg_extension 
  WHERE extname IN ('timescaledb', 'vector');
"

# Should show both timescaledb and vector extensions

# Test Neo4j connection
docker exec vitaex-neo4j cypher-shell -u neo4j -p password "RETURN 'Connected!' as status"
```

### Step 5: Start the Agentic Platform

```bash
# Ensure virtual environment is activated
source venv/bin/activate

# Start the platform
uvicorn api.service:app --host 0.0.0.0 --port 8080 --reload
```

### Step 6: Verify Everything Works

Open a new terminal and run:

```bash
# Basic health check
curl http://localhost:8080/health

# Check all agents are running
curl http://localhost:8080/health/ready

# Should show: {"status": "ready", "agents": ["data_ingestion_agent", "knowledge_graph_agent", ...]}
```

## Integration with Your Existing Components

### Step 1: Integrate Your Health Knowledge Graph

```bash
# Copy your health knowledge graph data to the agentic platform
cp -r ../health-knowledge-graph/data agentic-platform/external/health-kg-data/

# Import existing knowledge graph data into Neo4j
curl -X POST http://localhost:8080/orchestrator/research/import

# Verify import in Neo4j browser
open http://localhost:7474
# Login: neo4j / password
# Query: MATCH (n) RETURN count(n) as total_nodes
```

### Step 2: Test with Your iOS App

Your iOS app can now use the new backend while keeping the existing Supabase functions as backup.

**Option A: Update iOS app to test new endpoints**

In your `vitaex-ios` project, update the API configuration:

```typescript
// In vitaex-ios/vitaex/src/config/environment.ts (create if not exists)
export const AGENTIC_API_BASE_URL = 'http://localhost:8080';
export const SPIKE_NEW_API_BASE_URL = 'http://localhost:8080/api/spike';

// Test the new Spike endpoints
export const testNewSpike = async (userId: string) => {
  const response = await fetch(`${SPIKE_NEW_API_BASE_URL}/generate-signature`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ userId })
  });
  return response.json();
};
```

**Option B: Test directly with curl while keeping iOS app unchanged**

```bash
# Test Spike API integration
curl -X POST http://localhost:8080/api/spike/generate-signature \
  -H "Content-Type: application/json" \
  -d '{"userId": "test-user-123"}'

# Test Omnos integration  
curl -X POST http://localhost:8080/omnos/sync/test-user-123

# Test protocol generation
curl -X POST http://localhost:8080/protocol/generate/test-user-123 \
  -H "Content-Type: application/json"
```

### Step 3: Test Agent Communication

```bash
# Test the event-driven agent system
curl -X POST http://localhost:8080/consent/grant \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test-user-123",
    "purpose": "personalization",
    "scope": "wearables,labs,protocols"
  }'

# Trigger vitality simulation
curl -X POST http://localhost:8080/simulation/vitality \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test-user-123",
    "sleep_minutes_delta": 60,
    "activity_minutes_delta": 30,
    "stress_reduction": 0.2,
    "current_vitality": 0.6
  }'

# Check agent logs for activity
tail -f platform.log | grep agent
```

## M2 Mac Specific Considerations

### Docker Performance on M2
```bash
# Increase Docker memory if needed
# Docker Desktop → Settings → Resources → Memory: 8GB+

# Use ARM-compatible images (most are already multi-arch)
# The docker-compose.dev.yml uses images that support ARM64
```

### Python Dependencies on M2
```bash
# If you encounter issues with binary packages:
export ARCHFLAGS="-arch arm64"
pip install --no-cache-dir --force-reinstall -r requirements.txt
```

### Database Performance
```bash
# M2 Macs handle the database load well, but if you need more performance:
docker exec vitaex-timescaledb psql -U postgres -d vitaex -c "
  ALTER SYSTEM SET shared_preload_libraries = 'timescaledb';
  ALTER SYSTEM SET max_connections = 200;
"
```

## Testing Your Complete System

### Test 1: Knowledge Graph Integration

```bash
# Verify your existing health knowledge graph works with agents
curl -X POST http://localhost:8080/orchestrator/research/import

# Check Neo4j for imported data
open http://localhost:7474
# Run: MATCH (n:Node) RETURN n.group, count(n) ORDER BY n.group
```

### Test 2: iOS App Integration

Keep your iOS app running as-is, but test the new endpoints:

```bash
# Test that your existing Spike integration data can be processed by agents
# Use a real user ID from your iOS app if available

USER_ID="your-actual-test-user-id"

# Grant consent
curl -X POST http://localhost:8080/consent/grant \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "'$USER_ID'",
    "purpose": "data_processing",
    "scope": "wearables,labs"
  }'

# Test Omnos sync (if you have real data)
curl -X POST http://localhost:8080/omnos/sync/$USER_ID
```

### Test 3: B2B Practitioner Features

```bash
# Test protocol review workflows
curl -X GET http://localhost:8080/reviews

# Test real-time collaboration WebSocket
# Use wscat or browser console:
# const ws = new WebSocket('ws://localhost:8080/ws/collab/test-room');
# ws.onmessage = (msg) => console.log('Received:', msg.data);
# ws.send('Hello from practitioner!');
```

### Test 4: Complete End-to-End Flow

```bash
# 1. Simulate wearable data ingestion → twin update → protocol generation
echo "Testing complete agent flow..."

# 2. Grant all necessary consents
curl -X POST http://localhost:8080/consent/grant \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test-user-123",
    "purpose": "data_processing",
    "scope": "all"
  }'

curl -X POST http://localhost:8080/consent/grant \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test-user-123", 
    "purpose": "personalization",
    "scope": "all"
  }'

# 3. Trigger protocol generation
curl -X POST http://localhost:8080/protocol/generate/test-user-123

# 4. Check logs for agent activity
tail -n 50 platform.log | grep -E "(agent|Published event|twin|protocol)"
```

## Troubleshooting M2 Mac Issues

### Common Issues and Fixes

**1. Docker compatibility issues:**
```bash
# Make sure you're using Docker Desktop for Apple Silicon
docker version | grep -i arm
# Should show arm64 architecture
```

**2. Python package compilation issues:**
```bash
# If packages fail to install:
export ARCHFLAGS="-arch arm64"
brew install postgresql  # For psycopg2 dependencies
pip install --no-binary=:all: psycopg2-binary
```

**3. Kafka connection issues:**
```bash
# Check Kafka is accessible
docker exec vitaex-kafka kafka-topics --bootstrap-server localhost:9092 --list

# If empty, manually create topics:
chmod +x scripts/create-kafka-topics.sh
docker cp scripts/create-kafka-topics.sh vitaex-kafka:/tmp/
docker exec vitaex-kafka bash /tmp/create-kafka-topics.sh
```

**4. Neo4j memory issues on M2:**
```bash
# If Neo4j runs slowly, increase memory:
docker-compose -f docker-compose.dev.yml down
# Edit docker-compose.dev.yml: 
# NEO4J_dbms_memory_heap_max__size: 2g
docker-compose -f docker-compose.dev.yml up -d neo4j
```

## Integration Testing with Your iPhone App

### Step 1: Test Spike API Compatibility

Your iOS app should continue working with Supabase, but test the new endpoints:

```bash
# Test the signature generation (used by your iOS app)
curl -X POST http://localhost:8080/api/spike/generate-signature \
  -H "Content-Type: application/json" \
  -d '{"userId": "test-user-from-ios"}'

# This should return the same format your iOS app expects
```

### Step 2: Gradual Migration Testing

```typescript
// In your iOS app, you can test both backends:
// Keep using Supabase for main functionality
// Test agentic platform for new features

const LEGACY_API = 'your-supabase-function-url';
const NEW_AGENTIC_API = 'http://localhost:8080';

// Example: Test protocol generation from new platform
const testNewProtocolGeneration = async (userId: string) => {
  try {
    const response = await fetch(`${NEW_AGENTIC_API}/protocol/generate/${userId}`, {
      method: 'POST'
    });
    return await response.json();
  } catch (error) {
    console.log('New platform not ready, using legacy');
    // Fallback to existing Supabase function
  }
};
```

## Next Steps: Production Deployment

### Option 1: Cloud Deployment (Recommended)

```bash
# Deploy to your preferred cloud provider
# Example with Google Cloud (good M2 Mac support):

# 1. Create GKE cluster
gcloud container clusters create vitaex-platform \
  --machine-type e2-standard-4 \
  --num-nodes 3 \
  --enable-autoscaling \
  --min-nodes 2 \
  --max-nodes 10

# 2. Get credentials
gcloud container clusters get-credentials vitaex-platform

# 3. Deploy using provided Kubernetes manifests
./deploy.sh production
```

### Option 2: Enhanced Local Deployment

If you want a more production-like local setup:

```bash
# Use kind (Kubernetes in Docker) on M2 Mac
brew install kind

# Create local Kubernetes cluster
cat > kind-config.yaml << 'EOF'
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
- role: control-plane
- role: worker
- role: worker
EOF

kind create cluster --config=kind-config.yaml --name vitaex

# Deploy using Kubernetes manifests
kubectl apply -f deployment/k8s/namespace.yaml
# Continue with full K8s deployment...
```

## Performance Optimization for M2 Mac

### Database Tuning

```bash
# Optimize PostgreSQL for M2 Mac
docker exec vitaex-timescaledb psql -U postgres -d vitaex -c "
  ALTER SYSTEM SET shared_buffers = '256MB';
  ALTER SYSTEM SET effective_cache_size = '1GB';
  ALTER SYSTEM SET maintenance_work_mem = '64MB';
  ALTER SYSTEM SET checkpoint_completion_target = 0.9;
  SELECT pg_reload_conf();
"

# Optimize Neo4j for M2 Mac memory
docker exec vitaex-neo4j neo4j-admin server memory-recommendation
```

### Kafka Optimization

```bash
# For M2 Mac, increase Kafka memory if needed
# Edit docker-compose.dev.yml and add:
# KAFKA_HEAP_OPTS: "-Xmx1G -Xms1G"
```

## Connecting Your iPhone App to the New Backend

### Gradual Integration Approach

1. **Phase 1: Test New Endpoints (Current)**
   - Keep your iOS app using Supabase
   - Test agentic platform endpoints separately
   - Verify data flows and agent communication

2. **Phase 2: Dual Backend (Next)**
   - Modify iOS app to optionally use agentic platform
   - Use feature flags to switch between backends
   - Test with your TestFlight users

3. **Phase 3: Full Migration (Later)**
   - Switch iOS app to use agentic platform primarily
   - Keep Supabase as backup/legacy
   - Deploy to production cloud

### Sample iOS Integration Code

```typescript
// In vitaex-ios/vitaex/src/services/AgenticPlatformService.ts (create new file)
class AgenticPlatformService {
  private baseUrl = 'http://localhost:8080'; // Change to production URL later
  
  async generateProtocol(userId: string): Promise<any> {
    const response = await fetch(`${this.baseUrl}/protocol/generate/${userId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    return response.json();
  }
  
  async getVitalitySimulation(userId: string, params: any): Promise<any> {
    const response = await fetch(`${this.baseUrl}/simulation/vitality`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId, ...params })
    });
    return response.json();
  }
  
  async getProductRecommendations(userId: string): Promise<any> {
    const response = await fetch(`${this.baseUrl}/products/recommend/${userId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    return response.json();
  }
}

export const agenticPlatform = new AgenticPlatformService();
```

## Advanced Testing Scenarios

### Test Real Data Flow

```bash
# If you have real Omnos data, test the complete flow:
USER_ID="your-real-user-id"

# 1. Sync real lab data
curl -X POST http://localhost:8080/omnos/sync/$USER_ID

# 2. Check if digital twin was updated
curl http://localhost:8080/health/ready

# 3. Generate personalized protocol
curl -X POST http://localhost:8080/protocol/generate/$USER_ID

# 4. Get product recommendations
curl -X POST http://localhost:8080/products/recommend/$USER_ID

# 5. Check agent activity
grep -A 5 -B 5 "twin.updated\|protocol.generated\|products.curated" platform.log
```

### Test Practitioner Features (B2B)

```bash
# List protocol reviews
curl http://localhost:8080/reviews

# Test WebSocket collaboration
# Use a WebSocket client or browser:
const ws = new WebSocket('ws://localhost:8080/ws/collab/practitioner-room-1');
```

## Monitoring Your Deployment

### View Real-time Logs

```bash
# Platform logs
tail -f platform.log

# Agent-specific activity
tail -f platform.log | grep "knowledge_graph_agent"

# Event bus activity  
tail -f platform.log | grep "Published event"

# Database activity
docker logs vitaex-timescaledb --tail=20
docker logs vitaex-neo4j --tail=20
```

### Kafka Monitoring

```bash
# Open Kafka UI in browser
open http://localhost:8081

# Or use command line:
docker exec vitaex-kafka kafka-topics --bootstrap-server localhost:9092 --list
docker exec vitaex-kafka kafka-console-consumer --bootstrap-server localhost:9092 --topic protocol.generated --from-beginning
```

## Next Steps After Local Testing

### 1. Performance Testing
- Test with realistic data volumes
- Monitor memory usage: `docker stats`
- Test concurrent users with your iOS app

### 2. Production Preparation
- Set up cloud provider (AWS/GCP/Azure)
- Configure domain and SSL certificates
- Set up managed databases and Kafka

### 3. iOS App Enhancement
- Add new agentic features to your iOS app
- Implement vitality simulation UI
- Add product recommendation display
- Test with your TestFlight users

### 4. B2B Platform Development
- Create practitioner dashboard UI
- Implement protocol review interface
- Test with partner practitioners/clinics

## Quick Verification Checklist

- [ ] All Docker containers running (`docker ps` shows 5-6 containers)
- [ ] Platform responds to health checks
- [ ] All 8 agents are running (`/health/ready`)
- [ ] Knowledge graph data imported
- [ ] Event bus topics created
- [ ] Your iOS app can access Spike endpoints (if testing)
- [ ] Logs show agent communication
- [ ] Protocol generation works
- [ ] Database connections stable

Your M2 Mac setup is ideal for this platform - the ARM architecture handles the containerized microservices very efficiently!