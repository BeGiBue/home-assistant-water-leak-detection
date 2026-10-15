"""Tests for the version-controlled GitHub Wiki source."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WIKI = ROOT / "docs" / "wiki"

REQUIRED_PAGES = {
    "Home.md",
    "Projektueberblick.md",
    "Architektur.md",
    "Installation-und-Konfiguration.md",
    "Leckageklassen-und-Erkennungslogik.md",
    "Alarmstufen-und-Quittierung.md",
    "Water-Shut-Off.md",
    "Adaptives-Lernen-und-Hydraulik.md",
    "Home-Assistant-Schnittstellen.md",
    "Persistenz-und-Betrieb.md",
    "Troubleshooting.md",
    "Entwicklung-und-Release.md",
    "Designentscheidungen.md",
    "_Sidebar.md",
    "_Footer.md",
}


def test_required_wiki_pages_exist() -> None:
    existing = {path.name for path in WIKI.glob("*.md")}
    assert existing >= REQUIRED_PAGES


def test_internal_wiki_links_point_to_existing_pages() -> None:
    existing_stems = {path.stem for path in WIKI.glob("*.md")}
    link_pattern = re.compile(r"\[[^]]+\]\(([^)]+)\)")

    missing: list[tuple[str, str]] = []
    for page in WIKI.glob("*.md"):
        content = page.read_text(encoding="utf-8")
        for target in link_pattern.findall(content):
            if (
                "://" in target
                or target.startswith("#")
                or target.endswith(".md")
            ):
                continue
            target_page = target.split("#", 1)[0]
            if target_page and target_page not in existing_stems:
                missing.append((page.name, target_page))

    assert missing == []


def test_five_core_project_topics_are_documented() -> None:
    detection = (WIKI / "Leckageklassen-und-Erkennungslogik.md").read_text(
        encoding="utf-8"
    )
    alarms = (WIKI / "Alarmstufen-und-Quittierung.md").read_text(
        encoding="utf-8"
    )
    shutoff = (WIKI / "Water-Shut-Off.md").read_text(encoding="utf-8")
    decisions = (WIKI / "Designentscheidungen.md").read_text(encoding="utf-8")

    for detector in ("Slow Leak", "Low Flow", "High Flow", "Burst Leak"):
        assert detector in detection

    assert "Quittierung" in alarms
    assert "globale Quittierung" in alarms
    assert "Absperranforderung" in shutoff
    assert "Quittierung löscht keinen Water-Shut-Off-Request" in decisions
    assert "Alarme bleiben bis zur physischen Resetbedingung stehen" in decisions


def test_wiki_uses_current_product_names() -> None:
    home = (WIKI / "Home.md").read_text(encoding="utf-8")
    assert "Wasserwächter" in home
    assert "Water Leak Guard" in home
    assert "water_leak_detection" in home


def _github_slug(heading: str) -> str:
    """GitHub heading anchor: lower case, punctuation dropped, each space a hyphen."""
    slug = re.sub(r"[^\w\- ]", "", heading.strip().lower())
    return slug.replace(" ", "-")


def test_display_forms_link_to_the_wiki_automation_example() -> None:
    import json

    base = "https://github.com/BeGiBue/homeassistant-water-leak-detection/wiki/"
    page = (WIKI / "Dashboard-Karte.md").read_text(encoding="utf-8")
    anchors = {
        _github_slug(line.lstrip("#"))
        for line in page.splitlines()
        if line.startswith("#")
    }
    assert _github_slug("Wanddisplay / TouchKio") == "wanddisplay--touchkio"
    translations = ROOT / "custom_components" / "water_leak_detection" / "translations"
    for lang in ("de", "en"):
        steps = json.loads((translations / f"{lang}.json").read_text(encoding="utf-8"))[
            "options"
        ]["step"]
        for step in ("add_display", "edit_display_details"):
            links = re.findall(r"\]\((https://[^)]+)\)", steps[step]["description"])
            wiki = [link for link in links if link.startswith(base)]
            assert len(wiki) == 1, (lang, step)
            target_page, _, anchor = wiki[0].removeprefix(base).partition("#")
            assert target_page == "Dashboard-Karte", (lang, step)
            assert anchor == "wanddisplay--touchkio" and anchor in anchors, (lang, step)
