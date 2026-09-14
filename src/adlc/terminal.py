from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text

from adlc.report import CONTROL_LINE, confounder_intro, coverage_line, footer_lines, table_rows

TIER_STYLES = {
    "elite": "bold green",
    "good": "bold cyan",
    "fair": "bold yellow",
    "needs focus": "bold red",
}


def band_cell(band: str, tier: str | None) -> Text:
    if tier is None:
        return Text(band, style="dim")
    text = Text(band)
    text.stylize(TIER_STYLES[tier], 0, len(tier))
    return text


def metrics_table(baseline: dict) -> Table:
    table = Table(box=box.SIMPLE_HEAD, show_edge=False, pad_edge=False, expand=False, header_style="bold")
    table.add_column("Metric", min_width=44)
    table.add_column("Value", justify="right", no_wrap=True, style="bold")
    table.add_column("Band, LinearB 2026 p75", min_width=30)
    for row in table_rows(baseline):
        table.add_row(row.metric, row.value, band_cell(row.band, row.tier))
    return table


def bullets(items: list[str], style: str = "") -> Table:
    grid = Table.grid(padding=(0, 1))
    grid.add_column(width=3, justify="right", style="bold")
    grid.add_column(style=style)
    for item in items:
        grid.add_row("•", item)
    return grid


def section(console: Console, title: str, style: str = "") -> None:
    console.print()
    console.print(Text(title, style=f"bold {style}".strip()))


def render(baseline: dict, console: Console) -> None:
    console.rule(Text(f"Delivery baseline for {baseline['repo']}", style="bold"), align="left")
    console.print(coverage_line(baseline), style="dim")
    console.print(metrics_table(baseline))
    if baseline.get("findings"):
        section(console, "What stands out")
        console.print(bullets([finding["text"] for finding in baseline["findings"]]))
        section(console, "Caveats", "dim")
        console.print(Text(confounder_intro(baseline), style="dim"))
        console.print(bullets(list(baseline["confounders"]), style="dim"))
        console.print(Text(CONTROL_LINE, style="dim"))
    if baseline.get("assumptions"):
        section(console, "What this report assumes", "dim")
        console.print(bullets(list(baseline["assumptions"]), style="dim"))
    console.print()
    for line in footer_lines(baseline):
        console.print(line, style="dim")
