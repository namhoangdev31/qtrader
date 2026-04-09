from __future__ import annotations

import base64
import io
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl

try:
    import matplotlib.pyplot as plt

    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

log = logging.getLogger("qtrader.research.report")


@dataclass
class _Section:
    title: str
    content_html: str


class ReportBuilder:
    _CSS = (
        "<style>\n"
        "body { font-family: Inter, system-ui, sans-serif; margin: 0; padding: 32px; "
        "background: #0f1117; color: #e2e8f0; }\n"
        "h1 { color: #7dd3fc; border-bottom: 2px solid #1e40af; padding-bottom: 8px; }\n"
        "h2 { color: #a5f3fc; margin-top: 40px; }\n"
        "h3 { color: #94a3b8; }\n"
        "table { border-collapse: collapse; width: 100%; margin: 16px 0; "
        "border-radius: 8px; overflow: hidden; }\n"
        "th { background: #1e3a5f; color: #bae6fd; padding: 10px 14px; "
        "text-align: left; font-size: 13px; }\n"
        "td { padding: 9px 14px; border-bottom: 1px solid #1e293b; "
        "font-size: 13px; color: #cbd5e1; }\n"
        "tr:hover td { background: #1e293b; }\n"
        "img { max-width: 100%; border-radius: 8px; margin: 12px 0; "
        "border: 1px solid #334155; }\n"
        ".section { margin-bottom: 40px; }\n"
        ".meta { font-size: 12px; color: #64748b; margin-top: -4px; "
        "margin-bottom: 24px; }\n"
        "</style>"
    )

    def __init__(self, title: str) -> None:
        self.title = title
        self._sections: list[_Section] = []

    def add_text(self, heading: str, body: str) -> ReportBuilder:
        html = f"<h2>{heading}</h2><p>{body}</p>"
        self._sections.append(_Section(heading, html))
        return self

    def add_table(self, heading: str, df: pl.DataFrame | dict[str, Any]) -> ReportBuilder:
        if isinstance(df, dict):
            df = pl.DataFrame(
                {
                    "Metric": list(df.keys()),
                    "Value": [f"{v:.4f}" if isinstance(v, float) else str(v) for v in df.values()],
                }
            )
        html = self._df_to_html_table(df)
        self._sections.append(_Section(heading, f"<h2>{heading}</h2>{html}"))
        return self

    def add_figure(self, heading: str, fig: Any) -> ReportBuilder:
        if not HAS_MATPLOTLIB:
            log.warning("matplotlib not installed - skipping figure '%s'", heading)
            return self
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", dpi=150, facecolor="#0f1117")
        buf.seek(0)
        b64 = base64.b64encode(buf.read()).decode()
        html = f'<h2>{heading}</h2><img src="data:image/png;base64,{b64}" alt="{heading}" />'
        self._sections.append(_Section(heading, html))
        return self

    def add_polars_plot(self, heading: str, series: pl.Series) -> ReportBuilder:
        if not HAS_MATPLOTLIB:
            log.warning("matplotlib not installed - skipping plot '%s'", heading)
            return self
        (fig, ax) = plt.subplots(figsize=(10, 4))
        ax.plot(series.to_numpy(), linewidth=1.5, color="#38bdf8")
        ax.set_facecolor("#0f1117")
        fig.patch.set_facecolor("#0f1117")
        ax.tick_params(colors="#94a3b8")
        ax.spines["bottom"].set_color("#334155")
        ax.spines["left"].set_color("#334155")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.grid(color="#1e293b", linestyle="--", linewidth=0.5)
        self.add_figure(heading, fig)
        plt.close(fig)
        return self

    def build_html(self) -> str:
        body = "\n".join(f'<div class="section">{s.content_html}</div>' for s in self._sections)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{self.title}</title>
  {self._CSS}
</head>
<body>
  <h1>{self.title}</h1>
  <p class="meta">Generated: {ts} | QTrader Analyst Platform</p>
  {body}
</body>
</html>"""

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        html = self.build_html()
        p.write_text(html, encoding="utf-8")
        log.info("Report saved → %s", p)
        return p

    @staticmethod
    def _df_to_html_table(df: pl.DataFrame) -> str:
        headers = "".join(f"<th>{c}</th>" for c in df.columns)
        rows = ""
        for row in df.iter_rows():
            cells = "".join(f"<td>{v}</td>" for v in row)
            rows += f"<tr>{cells}</tr>"
        return f"<table><thead><tr>{headers}</tr></thead><tbody>{rows}</tbody></table>"
