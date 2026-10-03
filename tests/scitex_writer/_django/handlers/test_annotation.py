#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for _django/handlers/annotation.py (the /api/annotations handler).

Real Django RequestFactory + a REAL store in a throwaway PostgreSQL schema
(``pg_schema``) — never a mock and never the live fleet store. ``pg_schema``
repoints ``SCITEX_CARDS_DB`` as well, which is what keeps the handler's emit
seam off the live cards board: the handler passes NO explicit cards store, so
before that isolation existed every POST here commented on the real
``writer-annotations-*`` card. The rail stays optional, so the notify tests
``pytest.importorskip("scitex_cards")``. No mocks (STX-NM002); one assert per
test (STX-TQ007).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from django.test import RequestFactory

from scitex_writer._django import views


@pytest.fixture
def project_dir(tmp_path):
    p = tmp_path / "myproj"
    (p / "01_manuscript" / "contents").mkdir(parents=True)
    (p / "01_manuscript" / "contents" / "01_intro.tex").write_text(r"\section{Intro}")
    (p / "00_shared" / "bib_files").mkdir(parents=True)
    (p / "00_shared" / "bib_files" / "bibliography.bib").write_text(
        "@article{foo2024, title={Foo}}\n"
    )
    return str(p)


@pytest.fixture
def seeded_card(seed_card) -> str:
    """The manuscript's owning card, on the throwaway board."""
    return seed_card("writer-annotations-myproj", "annotations for myproj")


def _post(project: str, body: dict):
    rf = RequestFactory()
    request = rf.post(
        f"/api/annotations?working_dir={project}",
        data=json.dumps(body),
        content_type="application/json",
    )
    request._dont_enforce_csrf_checks = True  # Handler unit test; boundary tests enforce CSRF.
    return views.api_dispatch(request, "api/annotations")


def _text_body(text: str = "please clarify") -> dict:
    return {"page": 2, "doc_type": "manuscript", "payload": {"text": text}}


def test_post_returns_200(pg_schema: str, project_dir):
    # Arrange
    body = _text_body()
    # Act
    resp = _post(project_dir, body)
    # Assert
    assert resp.status_code == 200


def test_post_response_is_ok(pg_schema: str, project_dir):
    # Arrange
    body = _text_body()
    # Act
    data = json.loads(_post(project_dir, body).content)
    # Assert
    assert data["ok"] is True


def test_post_assigns_annotation_id(pg_schema: str, project_dir):
    # Arrange
    body = _text_body()
    # Act
    data = json.loads(_post(project_dir, body).content)
    # Assert
    assert data["annotation_id"]


def test_post_source_ref_is_page_only(pg_schema: str, project_dir):
    # Arrange
    body = _text_body()
    # Act
    data = json.loads(_post(project_dir, body).content)
    # Assert
    assert data["source_ref"] == {"page": 2}


def test_post_invalid_kind_returns_400(project_dir):
    """Validation refuses BEFORE any store is opened — no fixture needed."""
    # Arrange
    body = {"page": 1, "kind": "stroke", "payload": {"text": "x"}}
    # Act
    resp = _post(project_dir, body)
    # Assert
    assert resp.status_code == 400


def test_get_lists_the_persisted_annotation(pg_schema: str, project_dir):
    # Arrange
    _post(project_dir, _text_body("first note"))
    rf = RequestFactory()
    request = rf.get(f"/api/annotations?working_dir={project_dir}")
    # Act
    data = json.loads(views.api_dispatch(request, "api/annotations").content)
    # Assert
    assert data["count"] == 1


def test_get_does_not_see_another_manuscripts_annotation(pg_schema: str, tmp_path):
    """The store is fleet-wide; the project scope is what keeps queues apart."""
    # Arrange
    mine, theirs = str(tmp_path / "mine"), str(tmp_path / "theirs")
    for p in (mine, theirs):
        (Path(p) / "01_manuscript" / "contents").mkdir(parents=True)
    _post(theirs, _text_body("not mine"))
    rf = RequestFactory()
    request = rf.get(f"/api/annotations?working_dir={mine}")
    # Act
    data = json.loads(views.api_dispatch(request, "api/annotations").content)
    # Assert
    assert data["count"] == 0


def test_post_emit_seam_notifies_owning_card(seeded_card: str, project_dir):
    # Arrange
    body = _text_body()
    # Act
    data = json.loads(_post(project_dir, body).content)
    # Assert
    assert data["notified"] is True


def test_post_comment_lands_on_the_card(seeded_card: str, project_dir):
    # Arrange
    from scitex_cards import get_task

    _post(project_dir, _text_body("expand the discussion"))
    # Act
    card = get_task(None, seeded_card)
    texts = " ".join(c.get("text", "") for c in card.get("comments", []))
    # Assert
    assert "expand the discussion" in texts
