"""Load config/rules.toml (R1-R7). See docs/PP_rules_and_pilot.md for sources."""

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATH = Path("config/rules.toml")


def norm_chain_key(name):
    """Match osm_match.norm/chain_key: lowercase, apostrophes dropped, one space."""
    s = (name or "").lower().replace("&", " and ").replace("'", "")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


@dataclass
class Rules:
    r1_category_defaults: dict
    r3_own_brand_names: set
    r6_chains: dict                  # normalised chain key -> {who_can_park?, cost_type?, operator?}
    r7_free_requires_access: set
    r7_risky_cost_types: set
    r7_risky_who_can_park: set

    def is_own_brand_operator(self, operator_tag):
        return norm_chain_key(operator_tag) in self.r3_own_brand_names

    def chain_for(self, location_name):
        """The R6 chain rule for a location's first word(s), or None."""
        words = norm_chain_key(location_name).split()
        for n in (2, 1):
            key = " ".join(words[:n])
            if key in self.r6_chains:
                return self.r6_chains[key]
        return None


def load_rules(path=DEFAULT_PATH):
    with open(path, "rb") as f:
        data = tomllib.load(f)
    chains = {norm_chain_key(k): v for k, v in data.get("r6", {}).get("chains", {}).items()}
    return Rules(
        r1_category_defaults=data["r1_category_defaults"],
        r3_own_brand_names={norm_chain_key(n) for n in data["r3_own_brand_operators"]["names"]},
        r6_chains=chains,
        r7_free_requires_access=set(data["r7"]["free_requires_access"]),
        r7_risky_cost_types=set(data["r7"]["risky_cost_types"]),
        r7_risky_who_can_park=set(data["r7"]["risky_who_can_park"]),
    )
