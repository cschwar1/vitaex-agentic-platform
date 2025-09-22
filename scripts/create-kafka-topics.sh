#!/bin/bash

# Create Kafka topics for VitaeX Agentic AI Platform
# Run this script after Kafka cluster is up and running

set -e

KAFKA_BROKER=${KAFKA_BROKER:-"localhost:9092"}
PARTITIONS=${PARTITIONS:-6}
REPLICATION=${REPLICATION:-1}

echo "Creating Kafka topics for VitaeX Agentic Platform..."
echo "Kafka broker: $KAFKA_BROKER"
echo "Default partitions: $PARTITIONS, replication: $REPLICATION"

# Function to create topic with error handling
create_topic() {
    local topic_name=$1
    local custom_partitions=${2:-$PARTITIONS}
    local custom_replication=${3:-$REPLICATION}
    
    echo "Creating topic: $topic_name"
    
    if kafka-topics --bootstrap-server $KAFKA_BROKER --list | grep -q "^${topic_name}$"; then
        echo "  ✓ Topic $topic_name already exists"
    else
        kafka-topics --bootstrap-server $KAFKA_BROKER \
            --create \
            --topic $topic_name \
            --partitions $custom_partitions \
            --replication-factor $custom_replication \
            --config retention.ms=604800000 \
            --config segment.ms=86400000
        echo "  ✓ Created topic: $topic_name"
    fi
}

# Wait for Kafka to be ready
echo "Waiting for Kafka to be ready..."
timeout=60
while ! kafka-topics --bootstrap-server $KAFKA_BROKER --list >/dev/null 2>&1; do
    sleep 2
    timeout=$((timeout-2))
    if [ $timeout -le 0 ]; then
        echo "❌ Kafka not ready after 60 seconds"
        exit 1
    fi
done
echo "✓ Kafka is ready"

# Data Ingestion Topics (high throughput)
create_topic "ingest.wearables.raw" 8
create_topic "ingest.wearables.standardized" 8
create_topic "ingest.labs.raw" 4
create_topic "ingest.labs.standardized" 4
create_topic "ingest.questionnaire.standardized" 2

# Knowledge Graph Topics (low throughput)
create_topic "knowledge.research.import.requested" 2
create_topic "knowledge.research.import.completed" 2
create_topic "knowledge.graph.updated" 2

# Digital Twin Topics (medium throughput)
create_topic "user.twin.update.requested" 6
create_topic "user.twin.updated" 6

# Simulation Topics (medium throughput)
create_topic "simulation.vitality.requested" 4
create_topic "simulation.vitality.completed" 4

# Protocol Topics (medium throughput)
create_topic "protocol.generate.requested" 4
create_topic "protocol.generated" 4
create_topic "protocol.review.requested" 2
create_topic "protocol.review.updated" 2

# Product Recommendation Topics
create_topic "product.recommendation.requested" 2
create_topic "product.recommendations" 2

# Compliance and Audit Topics
create_topic "compliance.alert" 2
create_topic "audit.events" 4

echo ""
echo "✅ All Kafka topics created successfully!"
echo ""
echo "📋 Topic Summary:"
kafka-topics --bootstrap-server $KAFKA_BROKER --list | sort

echo ""
echo "🔧 To verify topic details:"
echo "kafka-topics --bootstrap-server $KAFKA_BROKER --describe --topic [topic-name]"