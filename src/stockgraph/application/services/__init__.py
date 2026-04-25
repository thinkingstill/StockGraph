__all__ = [
    "DashboardGenerationService",
    "DragonTigerIngestionService",
    "MarketOverviewService",
    "NetworkAnalysisService",
    "NewsIngestionService",
    "UnifiedFrontendService",
]


def __getattr__(name: str):
    if name == "DashboardGenerationService":
        from .dashboard_generation import DashboardGenerationService

        return DashboardGenerationService
    if name == "DragonTigerIngestionService":
        from .dragon_tiger_ingestion import DragonTigerIngestionService

        return DragonTigerIngestionService
    if name == "MarketOverviewService":
        from .market_overview import MarketOverviewService

        return MarketOverviewService
    if name == "NetworkAnalysisService":
        from .network_analysis import NetworkAnalysisService

        return NetworkAnalysisService
    if name == "NewsIngestionService":
        from .news_ingestion import NewsIngestionService

        return NewsIngestionService
    if name == "UnifiedFrontendService":
        from .unified_frontend import UnifiedFrontendService

        return UnifiedFrontendService
    raise AttributeError(name)
