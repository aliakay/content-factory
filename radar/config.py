"""Search profile, scoring weights and environment loading."""
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

ROOT = os.environ.get("CF_ROOT") or os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
DB_PATH = os.path.join(ROOT, "data", "radar.db")
REPORT_DIR = os.path.join(ROOT, "reports")

# Initial model weights (a starting point to calibrate, not a proven formula)
WEIGHTS = {
    "velocity": 0.30,      # age-adjusted view velocity, compared within age cohorts
    "outlier": 0.25,       # views vs the creator's median comparable short
    "engagement": 0.15,    # (likes + comments) / views
    "acceleration": 0.15,  # growth speed-up between stored snapshots
    "replication": 0.10,   # same sub-topic rising across independent creators
    "trend": 0.05,         # manually supplied topic-interest signal
}


@dataclass
class SearchProfile:
    name: str = "psychology"
    topic: str = "psychology facts"
    days: int = 30
    max_duration_s: float = 15.0          # strictly less than this
    region: str | None = None             # global market: no regionCode
    languages: tuple = ("en",)
    queries: tuple = (
        "psychology facts",
        "psychology facts shorts",
        "human behavior facts",
        "social psychology facts",
        "brain facts psychology",
        "body language psychology",
        "cognitive bias explained",
        "#psychologyfacts",
    )
    orders: tuple = ("relevance",)         # add "viewCount" / "date" for wider coverage
    extra_view_order_queries: tuple = ("psychology facts",)
    search_budget: int = 10                # search.list calls per run (100 quota units each)

    def window(self, now: datetime | None = None):
        """Rolling window ending at `now` (UTC) and starting exactly `days` earlier."""
        end = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
        return end - timedelta(days=self.days), end


def load_env(path=os.path.join(ROOT, ".env")):
    env = {}
    if os.path.exists(path):
        for line in open(path):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return {**env, **{k: v for k, v in os.environ.items() if k in env or k.endswith("_API_KEY")}}


# Named search profiles: one per content pillar. Each run tags its videos with the profile name.
PROFILES = {
    "psychology": SearchProfile(),
    "travel": SearchProfile(
        name="travel", topic="travel shorts", max_duration_s=60.0, search_budget=10,
        queries=("travel shorts", "hidden gems europe", "germany travel", "bavaria travel", "lake como",
                 "zugspitze", "travel facts", "places that don't look real", "2 days itinerary travel",
                 "travel vlog shorts"),
        extra_view_order_queries=()),
}


def get_profile(name):
    return PROFILES.get(name or "psychology", PROFILES["psychology"])
