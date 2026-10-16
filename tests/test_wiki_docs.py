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
    "Wanddisplay-TouchKio.md",
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
    """The link is a placeholder (hassfest forbids URLs in translations)."""
    import json

    from custom_components.water_leak_detection.config_flow import DISPLAY_AUTOMATION_URL

    base = "https://github.com/BeGiBue/water-leak-guard/wiki/"
    page = (WIKI / "Dashboard-Karte.md").read_text(encoding="utf-8")
    anchors = {
        _github_slug(line.lstrip("#"))
        for line in page.splitlines()
        if line.startswith("## ") or line.startswith("# ")
    }
    assert _github_slug("Wanddisplay / TouchKio") == "wanddisplay--touchkio"
    target_page, _, anchor = DISPLAY_AUTOMATION_URL.removeprefix(base).partition("#")
    assert DISPLAY_AUTOMATION_URL.startswith(base) and target_page == "Dashboard-Karte"
    assert anchor == "wanddisplay--touchkio" and anchor in anchors
    translations = ROOT / "custom_components" / "water_leak_detection" / "translations"
    for lang in ("de", "en"):
        steps = json.loads((translations / f"{lang}.json").read_text(encoding="utf-8"))[
            "options"
        ]["step"]
        for step in ("add_display", "edit_display_details"):
            description = steps[step]["description"]
            assert re.search(r"\[[^\]]+\]\(\{automation_url\}\)", description), (lang, step)
            assert "://" not in description, (lang, step)


def test_wall_display_page_is_linked_and_anchors_resolve() -> None:
    """The guide exists, is linked from the entry pages and its anchors work."""
    guide = (WIKI / "Wanddisplay-TouchKio.md").read_text(encoding="utf-8")
    assert guide.startswith("# Wanddisplay mit TouchKio")
    for page in (
        "_Sidebar.md",
        "Home.md",
        "Dashboard-Karte.md",
        "Alarmstufen-und-Quittierung.md",
        "Installation-und-Konfiguration.md",
    ):
        assert "Wanddisplay-TouchKio" in (WIKI / page).read_text(encoding="utf-8"), page

    anchors_by_page = {
        path.stem: {
            _github_slug(line.lstrip("#"))
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.startswith("#")
        }
        for path in WIKI.glob("*.md")
    }
    link_pattern = re.compile(r"\[[^]]+\]\(([^)]+)\)")
    broken: list[tuple[str, str]] = []
    for path in WIKI.glob("*.md"):
        for target in link_pattern.findall(path.read_text(encoding="utf-8")):
            if "://" in target or target.endswith(".md"):
                continue
            page, _, anchor = target.partition("#")
            page = page or path.stem
            if anchor and page in anchors_by_page and anchor not in anchors_by_page[page]:
                broken.append((path.name, target))
    assert broken == []


def test_wall_display_images_are_absolute_raw_urls_and_small() -> None:
    base = (
        "https://raw.githubusercontent.com/BeGiBue/water-leak-guard"
        "/main/docs/assets/"
    )
    for image in ("card-preview.png", "card-wall-display.png"):
        assert (ROOT / "docs" / "assets" / image).stat().st_size < 400_000, image
    for doc in (
        ROOT / "README.md",
        ROOT / "docs" / "CARD.md",
        WIKI / "Dashboard-Karte.md",
        WIKI / "Wanddisplay-TouchKio.md",
    ):
        text = doc.read_text(encoding="utf-8")
        if doc.name == "README.md":
            assert f"]({base}" in text, doc
        else:
            assert base + "card-wall-display.png" in text or base + "card-preview.png" in text, doc
        assert "](docs/assets/" not in text and "](../assets/" not in text, doc
