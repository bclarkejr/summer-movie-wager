"""Detect drift between scraped picks and the season's locked-in snapshot."""

from pathlib import Path

import yaml

from summer_movie_wager.types import PlayerPicks


class PicksDriftError(RuntimeError):
    """Raised when scraped picks no longer match the persisted snapshot."""


def bootstrap_or_validate(
    scraped: dict[str, PlayerPicks],
    snapshot_path: Path,
) -> None:
    """If snapshot file exists, validate scraped picks match it. Otherwise persist scraped as new snapshot."""

    if not snapshot_path.exists():
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        _write(scraped, snapshot_path)
        return

    persisted = _read(snapshot_path)
    diffs: list[str] = []

    persisted_users = set(persisted.keys())
    scraped_users = set(scraped.keys())
    missing = persisted_users - scraped_users
    extra = scraped_users - persisted_users
    if missing:
        diffs.append(f"snapshot has players not in scrape: {sorted(missing)}")
    if extra:
        diffs.append(f"scrape has players not in snapshot: {sorted(extra)}")

    for user in persisted_users & scraped_users:
        if persisted[user].ranked != scraped[user].ranked:
            diffs.append(f"{user}: ranked picks changed")
        # Dark horses are unordered — each scores 1pt if it lands top-10, no positional weight.
        if sorted(persisted[user].dark_horses) != sorted(scraped[user].dark_horses):
            diffs.append(f"{user}: dark horses changed")

    if diffs:
        raise PicksDriftError(
            "Picks drift detected vs. picks_snapshot_2026.yaml:\n  - "
            + "\n  - ".join(diffs)
            + "\n\nIf the change is intentional, delete the snapshot file and re-run to "
            "rebootstrap. Otherwise, investigate the scraper or the source page."
        )


def _read(path: Path) -> dict[str, PlayerPicks]:
    raw = yaml.safe_load(path.read_text()) or {}
    return {
        username: PlayerPicks(
            username = username,
            ranked = entry["ranked"],
            dark_horses = entry["dark_horses"],
        )
        for username, entry in raw.items()
    }


def _write(picks: dict[str, PlayerPicks], path: Path) -> None:
    out = {
        username: {"ranked": p.ranked, "dark_horses": p.dark_horses}
        for username, p in picks.items()
    }
    path.write_text(yaml.safe_dump(out, sort_keys=True, allow_unicode=True))
