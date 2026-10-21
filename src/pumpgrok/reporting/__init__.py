"""Paper trading reports: daily and weekly ASCII markdown (paper-engine.md 8).

Rendering is pure: ``ReportModel`` is built from ledger rows and the renderer
has no I/O, so tests snapshot the markdown from a fixture ledger. Lamport
integers render as SOL with 9 decimals only at render time. Templates use
``str.format`` only (no jinja2, R9) and every byte is ASCII.
"""

from pumpgrok.reporting.daily import DailyReport
from pumpgrok.reporting.render import ReportModel, render_daily, render_weekly
from pumpgrok.reporting.weekly import WeeklyReport

__all__ = ["DailyReport", "ReportModel", "WeeklyReport", "render_daily", "render_weekly"]
