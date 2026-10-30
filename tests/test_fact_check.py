"""Fact-checker: strict place matching (a wrong match would make false claims) and time parsing."""

from __future__ import annotations

from datetime import time

import pytest

from tastewalk.fact_check import _parse_times, name_variants, same_place


@pytest.mark.parametrize(
    ("llm", "qloo", "match"),
    [
        ("Jean-Talon Market", "Jean Talon Market", True),
        ("Cinéma du Parc", "Cinema du Parc", True),
        ("Café Olimpico", "Café Olimpico - Vieux-Montréal", True),
        ("Belvédère Kondiaronk", "Kondiaronk Belvedere", True),
        ("Marché Jean-Talon", "SAQ-Marché Jean-Talon", False),  # liquor store inside the market
        ("Phonopolis", "La Grande Roue de Montréal", False),
        ("Café", "Café Parvis", False),  # generic words alone never match
    ],
)
def test_same_place(llm, qloo, match):
    assert same_place(llm, qloo) is match


def test_name_variants_strip_decoration_but_not_streets():
    assert name_variants("Muji Montréal – Rue Saint‑Denis") == [
        "Muji Montréal - Rue Saint-Denis",
        "Muji Montréal",
    ]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("11:00 - 12:30", (time(11), time(12, 30))),
        ("2:00 PM", (time(14), time(15))),
        ("14h00-15h15", (time(14), time(15, 15))),
        ("afternoon", None),
        (None, None),
    ],
)
def test_parse_times(text, expected):
    assert _parse_times(text) == expected
