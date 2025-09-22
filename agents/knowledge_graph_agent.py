import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger

from agents.base import BaseAgent, AgentConfig
from common.event_bus import Event
from common.persistence.graph_client import GraphClient

# Ensure we can import modules from the existing health-knowledge-graph directory
HG_DIR = Path(__file__).resolve().parents[2] / "health-knowledge-graph"
if str(HG_DIR) not in sys.path:
    sys.path.append(str(HG_DIR))

# Import existing modules
from enhanced_entity_extractor import EnhancedEntityExtractor
from enhanced_import_system import EnhancedGraphBuilder, EnhancedPubMedFetcher, EnhancedClinicalTrialsFetcher, ImportConfig, DownloadTracker, load_search_terms  # type: ignore


JsonDict = Dict[str, Any]


class KnowledgeGraphAgent(BaseAgent):
    def __init__(self, bus):
        super().__init__(AgentConfig(
            name="knowledge_graph_agent",
            subscribe_topics=[
                "knowledge.research.import.requested"
            ]
        ), bus)
        self._graph_client = GraphClient()

    async def handle(self, event: Event) -> None:
        if event.topic == "knowledge.research.import.requested":
            await self._import_research_and_sync(correlation_id=event.correlation_id)

    async def _import_research_and_sync(self, correlation_id: Optional[str]) -> None:
        logger.info("Starting research import")
        # Load config and tracker from existing system
        config = ImportConfig.from_yaml()
        tracker = DownloadTracker() if config.enable_tracking else None
        extractor = EnhancedEntityExtractor()
        graph_builder = EnhancedGraphBuilder()

        # Pull search terms
        pubmed_terms, ct_params = load_search_terms()

        # Load email
        try:
            with open("config/config.yaml", "r") as f:
                email = json.load(f).get("data_sources", {}).get("pubmed", {}).get("email", "demo@example.com")
        except Exception:
            email = "demo@example.com"

        all_studies = []
        # PubMed
        if config.enable_pubmed:
            pubmed_fetcher = EnhancedPubMedFetcher(email, config, tracker)
            for query in pubmed_terms:
                pmids = pubmed_fetcher.search_with_progress(query, config.pubmed_max_per_query)
                if pmids:
                    articles = pubmed_fetcher.fetch_articles_with_progress(pmids, query)
                    all_studies.extend(articles)
        # ClinicalTrials
        if config.enable_clinicaltrials:
            ct_fetcher = EnhancedClinicalTrialsFetcher(config, tracker)
            for params in ct_params:
                studies = ct_fetcher.search_with_progress(params, config.clinicaltrials_max_per_query)
                if studies:
                    trials = ct_fetcher.parse_studies_with_progress(studies, str(params))
                    all_studies.extend(trials)

        # Build graph data
        graph_data = graph_builder.process_studies_with_progress(all_studies, extractor)

        # Persist to Neo4j
        self._graph_client.sync_graph(graph_data)

        # Publish update
        await self.publish(
            topic="knowledge.research.import.completed",
            event_type="research.import.completed",
            payload={"graph_version": graph_data["metadata"]["generated_at"], "counts": graph_data["metadata"]["entity_counts"]},
            correlation_id=correlation_id
        )