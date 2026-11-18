"""grapeminds Wine API client and source merging for WeinSommelier.

grapeminds (https://grapeminds.eu/wine-api) is an official REST API with an
API key.  It supplies verified master data (producer, region, grapes,
drinking window, descriptions, flavor profile) but no prices, ratings or
bottle images - those still come from Vivino, and label facts (vintage,
alcohol, bottle size) from the AI label reader.

This module has no Flask dependency so it can be unit-tested directly.
"""
import re

BASE_URL = "https://api.grapeminds.eu/public/v1"
TIMEOUT = 10

# Languages grapeminds can localize texts into.
SUPPORTED_LANGS = {"de", "en", "it", "fr", "es", "pt", "nl"}


class GrapemindsError(Exception):
    """Raised for any grapeminds failure; `code` is a short machine string."""

    def __init__(self, code, message="", retry_after=None):
        super().__init__(message or code)
        self.code = code
        self.retry_after = retry_after


# ── Low-level HTTP ────────────────────────────────────────────────────────────

def _get(session, path, api_key, lang="de", params=None, verify=True):
    """GET a grapeminds endpoint and return parsed JSON (or raise)."""
    import requests as req

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Accept-Language": lang if lang in SUPPORTED_LANGS else "en",
    }
    try:
        resp = session.get(f"{BASE_URL}{path}", headers=headers, params=params,
                           timeout=TIMEOUT, verify=verify)
    except req.exceptions.Timeout:
        raise GrapemindsError("timeout")
    except req.exceptions.RequestException as e:
        raise GrapemindsError("network_error", str(e))

    if resp.status_code == 401:
        raise GrapemindsError("invalid_key")
    if resp.status_code == 429:
        retry = resp.headers.get("Retry-After")
        raise GrapemindsError("rate_limited", retry_after=retry)
    if resp.status_code == 404:
        body = _safe_json(resp)
        if isinstance(body, dict) and body.get("generating"):
            raise GrapemindsError("generating")
        raise GrapemindsError("not_found")
    if resp.status_code >= 400:
        raise GrapemindsError("api_error", f"HTTP {resp.status_code}")
    body = _safe_json(resp)
    if body is None:
        raise GrapemindsError("parse_error")
    return body


def _safe_json(resp):
    try:
        return resp.json()
    except ValueError:
        return None


def _unwrap(body):
    """Some endpoints wrap the object in {"data": ...}, some do not."""
    if isinstance(body, dict) and isinstance(body.get("data"), (dict, list)):
        return body["data"]
    return body


# ── Mapping helpers ──────────────────────────────────────────────────────────

_YEAR_RE = re.compile(r"\b(19[0-9]{2}|20[0-9]{2})\b")

# ISO country code -> name (German / English). Covers the wine countries the
# stats map knows; unknown codes are passed through unchanged.
_COUNTRIES = {
    "FR": ("Frankreich", "France"), "IT": ("Italien", "Italy"),
    "ES": ("Spanien", "Spain"), "DE": ("Deutschland", "Germany"),
    "AT": ("Österreich", "Austria"), "CH": ("Schweiz", "Switzerland"),
    "PT": ("Portugal", "Portugal"), "US": ("USA", "USA"),
    "AR": ("Argentinien", "Argentina"), "CL": ("Chile", "Chile"),
    "AU": ("Australien", "Australia"), "NZ": ("Neuseeland", "New Zealand"),
    "ZA": ("Südafrika", "South Africa"), "GR": ("Griechenland", "Greece"),
    "HU": ("Ungarn", "Hungary"), "SI": ("Slowenien", "Slovenia"),
    "HR": ("Kroatien", "Croatia"), "LB": ("Libanon", "Lebanon"),
    "IL": ("Israel", "Israel"), "GE": ("Georgien", "Georgia"),
    "CA": ("Kanada", "Canada"), "UY": ("Uruguay", "Uruguay"),
    "RO": ("Rumänien", "Romania"), "BG": ("Bulgarien", "Bulgaria"),
    "MD": ("Moldawien", "Moldova"), "CZ": ("Tschechien", "Czechia"),
    "LU": ("Luxemburg", "Luxembourg"), "GB": ("England", "England"),
}

_SWEET_WORDS = ("sweet", "süß", "suess", "edelsüß", "dolce", "doux", "liebl")


def country_name(code, lang="de"):
    if not code:
        return ""
    names = _COUNTRIES.get(str(code).upper())
    if not names:
        return str(code)
    return names[0] if lang == "de" else names[1]


def strip_producer(name, producer):
    """grapeminds names often repeat the producer ("Bruno Rivetti, Barolo")."""
    name = (name or "").strip()
    producer = (producer or "").strip()
    if producer and name.lower().startswith(producer.lower()):
        rest = name[len(producer):].lstrip(" ,-–")
        if rest:
            return rest
    return name


def year_from_name(name):
    """grapeminds display names often end with the vintage ("... 2018")."""
    if not name:
        return None
    years = _YEAR_RE.findall(str(name))
    return int(years[-1]) if years else None


def wine_type(color=None, type_=None, sub_type=None, residual_sugar=None):
    """Map grapeminds color/type/sub_type to WeinSommelier's wine types."""
    t = (type_ or "").lower()
    st = (sub_type or "").lower()
    c = (color or "").lower()
    sugar = (residual_sugar or "").lower()
    if "fortified" in t:
        return "Likörwein"
    if st == "sparkling" or c == "sparkling":
        return "Schaumwein"
    if t and t not in ("wine",):
        return "Anderes"
    if any(w in sugar for w in _SWEET_WORDS) and "halb" not in sugar \
            and "semi" not in sugar and "medium" not in sugar:
        return "Dessertwein"
    return {"red": "Rotwein", "white": "Weisswein",
            "rose": "Rosé", "rosé": "Rosé"}.get(c, "")


def _text(obj):
    """Return the best text from a {text, text_long} block (or a string)."""
    if isinstance(obj, str):
        return obj.strip()
    if isinstance(obj, list):
        obj = obj[0] if obj else None
    if isinstance(obj, dict):
        return (obj.get("text") or obj.get("text_long") or "").strip()
    return ""


def _clamp_1_5(val):
    try:
        v = int(round(float(val)))
    except (TypeError, ValueError):
        return None
    return max(1, min(5, v))


def taste_profile(flavor):
    """grapeminds flavor_profile (1-5 scales) -> WeinSommelier taste_profile."""
    if not isinstance(flavor, dict):
        return None
    out = {}
    for src, dst in (("body", "body"), ("tannins", "tannin"),
                     ("acidity", "acidity"), ("sweetness", "sweetness")):
        v = _clamp_1_5(flavor.get(src))
        if v is not None:
            out[dst] = v
    return out or None


# ── Public API ────────────────────────────────────────────────────────────────

def search(session, api_key, query, lang="de", limit=10, verify=True):
    """Full-text wine search. Returns a list of compact result dicts."""
    query = (query or "").strip()
    if len(query) < 3:
        raise GrapemindsError("query_too_short")
    body = _get(session, "/wines/search", api_key, lang,
                params={"q": query[:255], "limit": limit}, verify=verify)
    items = _unwrap(body)
    if not isinstance(items, list):
        items = []
    results = []
    for it in items:
        if not isinstance(it, dict) or it.get("id") is None:
            continue
        name = (it.get("display_name") or "").strip()
        producer = (it.get("producer_display_name") or it.get("producer_name") or "").strip()
        results.append({
            "grapeminds_id": it.get("id"),
            "name": strip_producer(name, producer),
            "producer": producer,
            "year": it.get("vintage") or year_from_name(name),
            "wine_type": wine_type(it.get("color"), None, None, it.get("residual_sugar")),
        })
    return results


def wine_fields(session, api_key, wine_id, lang="de", verify=True):
    """Fetch details + drinking period for one wine, mapped to form fields.

    Costs two API requests.  A missing drinking period is not an error.
    """
    detail = _unwrap(_get(session, f"/wines/{int(wine_id)}", api_key, lang,
                          params={"lang": lang}, verify=verify))
    if not isinstance(detail, dict):
        raise GrapemindsError("parse_error")

    producer_obj = detail.get("producer") or {}
    producer = (producer_obj.get("display_name") or producer_obj.get("name") or "").strip()
    name = strip_producer(detail.get("display_name"), producer)
    vintage = detail.get("vintage") or year_from_name(name)
    if vintage and name.endswith(str(vintage)):
        name = name[: -len(str(vintage))].rstrip(" ,-")

    region_obj = detail.get("region") or {}
    region_name = (region_obj.get("name") or "").strip()
    country = country_name(region_obj.get("country"), lang)
    region = ", ".join(p for p in (region_name, country) if p)

    grapes = [g.get("name", "").strip() for g in detail.get("grapes") or []
              if isinstance(g, dict) and g.get("name")]

    fields = {
        "name": name,
        "producer": producer,
        "vintage": vintage,
        "wine_type": wine_type(detail.get("color"), detail.get("type"),
                               detail.get("sub_type"), detail.get("residual_sugar")),
        "region": region,
        "grape": ", ".join(grapes),
        "taste_profile": taste_profile(detail.get("flavor_profile")),
    }

    # Keep the note short: one description (the tasting notes largely repeat
    # it), the storage hint and the pairing.
    notes = []
    for key in ("description", "descriptions", "tasting_notes", "tastingnotes"):
        txt = _text(detail.get(key))
        if txt:
            notes.append(txt)
            break
    pairing = _text(detail.get("pairing") or detail.get("pairings"))

    try:
        period = _unwrap(_get(session, f"/drinking-periods/{int(wine_id)}", api_key,
                              lang, params={"lang": lang}, verify=verify))
        if isinstance(period, dict):
            period = period.get("drinking_period", period) or {}
            d_from = int(period["from"]) if period.get("from") is not None else None
            d_to = int(period["to"]) if period.get("to") is not None else None
            if (d_from or 0) >= 1900 or (d_to or 0) >= 1900:
                # absolute calendar years
                if d_from:
                    fields["drink_from"] = d_from
                if d_to:
                    fields["drink_until"] = d_to
            elif d_from is not None or d_to is not None:
                # years after the vintage, e.g. 6-18
                fields["drink_offset"] = [d_from, d_to]
                if vintage:
                    fields.update(drinking_years(vintage, [d_from, d_to]))
            storage = (period.get("storage") or "").strip()
            if storage:
                notes.append(storage)
    except (GrapemindsError, TypeError, ValueError):
        pass

    if pairing:
        notes.append(("Passt zu: " if lang == "de" else "Pairs with: ") + pairing)
    fields["notes"] = "\n\n".join(notes)
    fields["grapeminds_id"] = detail.get("id", wine_id)
    return {k: v for k, v in fields.items() if v not in (None, "", [])}


def drinking_years(vintage, offset):
    """Turn a relative drinking window (years after vintage) into years."""
    out = {}
    try:
        v = int(vintage)
    except (TypeError, ValueError):
        return out
    if not offset or v < 1900:
        return out
    lo, hi = (list(offset) + [None, None])[:2]
    if lo is not None:
        out["drink_from"] = v + int(lo)
    if hi is not None:
        out["drink_until"] = v + int(hi)
    return out


# ── Merging the three sources ────────────────────────────────────────────────

# Which source is trusted most for each form field, best first.
#  ai_label  = facts the AI read off the label (vintage, alcohol, size)
#  ai        = AI estimates (drinking window, taste, pairings, ...)
FIELD_PRIORITY = {
    "name":          ("grapeminds", "ai_label", "vivino"),
    "producer":      ("grapeminds", "ai_label", "vivino"),
    "vintage":       ("ai_label", "vivino", "grapeminds"),
    "wine_type":     ("grapeminds", "vivino", "ai_label"),
    "region":        ("grapeminds", "vivino", "ai_label"),
    "grape":         ("grapeminds", "vivino", "ai_label"),
    "alcohol_pct":   ("ai_label",),
    "bottle_format": ("ai_label",),
    "drink_from":    ("grapeminds", "ai"),
    "drink_until":   ("grapeminds", "ai"),
    "notes":         ("grapeminds", "ai"),
    "taste_profile": ("grapeminds", "ai"),
    "food_pairings": ("ai",),
    "maturity_data": ("ai",),
    "price":         ("vivino", "ai_label"),
    "rating":        ("vivino",),
    "drink_offset":  ("grapeminds",),
}

# Fields the AI reads directly from the label (everything else it estimates).
_AI_LABEL_FIELDS = {"name", "producer", "vintage", "wine_type", "region",
                    "grape", "alcohol_pct", "bottle_format", "price"}


def vivino_fields(item):
    """Convert one /api/vivino-search result into form fields."""
    if not isinstance(item, dict):
        return {}
    out = {
        "name": item.get("name"),
        "vintage": item.get("year"),
        "wine_type": item.get("wine_type"),
        "region": item.get("region"),
        "grape": item.get("grape"),
        "price": item.get("price"),
        "rating": item.get("rating"),
    }
    return {k: v for k, v in out.items() if v not in (None, "", [])}


def merge(ai=None, grapeminds=None, vivino=None):
    """Merge per-source field dicts by FIELD_PRIORITY.

    Returns (fields, sources) where sources maps each field to the source
    it was taken from ("ai" for estimates, "label" for label facts).
    """
    ai = ai or {}
    pools = {
        "grapeminds": grapeminds or {},
        "vivino": vivino or {},
        "ai_label": {k: v for k, v in ai.items() if k in _AI_LABEL_FIELDS},
        "ai": {k: v for k, v in ai.items() if k not in _AI_LABEL_FIELDS},
    }
    # A relative grapeminds drinking window becomes absolute once the
    # vintage of *this* bottle is known (label beats grapeminds' own guess).
    gm_pool = pools["grapeminds"]
    offset = gm_pool.get("drink_offset")
    if offset:
        vintage = (pools["ai_label"].get("vintage") or pools["vivino"].get("vintage")
                   or gm_pool.get("vintage"))
        gm_pool = dict(gm_pool)
        gm_pool.pop("drink_from", None)
        gm_pool.pop("drink_until", None)
        gm_pool.update(drinking_years(vintage, offset))
        pools["grapeminds"] = gm_pool

    fields, sources = {}, {}
    for field, order in FIELD_PRIORITY.items():
        for src in order:
            val = pools[src].get(field)
            if val not in (None, "", [], {}):
                fields[field] = val
                sources[field] = "label" if src == "ai_label" else src
                break
    return fields, sources
