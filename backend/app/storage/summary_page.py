"""A plain HTML rendering of the event summary.

No framework, no client JS, no styling ambition. This is an operator surface
read on a phone, and every dependency it grew would be a dependency that could
break the one page you look at when you want to know whether anyone used the
thing. The dark palette matches the product only so it isn't jarring.

Everything interpolated here is either a number this module computed or an
event name from `ALLOWED_EVENT_NAMES`, but it is HTML-escaped anyway --
depending on an upstream allowlist to keep an output encoder honest is exactly
how injection bugs survive a refactor.
"""

from __future__ import annotations

from html import escape


def _percent(rate: float | None) -> str:
    return "—" if rate is None else f"{rate * 100:.1f}%"


def render_events_summary(summary: dict) -> str:
    totals: dict = summary.get("totals") or {}
    daily: list = summary.get("daily") or []

    headline_rows = "".join(
        f"<tr><th>{escape(label)}</th><td>{escape(str(value))}</td></tr>"
        for label, value in (
            ("Backtests completed", summary.get("total_backtests_completed", 0)),
            ("Gate shown", summary.get("gate_shown", 0)),
            ("Gate confirmed", summary.get("gate_confirmed", 0)),
            ("Gate abandoned", summary.get("gate_abandoned", 0)),
            ("Gate confirm rate", _percent(summary.get("gate_confirm_rate"))),
            ("Total events", summary.get("total_events", 0)),
        )
    )

    total_rows = "".join(
        f"<tr><th>{escape(str(name))}</th><td>{escape(str(count))}</td></tr>"
        for name, count in totals.items()
    ) or '<tr><td colspan="2">No events recorded yet.</td></tr>'

    names = sorted({name for day in daily for name in (day.get("counts") or {})})
    daily_head = "".join(f"<th>{escape(n)}</th>" for n in names)
    daily_body = "".join(
        "<tr><th>"
        + escape(str(day.get("day", "")))
        + "</th>"
        + "".join(f"<td>{escape(str((day.get('counts') or {}).get(n, 0)))}</td>" for n in names)
        + "</tr>"
        for day in daily
    ) or f'<tr><td colspan="{len(names) + 1}">Nothing in this window.</td></tr>'

    storage_note = (
        ""
        if summary.get("storage_enabled")
        else "<p class='warn'>Event storage is disabled — no writable data directory. "
        "Counts are not being recorded.</p>"
    )

    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Deflate — events</title>
<style>
  body {{ background:#0a0a0a; color:#ededed; font:14px/1.5 ui-monospace, monospace;
         margin:0; padding:1.5rem; }}
  h1 {{ font-size:1.1rem; margin:0 0 .25rem; }}
  p.meta {{ color:#8f8f8f; margin:0 0 1.5rem; }}
  p.warn {{ color:#ededed; border:1px solid #444; padding:.75rem; }}
  h2 {{ font-size:.75rem; text-transform:uppercase; letter-spacing:.08em;
        color:#8f8f8f; margin:2rem 0 .5rem; }}
  table {{ border-collapse:collapse; width:100%; max-width:46rem; }}
  th, td {{ text-align:left; padding:.4rem .6rem; border-bottom:1px solid #262626;
            white-space:nowrap; }}
  th {{ font-weight:600; }}
  td {{ text-align:right; }}
  .scroll {{ overflow-x:auto; }}
</style>
</head><body>
<h1>Deflate — events</h1>
<p class="meta">Aggregate counts. No IPs, no user agents, no strategy text.</p>
{storage_note}
<h2>Headline</h2>
<table>{headline_rows}</table>
<h2>Totals by event</h2>
<table>{total_rows}</table>
<h2>Last {escape(str(summary.get("days", 0)))} days</h2>
<div class="scroll"><table>
<tr><th>day</th>{daily_head}</tr>
{daily_body}
</table></div>
</body></html>"""
