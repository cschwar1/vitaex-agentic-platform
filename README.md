VitaeX Agentic AI Platform

Overview
This repository implements a production-ready, modular, and privacy-first agentic AI platform for VitaeX. It builds on existing investments in the Health Knowledge Graph and the iOS app, introduces multi-agent patterns, and scales to B2C wellness and B2B practitioner collaboration.

Key Outcomes
- Multi-agent orchestration with clearly defined agents for ingestion, knowledge, personalization, simulations, compliance, and practitioner oversight.
- Event-driven microservices with Kafka for decoupling and scalability.
- Standards-based health data (FHIR/OMOP) and graph/vector/time-series databases.
- Privacy-preserving ML features: differential privacy, federated learning scaffolding, consent management, and audit logging.
- Cloud-native deployment on Kubernetes with service mesh, API gateway, and observability.
- Clear compliance guardrails to maximize functionality while avoiding medical device classification.

Repository Structure
- agents/: Agent base, orchestrator, and specific agent implementations.
- common/: Event bus (Kafka), privacy, persistence, mapping models (FHIR/OMOP), RAG.
- integrations/: Spike API, Omnos/Regenerus, media processing, and questionnaires.
- api/: FastAPI application that exposes APIs and WebSocket endpoints, and bootstraps agents.
- deployment/k8s/: Kubernetes manifests (namespace, deployments, services, Istio, gateway, monitoring).

Multi-Agent System
- Orchestrator: Central coordinator for agent lifecycles, task graphs, and event topology.
- Data Ingestion Agent: Standardizes data from Spike/wearables and labs (Omnos) into FHIR/OMOP; persists time-series; publishes events.
- Knowledge Graph Agent: Leverages existing health-knowledge-graph modules to extract entities/relationships from research; syncs to Neo4j; supports RAG.
- Digital Twin Agent: Maintains an N-of-1 twin per user from longitudinal data.
- Vitality Simulation Agent: What-if scenarios (sleep, exercise, diet, supplement changes) that estimate biomarker trends and vitality scores.
- Protocol Generator Agent: Produces personalized wellness protocols using RAG over knowledge graph + user data; guarded by compliance policies.
- Practitioner Oversight Agent: B2B workflows for review/approval, consensus validation, and real-time collaboration.
- Compliance Guardian Agent: Enforces regulatory safeguards, consent checks, audit logging, and content classification to avoid SaMD classification.

Data Architecture
- Standards: FHIR (Observation/Questionnaire/QuestionnaireResponse), OMOP CDM (measurement/observation).
- Event Streaming: Apache Kafka for decoupling; well-defined topics and schemas.
- Datastores:
  - Time-series: TimescaleDB (Postgres) for wearables and continuous signals.
  - Graph: Neo4j for the knowledge graph; integration with enhanced_entity_extractor and enhanced_import_system.
  - Vector: PGVector (in Postgres) for semantic search and RAG.
- Indexing and RAG: Hybrid retrieval across vector store and graph neighborhood.

Integrations
- Spike API (30+ wearables): Server-side HMAC auth, OAuth callback, data proxy endpoints compatible with vitaex-ios patterns.
- Omnos/Regenerus Labs: Token-based proxy, caching, and mapping to FHIR/OMOP.
- Media processing: Audio/video journaling to text via Whisper/OpenAI.
- Questionnaire processing: Map to FHIR QuestionnaireResponse and OMOP.

Privacy & Compliance
- Differential Privacy: Aggregation utilities for analytics and cohort stats with configurable epsilon/delta.
- Federated Learning: Aggregator and client scaffolding; secure aggregation placeholders.
- Consent Management: Purpose-based, time-bound, and scope-specific checks enforced before processing.
- Audit Logging: Structured logs with correlation IDs; OTEL tracing; append-only audit events.

Deployment & Scalability
- Kubernetes: Manifests for services, Kafka topics (via Strimzi), Postgres/Timescale, Neo4j, and gateway (Kong or Istio).
- Service Mesh: Istio mTLS and routing for inter-service security and policy control.
- Observability: OpenTelemetry instrumentation; Prometheus/Grafana compatibility.
- Horizontal scaling via stateless microservices and shared backing stores.

B2B Platform Features
- Practitioner dashboard APIs for reviewing and approving protocols.
- Consensus-based validation with configurable thresholds and quorum.
- Real-time collaboration via WebSockets.
- Granular audit trails on who approved what and when.

Compliance Boundaries (Non-Medical Device Posture)
- The system provides general wellness insights, behavioral suggestions, and protocol drafts that must be reviewed by a qualified practitioner before being presented as guidance.
- No diagnoses, treatment claims, or device-like closed-loop actions.
- Mandatory disclaimers on all protocol outputs.
- Practitioner Oversight and Compliance Guardian enforce gating and auditable controls.

Migration Path
- Phase 1: Use agents to enrich current iOS experiences (journaling, recommendations) with clear wellness boundaries. Start Kafka topics with minimal producers/consumers.
- Phase 2: Introduce practitioner review workflows; integrate Neo4j sync for knowledge graph queries; begin RAG for personalization.
- Phase 3: Expand to federated learning pilots; activate differential privacy analytics; productionize Istio and Kafka multi-cluster if needed.

Local Development
- Python 3.11 recommended.
- Install: pip install -r requirements.txt
- Run API: uvicorn api.service:app --reload
- Kafka: Use local Kafka (e.g., Docker) or Strimzi on a K8s dev cluster.
- Environment variables control DBs, Kafka brokers, and external API credentials.

Security Notes
- Put all secrets in environment variables or Kubernetes Secrets.
- Use mTLS (Istio) and OAuth2 for external integrations.
- Limit scopes and enforce consent on all processing paths.

References to Existing Components
- Health Knowledge Graph: This system imports and leverages enhanced_entity_extractor.py and enhanced_import_system.py to populate Neo4j and the vector store, and to provide explainable RAG context.
- iOS Integration: Server-side Spike endpoints mirror the vitaex-ios usage patterns (spike.ts and UnifiedDeviceConnect.tsx). The API is designed to slot under /api/spike to minimize client changes.
