"""Tests for the grapeminds integration and the combined search."""
import json
from unittest.mock import MagicMock, patch

import pytest

import app as wine_app
import grapeminds as gm


def _resp(status=200, body=None, headers=None):
    r = MagicMock()
    r.status_code = status
    r.headers = headers or {}
    r.json.return_value = body
    return r


DETAIL = {
    "data": {
        "id": 42,
        "display_name": "Barolo DOCG 2018",
        "color": "red", "type": "wine", "sub_type": "still",
        "residual_sugar": "trocken",
        "producer": {"id": 10, "name": "Marchesi di Barolo", "title": None,
                     "display_name": "Marchesi di Barolo"},
        "region": {"id": 5, "name": "Barolo", "country": "IT", "language": "de"},
        "grapes": [{"id": 1, "name": "Nebbiolo"}],
        "description": {"text": "Ein kraftvoller Rotwein.", "language": "de"},
        "pairing": {"text": "Trüffel und Wild.", "language": "de"},
        "tasting_notes": {"text": "Rote Beeren, Teer.", "language": "de"},
        "flavor_profile": {"sweetness": 1, "acidity": 3, "tannins": 5,
                           "alcohol": 4, "body": 5, "finish": 5},
    }
}
PERIOD = {"id": 1, "wine_id": 42, "lang": "de", "from": 2024, "to": 2035,
          "storage": "Kühl lagern."}
SEARCH = {"data": [{"id": 42, "display_name": "Barolo DOCG 2018", "color": "red",
                    "residual_sugar": "trocken", "producer_name": "Marchesi di Barolo",
                    "producer_display_name": "Marchesi di Barolo"}],
          "meta": {"query": "Barolo", "count": 1}}


@pytest.fixture
def gm_key(monkeypatch):
    real = wine_app.load_options

    def opts():
        o = real()
        o["grapeminds_api_key"] = "test-key"
        return o
    monkeypatch.setattr(wine_app, "load_options", opts)


# ── Mapping ───────────────────────────────────────────────────────────────────

class TestMapping:
    @pytest.mark.parametrize("args,expected", [
        (("red", "wine", "still", "dry"), "Rotwein"),
        (("white", "wine", "still", "trocken"), "Weisswein"),
        (("rose", "wine", "still", None), "Rosé"),
        (("white", "wine", "sparkling", "brut"), "Schaumwein"),
        (("red", "fortified_wine", None, "sweet"), "Likörwein"),
        (("white", "wine", "still", "edelsüß"), "Dessertwein"),
        (("white", "wine", "still", "halbtrocken"), "Weisswein"),
        (("white", "spirit", None, None), "Anderes"),
        ((None, None, None, None), ""),
    ])
    def test_wine_type(self, args, expected):
        assert gm.wine_type(*args) == expected

    def test_year_from_name(self):
        assert gm.year_from_name("Barolo DOCG 2018") == 2018
        assert gm.year_from_name("Riesling GG") is None

    def test_taste_profile_maps_and_clamps(self):
        tp = gm.taste_profile({"body": 5, "tannins": 7, "acidity": 0, "sweetness": "2"})
        assert tp == {"body": 5, "tannin": 5, "acidity": 1, "sweetness": 2}

    def test_strip_producer(self):
        assert gm.strip_producer("Bruno Rivetti, Barolo", "Bruno Rivetti") == "Barolo"
        assert gm.strip_producer("Barolo DOCG", "Marchesi di Barolo") == "Barolo DOCG"
        assert gm.strip_producer("Funtanin", "Funtanin") == "Funtanin"

    def test_country_name(self):
        assert gm.country_name("IT", "de") == "Italien"
        assert gm.country_name("IT", "en") == "Italy"
        assert gm.country_name("XX") == "XX"


# ── Client ────────────────────────────────────────────────────────────────────

class TestClient:
    def test_search_parses_results_and_sends_auth(self):
        s = MagicMock()
        s.get.return_value = _resp(body=SEARCH)
        res = gm.search(s, "k", "Barolo")
        assert res == [{"grapeminds_id": 42, "name": "Barolo DOCG 2018",
                        "producer": "Marchesi di Barolo", "year": 2018,
                        "wine_type": "Rotwein"}]
        headers = s.get.call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer k"
        assert headers["Accept-Language"] == "de"

    def test_search_too_short(self):
        with pytest.raises(gm.GrapemindsError) as e:
            gm.search(MagicMock(), "k", "ab")
        assert e.value.code == "query_too_short"

    def test_search_strips_producer_from_name(self):
        s = MagicMock()
        s.get.return_value = _resp(body={"data": [{"id": 1, "display_name": "Bruno Rivetti, Barolo",
                                                   "color": "red", "producer_display_name": "Bruno Rivetti"}]})
        assert gm.search(s, "k", "Barolo")[0]["name"] == "Barolo"

    @pytest.mark.parametrize("status,body,code", [
        (401, {"message": "Invalid API key"}, "invalid_key"),
        (429, {"error": {"code": "rate_limited"}}, "rate_limited"),
        (404, {"generating": True}, "generating"),
        (404, {"generating": False}, "not_found"),
        (500, {}, "api_error"),
    ])
    def test_errors(self, status, body, code):
        s = MagicMock()
        s.get.return_value = _resp(status, body)
        with pytest.raises(gm.GrapemindsError) as e:
            gm.search(s, "k", "Barolo")
        assert e.value.code == code

    def test_wine_fields(self):
        s = MagicMock()
        s.get.side_effect = [_resp(body=DETAIL), _resp(body=PERIOD)]
        f = gm.wine_fields(s, "k", 42)
        assert f["name"] == "Barolo DOCG"
        assert f["producer"] == "Marchesi di Barolo"
        assert f["vintage"] == 2018
        assert f["wine_type"] == "Rotwein"
        assert f["region"] == "Barolo, Italien"
        assert f["grape"] == "Nebbiolo"
        assert (f["drink_from"], f["drink_until"]) == (2024, 2035)
        assert f["taste_profile"] == {"body": 5, "tannin": 5, "acidity": 3, "sweetness": 1}
        assert "Ein kraftvoller Rotwein." in f["notes"]
        assert "Kühl lagern." in f["notes"]
        assert "Passt zu: Trüffel und Wild." in f["notes"]
        assert "Rote Beeren" not in f["notes"]  # tasting notes dropped when a description exists
        assert f["grapeminds_id"] == 42

    def test_wine_fields_without_drinking_period(self):
        s = MagicMock()
        s.get.side_effect = [_resp(body=DETAIL["data"]),  # no "data" wrapper
                             _resp(404, {"generating": True})]
        f = gm.wine_fields(s, "k", 42)
        assert "drink_from" not in f
        assert f["region"] == "Barolo, Italien"


# ── Merge ─────────────────────────────────────────────────────────────────────

class TestMerge:
    def test_priorities_and_sources(self):
        ai = {"name": "Barolo", "vintage": 2019, "alcohol_pct": 14.5,
              "drink_from": 2022, "drink_until": 2030, "notes": "KI-Notiz",
              "food_pairings": ["Wild"], "region": "Piemont"}
        grapeminds = {"name": "Barolo DOCG", "producer": "Marchesi di Barolo",
                      "vintage": 2018, "region": "Barolo, Italien",
                      "drink_from": 2024, "drink_until": 2035, "notes": "GM-Notiz"}
        vivino = {"name": "Marchesi di Barolo Barolo", "vintage": 2017,
                  "price": 39.9, "rating": 4.1, "region": "Barolo, Italy"}
        fields, src = gm.merge(ai, grapeminds, vivino)
        # label facts win for vintage / alcohol
        assert fields["vintage"] == 2019 and src["vintage"] == "label"
        assert fields["alcohol_pct"] == 14.5 and src["alcohol_pct"] == "label"
        # verified master data from grapeminds
        assert fields["region"] == "Barolo, Italien" and src["region"] == "grapeminds"
        assert fields["drink_from"] == 2024 and src["drink_from"] == "grapeminds"
        assert fields["notes"] == "GM-Notiz"
        # market data from vivino
        assert fields["price"] == 39.9 and src["price"] == "vivino"
        assert fields["rating"] == 4.1
        # AI estimates only where nothing else exists
        assert fields["food_pairings"] == ["Wild"] and src["food_pairings"] == "ai"

    def test_ai_estimates_fill_gaps(self):
        fields, src = gm.merge({"drink_from": 2022, "notes": "x"}, {}, {})
        assert src == {"drink_from": "ai", "notes": "ai"}

    def test_vivino_fields(self):
        assert gm.vivino_fields({"name": "A", "year": 2020, "price": None}) == \
            {"name": "A", "vintage": 2020}
        assert gm.vivino_fields(None) == {}


# ── Routes ────────────────────────────────────────────────────────────────────

class TestRoutes:
    def test_search_without_key(self, client):
        resp = client.get("/api/grapeminds-search?q=Barolo")
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "no_api_key"

    @patch("requests.Session")
    def test_search(self, MockSession, client, gm_key):
        MockSession.return_value.get.return_value = _resp(body=SEARCH)
        resp = client.get("/api/grapeminds-search?q=Barolo")
        data = resp.get_json()
        assert data["ok"] is True
        assert data["results"][0]["grapeminds_id"] == 42

    @patch("requests.Session")
    def test_search_invalid_key(self, MockSession, client, gm_key):
        MockSession.return_value.get.return_value = _resp(401, {"message": "Invalid API key"})
        resp = client.get("/api/grapeminds-search?q=Barolo")
        assert resp.status_code == 401
        assert resp.get_json()["error"] == "invalid_key"

    @patch("requests.Session")
    def test_wine(self, MockSession, client, gm_key):
        MockSession.return_value.get.side_effect = [_resp(body=DETAIL), _resp(body=PERIOD)]
        data = client.get("/api/grapeminds-wine/42").get_json()
        assert data["ok"] is True
        assert data["fields"]["drink_until"] == 2035
        assert data["sources"]["region"] == "grapeminds"

    @patch("requests.Session")
    def test_combine(self, MockSession, client, gm_key):
        MockSession.return_value.get.side_effect = [_resp(body=DETAIL), _resp(body=PERIOD)]
        resp = client.post("/api/combine", json={
            "ai": {"vintage": 2019, "alcohol_pct": 14.0},
            "grapeminds_id": 42,
            "vivino": {"name": "Marchesi di Barolo Barolo", "year": 2017,
                       "price": 39.9, "rating": 4.1, "vivino_id": 7},
        })
        data = resp.get_json()
        assert data["ok"] is True and data["warnings"] == []
        assert data["fields"]["vintage"] == 2019
        assert data["fields"]["region"] == "Barolo, Italien"
        assert data["fields"]["price"] == 39.9
        assert data["sources"]["price"] == "vivino"

    @patch("requests.Session")
    def test_combine_survives_grapeminds_failure(self, MockSession, client, gm_key):
        MockSession.return_value.get.return_value = _resp(429, {}, {"Retry-After": "5"})
        data = client.post("/api/combine", json={
            "grapeminds_id": 42, "vivino": {"name": "X", "price": 10.0},
        }).get_json()
        assert data["ok"] is True
        assert data["warnings"] == ["grapeminds_rate_limited"]
        assert data["fields"]["name"] == "X"

    def test_combine_without_key_warns(self, client):
        data = client.post("/api/combine", json={"grapeminds_id": 42}).get_json()
        assert data["warnings"] == ["grapeminds_no_api_key"]

    def test_index_hides_grapeminds_without_key(self, client):
        html = client.get("/").get_data(as_text=True)
        assert "onSourceGrapeminds()" not in html

    def test_index_shows_grapeminds_with_key(self, client, gm_key):
        html = client.get("/").get_data(as_text=True)
        assert "onSourceGrapeminds()" in html
        assert "onSourceCombined()" in html
