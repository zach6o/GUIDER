"""Pointing at the right thing, or at nothing.

A mark is the one output that puts Guider's finger on a specific pixel, so the
tests here are mostly about refusing: geometry that would land off the frame, a
control the guard would never let anyone click, and — the ordinary case — no
confident match at all.
"""

import pytest

from app.guide.marks import clamp, kind_for, mark_for, tokens
from app.providers.base import VisibleControl
from tests.test_context import seen


class FakeInstruction:
    def __init__(self, what: str, where: str = ""):
        self.what = what
        self.where = where


def control(label: str, box=(0.1, 0.1, 0.4, 0.2), kind="button") -> VisibleControl:
    return VisibleControl(label=label, box=box, kind=kind)


# --- geometry -------------------------------------------------------------


@pytest.mark.parametrize(
    "box",
    [
        (0.2, 0.2, 0.1, 0.5),      # inverted horizontally
        (0.2, 0.5, 0.6, 0.2),      # inverted vertically
        (0.5, 0.5, 0.5001, 0.9),   # a line, not a box
        ("a", 0, 1, 1),            # not numbers at all
        (0, 0, 0, 0),              # nothing
    ],
)
def test_unusable_geometry_is_dropped(box):
    assert clamp(box) is None


def test_geometry_outside_the_frame_is_pulled_back_in():
    assert clamp((-0.5, -0.2, 1.4, 1.9)) == (0.0, 0.0, 1.0, 1.0)


def test_a_control_kind_chooses_a_shape():
    assert kind_for(control("Name", kind="field")) == "underline"
    assert kind_for(control("Allow?", kind="dialog")) == "spotlight"
    assert kind_for(control("Download", kind="button")) == "circle"


# --- matching -------------------------------------------------------------


def test_common_words_never_carry_a_match():
    # "click the button" against a button labelled "Cancel" must not match on
    # "click" or "button": the point of the mark is which one.
    assert tokens("Click the button") == set()


def test_the_instruction_finds_the_control_it_names():
    context = seen(controls=[control("Cancel"), control("Download", box=(0.5, 0.5, 0.7, 0.6))])
    mark = mark_for(FakeInstruction("Press Download to get the installer."), context)
    assert mark is not None
    assert mark.label == "Download"
    assert mark.box == (0.5, 0.5, 0.7, 0.6)


def test_the_shorter_label_wins_a_tie():
    context = seen(controls=[
        control("Download the beta installer for developers"),
        control("Download", box=(0.5, 0.5, 0.7, 0.6)),
    ])
    assert mark_for(FakeInstruction("Download it."), context).label == "Download"


def test_no_confident_match_means_no_mark():
    """The ordinary case. The instruction still says where to look in words, and
    a confident arrow at the wrong control is worse than none."""
    context = seen(controls=[control("Cancel"), control("Preferences")])
    assert mark_for(FakeInstruction("Open the terminal panel."), context) is None


def test_a_screen_with_no_controls_produces_nothing():
    assert mark_for(FakeInstruction("Do the thing."), seen(controls=[])) is None


def test_no_instruction_means_no_mark():
    assert mark_for(None, seen(controls=[control("Download")])) is None


# --- the guard ------------------------------------------------------------


def test_guider_never_points_at_a_restricted_action():
    context = seen(controls=[control("sudo rm -rf /")])
    assert mark_for(FakeInstruction("Run sudo rm -rf / to clear it."), context) is None


def test_where_is_searched_as_well_as_what():
    context = seen(controls=[control("Terminal", box=(0.2, 0.8, 0.9, 0.95), kind="tab")])
    mark = mark_for(FakeInstruction("Open the panel.", where="In the Terminal tab."), context)
    assert mark is not None
    assert mark.label == "Terminal"
