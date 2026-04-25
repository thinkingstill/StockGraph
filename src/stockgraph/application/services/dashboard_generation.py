from pathlib import Path

from stockgraph.core.paths import OUTPUT_HTML_DIR, ensure_runtime_dirs
from stockgraph.domain.dragon_tiger import FAMOUS_TRADERS
from stockgraph.infrastructure.db import DragonTigerRepository
from stockgraph.presentation.templates import render_comprehensive_dashboard, render_query_dashboard


class DashboardGenerationService:
    def __init__(self, repository: DragonTigerRepository | None = None) -> None:
        self.repository = repository or DragonTigerRepository()

    def generate(self) -> list[Path]:
        ensure_runtime_dirs()
        self.repository.initialize_database()
        dates = self.repository.list_trade_dates()
        if not dates:
            return []

        latest_date = dates[0]
        query_html = render_query_dashboard(
            latest_date=latest_date,
            date_list=dates,
            all_operations=self.repository.export_query_dataset(),
            all_active_stocks={date: self.repository.aggregate_active_stocks(date) for date in dates},
            all_active_seats={date: self.repository.aggregate_active_seats(date) for date in dates},
            all_famous_traders={date: self.repository.aggregate_famous_traders(date) for date in dates},
        )
        comprehensive_html = render_comprehensive_dashboard(
            data=self.repository.export_operations(),
            famous_traders=FAMOUS_TRADERS,
        )

        outputs = [
            self._write_html("龙虎榜查询.html", query_html),
            self._write_html("龙虎榜综合分析.html", comprehensive_html),
        ]
        return outputs

    @staticmethod
    def _write_html(filename: str, content: str) -> Path:
        path = OUTPUT_HTML_DIR / filename
        path.write_text(content, encoding="utf-8")
        return path
