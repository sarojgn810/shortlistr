"""Filling react-select comboboxes, which is how Greenhouse asks its screening
questions.

They look like text inputs and are not. `role="combobox"`, `aria-haspopup`, no
native `<select>`, and the committed value lives on a wrapper as `data-value`.
Calling `.fill()` types into the box and commits nothing — the form still shows
the text, and Greenhouse still rejects it as unanswered. That was the actual
failure on the GitLab posting: eight fields filled, ten required questions
silently empty.

So the fill has to open the menu, pick a real option, and then verify something
was committed rather than trusting the click.
"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


class FakeLocator:
    def __init__(self, options=(), attrs=None, committed=""):
        self._options = list(options)
        self._attrs = attrs or {}
        self.committed = committed
        self.clicked = False
        self.typed = ""
        self.pressed = []

    # -- interrogation --------------------------------------------------
    def get_attribute(self, name):
        return self._attrs.get(name)

    def count(self):
        return 1

    def is_visible(self, timeout=None):
        return True

    def is_enabled(self, timeout=None):
        return True

    # -- interaction ----------------------------------------------------
    def click(self, timeout=None):
        self.clicked = True

    def fill(self, value, timeout=None):
        self.typed = value

    def type(self, value, delay=None, timeout=None):
        self.typed = value

    def press(self, key, timeout=None):
        self.pressed.append(key)
        # Enter on a react-select commits the highlighted option.
        if key == "Enter" and self._options:
            self.committed = self._options[0]


class FakePage:
    """Minimal stand-in: option lookup returns whatever the test seeded."""

    def __init__(self, combobox, options=()):
        self.combobox = combobox
        self._options = list(options)

    def wait_for_timeout(self, ms):
        pass

    def locator(self, selector):
        class Options:
            def __init__(self, items):
                self._items = items

            def count(self_inner):
                return len(self_inner._items)

            def nth(self_inner, i):
                text = self_inner._items[i]
                loc = FakeLocator()
                loc.inner_text = lambda timeout=None, t=text: t
                loc.click = lambda timeout=None, t=text: setattr(
                    self.combobox, "committed", t
                )
                return loc

        return Options(self._options)


def test_recognises_a_react_select_combobox():
    from apply.ats_fill import _is_combobox

    box = FakeLocator(attrs={"role": "combobox", "aria-haspopup": "true"})

    assert _is_combobox(box) is True


def test_a_plain_text_input_is_not_a_combobox():
    from apply.ats_fill import _is_combobox

    assert _is_combobox(FakeLocator(attrs={"type": "text"})) is False


def test_picks_a_matching_option_from_the_menu():
    from apply.ats_fill import _fill_combobox

    box = FakeLocator(attrs={"role": "combobox"})
    page = FakePage(box, options=["Yes", "No"])

    assert _fill_combobox(page, box, "Yes") is True
    assert box.clicked, "the menu has to be opened before an option exists"
    assert box.committed == "Yes"


def test_typing_alone_is_not_treated_as_success():
    from apply.ats_fill import _fill_combobox

    # No options appear and Enter commits nothing — exactly the silent failure
    # this exists to catch. Typing text is not answering the question.
    box = FakeLocator(attrs={"role": "combobox"})
    page = FakePage(box, options=[])

    assert _fill_combobox(page, box, "Yes") is False


def test_reports_failure_when_no_option_matches():
    from apply.ats_fill import _fill_combobox

    box = FakeLocator(attrs={"role": "combobox"})
    page = FakePage(box, options=["Maybe", "Later"])

    # Picking the wrong option would put a false answer on an application.
    assert _fill_combobox(page, box, "Yes") is False
    assert box.committed == ""


def test_matches_an_option_case_insensitively():
    from apply.ats_fill import _fill_combobox

    box = FakeLocator(attrs={"role": "combobox"})
    page = FakePage(box, options=["YES", "NO"])

    assert _fill_combobox(page, box, "yes") is True


def test_option_lookup_is_scoped_to_this_control():
    """A page-wide option search finds the wrong widget.

    On a real Greenhouse form "[role='option']" matched 246 elements — the
    phone field's country-code list, which is always in the DOM — so the search
    walked country names looking for "Yes" and gave up after sixty.
    """
    from apply.ats_fill import _COMBOBOX_OPTION_SELECTOR

    assert "select__option" in _COMBOBOX_OPTION_SELECTOR
    # A bare, unscoped role=option would reintroduce the bug.
    assert not _COMBOBOX_OPTION_SELECTOR.strip().startswith("[role='option']")


def test_prefers_the_menu_the_control_names():
    from apply.ats_fill import _combobox_options

    asked = []

    class Page:
        def locator(self, selector):
            asked.append(selector)

            class L:
                def count(self_inner):
                    return 2 if "menu-7" in selector else 0

            return L()

    box = FakeLocator(attrs={"role": "combobox", "aria-controls": "menu-7"})
    _combobox_options(Page(), box)

    assert any("menu-7" in s for s in asked)


@pytest.mark.parametrize("answer,expected", [("Yes", "Yes, I am"), ("No", "No, I am not")])
def test_matches_an_option_that_contains_the_answer(answer, expected):
    from apply.ats_fill import _fill_combobox

    box = FakeLocator(attrs={"role": "combobox"})
    page = FakePage(box, options=["Yes, I am", "No, I am not"])

    assert _fill_combobox(page, box, answer) is True
    assert box.committed == expected
