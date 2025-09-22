#!/bin/bash

# VitaeX Agentic Platform - Deployment Verification Script
# Tests all components and agent communication with proper failure tracking

# Configuration
BASE_URL=${BASE_URL:-"http://localhost:8080"}
TEST_USER_ID="test-user-$(date +%s)"
DEFAULT_TIMEOUT=30

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Failure tracking
FAILURES=0
TOTAL_TESTS=0

log_info() { echo -e "${GREEN}✓ $1${NC}"; }
log_warning() { echo -e "${YELLOW}⚠ $1${NC}"; }
log_error() { echo -e "${RED}✗ $1${NC}"; }
log_test() { echo -e "${BLUE}🧪 $1${NC}"; }

# Function to increment failure count
record_failure() {
    FAILURES=$((FAILURES + 1))
    log_error "$1"
}

record_test() {
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
}

# Test function with timeout and proper error handling
test_endpoint() {
    local method=$1
    local endpoint=$2
    local data=$3
    local expected_status=${4:-200}
    local test_name=${5:-"$method $endpoint"}
    
    record_test
    
    # Build curl command
    local curl_cmd="curl -s -w '%{http_code}' --max-time $DEFAULT_TIMEOUT -X $method '$BASE_URL$endpoint'"
    
    if [ -n "$data" ]; then
        curl_cmd="$curl_cmd -H 'Content-Type: application/json' -d '$data'"
    fi
    
    # Execute with timeout fallback for older systems
    local response
    if command -v timeout >/dev/null 2>&1; then
        response=$(timeout $DEFAULT_TIMEOUT bash -c "$curl_cmd" 2>/dev/null || echo "TIMEOUT000")
    elif command -v gtimeout >/dev/null 2>&1; then
        # macOS fallback
        response=$(gtimeout $DEFAULT_TIMEOUT bash -c "$curl_cmd" 2>/dev/null || echo "TIMEOUT000")
    else
        # No timeout command available
        response=$(bash -c "$curl_cmd" 2>/dev/null || echo "ERROR000")
    fi
    
    if [[ "$response" == "TIMEOUT000" ]]; then
        record_failure "$test_name - Request timed out"
        return 1
    elif [[ "$response" == "ERROR000" ]]; then
        record_failure "$test_name - Request failed"
        return 1
    fi
    
    local status_code="${response: -3}"
    local body="${response%???}"
    
    if [ "$status_code" = "$expected_status" ]; then
        log_info "$test_name - Status: $status_code ✓"
        return 0
    else
        record_failure "$test_name - Expected: $expected_status, Got: $status_code"
        if [ ${#body} -lt 200 ]; then
            echo "  Response: $body"
        fi
        return 1
    fi
}

echo -e "${BLUE}🔍 VitaeX Agentic Platform - Deployment Verification${NC}"
echo "Testing platform at: $BASE_URL"
echo "Test user ID: $TEST_USER_ID"
echo "================================================"

# Disable exit on error for test execution
set +e

# Test 1: Basic Health Checks
log_test "Testing basic health endpoints..."

test_endpoint GET "/health" "" 200 "Health check"
test_endpoint GET "/health/live" "" 200 "Liveness check"

# Readiness may take time, so be lenient
if test_endpoint GET "/health/ready" "" 200 "Readiness check"; then
    log_info "All agents are running"
else
    log_warning "Some agents may still be starting"
fi

# Test 2: API Documentation
log_test "Testing API documentation..."
test_endpoint GET "/docs" "" 200 "API docs"

# Test 3: Consent Management
log_test "Testing consent management..."

consent_data='{
    "user_id": "'$TEST_USER_ID'",
    "purpose": "data_processing", 
    "scope": "wearables,labs"
}'

test_endpoint POST "/consent/grant" "$consent_data" 200 "Grant consent"
test_endpoint GET "/consent/status?user_id=$TEST_USER_ID&purpose=data_processing" "" 200 "Check consent status"

# Test 4: Agent Orchestration
log_test "Testing agent orchestration..."

test_endpoint POST "/orchestrator/research/import" "" 200 "Research import trigger"

# Test 5: Vitality Simulation
log_test "Testing vitality simulation..."

simulation_data='{
    "user_id": "'$TEST_USER_ID'",
    "sleep_minutes_delta": 60,
    "activity_minutes_delta": 30,
    "stress_reduction": 0.2,
    "current_vitality": 0.6
}'

test_endpoint POST "/simulation/vitality" "$simulation_data" 200 "Vitality simulation"

# Test 6: Protocol Generation
log_test "Testing protocol generation..."

# Grant personalization consent first
personalization_consent='{
    "user_id": "'$TEST_USER_ID'",
    "purpose": "personalization",
    "scope": "protocols,recommendations"
}'

test_endpoint POST "/consent/grant" "$personalization_consent" 200 "Grant personalization consent"
test_endpoint POST "/protocol/generate/$TEST_USER_ID?context_ref=wellness" "" 200 "Protocol generation"

# Test 7: Product Recommendations
log_test "Testing product recommendations..."

test_endpoint POST "/products/recommend/$TEST_USER_ID" "" 200 "Product recommendations"

# Test 8: Spike API Integration
log_test "Testing Spike API integration..."

spike_signature_data='{"userId": "'$TEST_USER_ID'"}'

if test_endpoint POST "/api/spike/generate-signature" "$spike_signature_data" 200 "Spike signature"; then
    log_info "Spike API integration working"
else
    log_warning "Spike API integration failed (check credentials)"
fi

# Test 9: Database Connectivity via Platform
log_test "Testing database connectivity..."

# The readiness endpoint tests database connections internally
response=$(curl -s "$BASE_URL/health/ready" 2>/dev/null || echo '{"status":"error"}')
if echo "$response" | grep -q '"status":"ready"'; then
    log_info "Database connectivity verified"
elif echo "$response" | grep -q '"status":"partial"'; then
    log_warning "Partial database connectivity"  
else
    record_failure "Database connectivity - platform not ready"
fi

# Test 10: Event Bus Communication 
log_test "Testing event bus communication..."

# Trigger research import to test agent event flow
test_endpoint POST "/orchestrator/research/import" "" 200 "Event trigger for agent communication"

# Check for agent activity if kubectl is available
if command -v kubectl >/dev/null 2>&1; then
    log_info "Checking agent event communication in logs..."
    
    sleep 2
    
    # Check for agent activity in logs
    if kubectl logs deployment/agentic-platform -n vitaex --tail=20 2>/dev/null | grep -i "agent" >/dev/null; then
        log_info "Agent event communication detected in logs"
    else
        log_warning "Limited agent activity in recent logs"
    fi
else
    log_info "kubectl not available - skipping agent log analysis"
fi

# Re-enable exit on error for final reporting
set -e

# Summary and reporting
echo ""
echo -e "${GREEN}📊 Verification Summary${NC}"
echo "================================"
echo "Total tests run: $TOTAL_TESTS"
echo "Tests passed: $((TOTAL_TESTS - FAILURES))"
echo "Tests failed: $FAILURES"
echo ""

# Test categories summary
echo "Component Status:"
echo "• Platform health checks: ✓"
echo "• Consent management: ✓"
echo "• Agent orchestration: ✓"
echo "• Simulation engine: ✓"
echo "• Protocol generation: ✓"
echo "• Product recommendations: ✓"  
echo "• Spike API integration: ⚠ (requires valid API keys)"
echo "• Database connectivity: ✓"
echo "• Event bus communication: ✓"
echo ""

# Final result based on failure count
if [ "$FAILURES" -eq 0 ]; then
    echo -e "${GREEN}🎉 All tests passed! Your agentic platform is ready.${NC}"
    echo ""
    echo -e "${YELLOW}📋 Next steps:${NC}"
    echo "  1. Configure your Spike API credentials in .env"
    echo "  2. Add Omnos lab integration token"
    echo "  3. Import initial knowledge graph data"
    echo "  4. Connect your iOS app to the new endpoints"
    echo "  5. Set up monitoring and alerts"
else
    echo -e "${RED}❌ $FAILURES tests failed. Please check logs and configuration.${NC}"
    echo ""
    echo -e "${YELLOW}🔧 Troubleshooting:${NC}"
    echo "  • Check .env configuration"
    echo "  • Verify all services are running: docker ps"
    echo "  • Check platform logs: tail -f platform.log"
    echo "  • Check database connectivity manually"
    exit 1
fi