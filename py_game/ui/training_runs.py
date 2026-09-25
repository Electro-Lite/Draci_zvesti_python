"""Filtering, sorting, and pagination for the training run library."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from math import ceil

from py_game.training_service import (
    TrainingJob,
    TrainingKind,
    TrainingRunSummary,
    TrainingService,
)


RunItem = TrainingJob | TrainingRunSummary
SORT_FIELDS = ("Date", "Name", "Status", "Mission")
STATUS_FILTERS = ("All statuses", "Running", "Completed", "Needs attention")
MISSION_FILTERS = (
    "All missions",
    "Counter-deck training",
    "Matchup evaluation",
    "General deck evolution",
)
ORIGIN_FILTERS = ("All origins", "UI-launched runs", "Database history")
STARTED_FILTERS = ("Any time", "Last 24 hours", "Last 7 days", "Last 30 days")
GENERATION_FILTERS = (
    "Any generation count",
    "10+ generations",
    "25+ generations",
    "40+ generations",
    "65+ generations",
)
ATTENTION_STATUSES = {"failed", "interrupted", "incomplete", "cancelled"}


@dataclass(frozen=True)
class RunFilters:
    status: str = STATUS_FILTERS[0]
    mission: str = MISSION_FILTERS[0]
    origin: str = ORIGIN_FILTERS[0]
    started: str = STARTED_FILTERS[0]
    generations: str = GENERATION_FILTERS[0]

    @property
    def active_count(self) -> int:
        return sum(
            (
                self.status != STATUS_FILTERS[0],
                self.mission != MISSION_FILTERS[0],
                self.origin != ORIGIN_FILTERS[0],
                self.started != STARTED_FILTERS[0],
                self.generations != GENERATION_FILTERS[0],
            )
        )


def run_id(item: RunItem) -> str:
    return item.run_id if isinstance(item, TrainingRunSummary) else item.job_id


def run_title(item: RunItem) -> str:
    if isinstance(item, TrainingRunSummary):
        return item.title
    return str((item.request or {}).get("run_label") or item.job_id)


def run_status(item: RunItem) -> str:
    return str(item.status or "unknown").lower()


def run_started(item: RunItem) -> str:
    return str(item.started if isinstance(item, TrainingRunSummary) else item.created_at)


def run_kind(item: RunItem) -> str:
    if isinstance(item, TrainingRunSummary):
        return item.run_kind
    return str((item.request or {}).get("kind") or "")


def run_mission(item: RunItem) -> str:
    return (
        "Counter-deck training"
        if run_kind(item) == TrainingKind.PLAYER_DECK.value
        else "Matchup evaluation"
        if run_kind(item) == TrainingKind.MATCHUP_EVALUATION.value
        else "General deck evolution"
        if run_kind(item) == TrainingKind.DECK_BUILDER.value
        else "AI training"
    )


def run_origin(item: RunItem) -> str:
    return "Database history" if isinstance(item, TrainingRunSummary) else "UI-launched runs"


def run_generations(item: RunItem) -> int:
    if isinstance(item, TrainingRunSummary):
        return int(item.generation or 0)
    request = item.request or {}
    key = (
        "outer_generations"
        if run_kind(item)
        in {TrainingKind.DECK_BUILDER.value, TrainingKind.PLAYER_DECK.value}
        and request.get("outer_generations") is not None
        else "evaluator_generations"
    )
    return int(request.get(key, 0) or 0)


def _started_datetime(item: RunItem) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(run_started(item).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def combined_runs(
    service: TrainingService,
    jobs: list[TrainingJob],
    database_runs: list[TrainingRunSummary],
    linked_database_ids: set[str] | None = None,
) -> list[RunItem]:
    """Merge UI and database records without showing one experiment twice."""
    if linked_database_ids is None:
        linked_database_ids = set()
        for job in jobs:
            database_id = service.job_database_run_id(job)
            if database_id is not None:
                linked_database_ids.add(f"DB {database_id}")
    return [*jobs, *(run for run in database_runs if run.run_id not in linked_database_ids)]


def query_runs(
    items: list[RunItem],
    *,
    search: str = "",
    sort_field: str = SORT_FIELDS[0],
    descending: bool = True,
    filters: RunFilters = RunFilters(),
    now: dt.datetime | None = None,
) -> list[RunItem]:
    needle = search.strip().casefold()
    now = now or dt.datetime.now()

    def included(item: RunItem) -> bool:
        status = run_status(item)
        if filters.status == "Running" and status != "running":
            return False
        if filters.status == "Completed" and status != "completed":
            return False
        if filters.status == "Needs attention" and status not in ATTENTION_STATUSES:
            return False
        mission = run_mission(item)
        if filters.mission != MISSION_FILTERS[0] and mission != filters.mission:
            return False
        if filters.origin != ORIGIN_FILTERS[0] and run_origin(item) != filters.origin:
            return False
        if filters.started != STARTED_FILTERS[0]:
            started = _started_datetime(item)
            if started is None:
                return False
            comparison_now = now
            if started.tzinfo is not None and comparison_now.tzinfo is None:
                comparison_now = comparison_now.replace(tzinfo=started.tzinfo)
            elif started.tzinfo is None and comparison_now.tzinfo is not None:
                started = started.replace(tzinfo=comparison_now.tzinfo)
            days = {"Last 24 hours": 1, "Last 7 days": 7, "Last 30 days": 30}[
                filters.started
            ]
            if not comparison_now - dt.timedelta(days=days) <= started <= comparison_now:
                return False
        if filters.generations != GENERATION_FILTERS[0]:
            minimum = int(filters.generations.split("+", 1)[0])
            if run_generations(item) < minimum:
                return False
        return not needle or needle in run_title(item).casefold()

    sorters = {
        "Date": run_started,
        "Name": lambda item: run_title(item).casefold(),
        "Status": lambda item: (run_status(item), run_started(item)),
        "Mission": lambda item: (run_mission(item), run_started(item)),
    }
    return sorted(
        (item for item in items if included(item)),
        key=sorters.get(sort_field, run_started),
        reverse=descending,
    )


def paginate_runs(
    items: list[RunItem],
    page: int,
    page_size: int = 10,
) -> tuple[list[RunItem], int, int]:
    page_count = max(1, ceil(len(items) / page_size))
    page = max(0, min(page, page_count - 1))
    start = page * page_size
    return items[start : start + page_size], page, page_count
