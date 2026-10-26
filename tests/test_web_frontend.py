"""Static UI contracts, plus dependency-free JavaScript regression tests."""

from __future__ import annotations

from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
import re
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "neow" / "web" / "static"
VOID_ELEMENTS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


class _PageParser(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.nodes = []
        self.stack = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        node = {
            "tag": tag,
            "attrs": dict(attrs),
            "text": "",
            "ancestors": tuple(self.stack),
        }
        self.nodes.append(node)
        if tag not in VOID_ELEMENTS:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID_ELEMENTS:
            self.stack.pop()

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]["tag"] == tag:
                del self.stack[index:]
                break

    def handle_data(self, text):
        for node in self.stack:
            node["text"] += text

    @property
    def by_id(self):
        return {n["attrs"]["id"]: n for n in self.nodes if "id" in n["attrs"]}


@pytest.fixture
def page():
    return _PageParser((STATIC / "index.html").read_text(encoding="utf-8"))


def test_frontend_ids_are_unique_and_controller_targets_exist(page):
    ids = [node["attrs"]["id"] for node in page.nodes if "id" in node["attrs"]]
    assert not {key: count for key, count in Counter(ids).items() if count > 1}

    controller = (STATIC / "app.js").read_text(encoding="utf-8")
    selectors = set(re.findall(r'\$\(["\']#([\w-]+)["\']\)', controller))
    assert selectors <= set(
        ids
    ), f"Controller targets missing from HTML: {selectors - set(ids)}"


def test_frontend_tabs_and_modal_close_targets_exist(page):
    for node in page.nodes:
        attrs = node["attrs"]
        if "tab-btn" in attrs.get("class", "").split():
            assert f"tab-{attrs['data-tab']}" in page.by_id
        if "data-close" in attrs:
            assert attrs["data-close"] in page.by_id
        for target in attrs.get("aria-controls", "").split():
            assert target in page.by_id


def test_frontend_forms_and_buttons_have_accessible_names(page):
    labelled = {
        node["attrs"]["for"]
        for node in page.nodes
        if node["tag"] == "label" and node["text"].strip() and "for" in node["attrs"]
    }
    missing = []
    for node in page.nodes:
        if node["tag"] not in {"input", "textarea", "select", "button"}:
            continue
        attrs = node["attrs"]
        if attrs.get("type") == "hidden":
            continue
        references = attrs.get("aria-labelledby", "").split()
        referenced_name = references and all(
            target in page.by_id and page.by_id[target]["text"].strip()
            for target in references
        )
        named = (
            attrs.get("aria-label", "").strip()
            or referenced_name
            or attrs.get("id") in labelled
            or (node["tag"] == "button" and node["text"].strip())
        )
        if not named:
            missing.append(attrs.get("id", node["tag"]))
    assert not missing, f"Controls missing accessible names: {missing}"


def test_frontend_dialogs_and_mobile_viewport_are_declared(page):
    dialogs = [
        n for n in page.nodes if "modal-dialog" in n["attrs"].get("class", "").split()
    ]
    assert dialogs
    for dialog in dialogs:
        attrs = dialog["attrs"]
        assert attrs.get("role") == "dialog"
        assert attrs.get("aria-modal") == "true"
        assert attrs.get("aria-label") or attrs.get("aria-labelledby")
    html = next(node for node in page.nodes if node["tag"] == "html")
    assert html["attrs"].get("lang")
    assert any(
        node["tag"] == "meta"
        and node["attrs"].get("name") == "viewport"
        and "width=device-width" in node["attrs"].get("content", "")
        for node in page.nodes
    )


def test_workspace_card_exposes_a_keyboard_accessible_switch_control(page):
    controls = [
        node
        for node in page.nodes
        if "workspace-card" in node["attrs"].get("class", "").split()
    ]
    assert len(controls) == 1
    assert controls[0]["tag"] == "button"
    assert controls[0]["attrs"].get("aria-haspopup") == "dialog"
    assert "modal-workspace" in page.by_id


def test_secondary_tools_are_available_on_demand_instead_of_always_visible(page):
    library = page.by_id["workspace-library"]
    assert "hidden" in library["attrs"]["class"].split()
    assert page.by_id["btn-toggle-library"]["attrs"]["aria-expanded"] == "false"

    def inside(control_id, container_id):
        return any(
            node["attrs"].get("id") == container_id
            for node in page.by_id[control_id]["ancestors"]
        )

    assert inside("file-search-input", "workspace-library")
    assert inside("skills-list", "workspace-library")
    for control_id in ("act-open-plan", "act-open-goal", "act-git-diff", "act-compact"):
        assert inside(control_id, "workflow-menu")
    for control_id in ("select-approval-mode", "select-effort"):
        assert inside(control_id, "composer-options")
    for menu_id in ("workflow-menu", "composer-options"):
        menu = page.by_id[menu_id]
        assert menu["tag"] == "details"
        assert "open" not in menu["attrs"]
    assert "btn-close-inspector" in page.by_id


def test_empty_state_avoids_decorative_hero_and_dashboard_chrome(page):
    classes = {
        cls
        for node in page.nodes
        for cls in node["attrs"].get("class", "").split()
    }
    assert not classes.intersection(
        {"studio-art", "canvas-footer", "brand-badge", "sidebar-signoff"}
    )
    assert "welcome-title" in page.by_id
    assert len(page.by_id["welcome-title"]["text"].strip()) < 20


def test_frontend_javascript_regressions():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is optional for Python-only installations")
    result = subprocess.run(
        [node, "--test", str(ROOT / "tests" / "web_frontend.test.cjs")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
