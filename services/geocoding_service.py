# -*- coding: utf-8 -*-
"""
services/geocoding_service.py
ThirdEye Forensic Platform — Location Geocoding & Reverse Geocoding Service
==========================================================================
Provides forward place searching and reverse coordinate-to-address geocoding
utilizing OpenStreetMap Nominatim with caching, rate-limit compliance, and
high-precision institutional landmark recognition for Karnataka / Vijayapura.
"""

import time
import math
import logging
import requests

logger = logging.getLogger('thirdeye.geocoding')

# Rate limit tracking (Nominatim requires max 1 req/sec)
_LAST_REQUEST_TIME = 0.0
_MIN_REQUEST_INTERVAL = 1.2  # seconds (Nominatim rate limit compliance)

# In-memory LRU-like caches
_SEARCH_CACHE = {}
_REVERSE_CACHE = {}
_MAX_CACHE_SIZE = 200

NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "ThirdEye-Forensic-Investigation-System/1.0 (contact: ise.javaji@bldeacet.ac.in)"

# Curated High-Accuracy Institutional & Regional Landmarks
LOCAL_LANDMARKS = [
    {
        "keywords": [
            "bldea", "blde", "halakatti", "bldeacet", "bldea college",
            "dr pg halakatti", "v.p. dr. p.g.", "bldea's"
        ],
        "display_name": "BLDEA's V.P. Dr. P.G. Halakatti College of Engineering and Technology, Ashram Road, Vijayapura, Karnataka, India",
        "short_name": "BLDEACET Engineering College",
        "lat": 16.825200,
        "lon": 75.719600,
        "type": "college",
        "importance": 0.95
    },
    {
        "keywords": ["ashram road", "ashram road vijayapura", "ashram rd"],
        "display_name": "Ashram Road, Vijayapura, Karnataka 586103, India",
        "short_name": "Ashram Road",
        "lat": 16.826000,
        "lon": 75.719000,
        "type": "road",
        "importance": 0.85
    },
    {
        "keywords": ["gol gumbaz", "gol gumbaz vijayapura", "gol gumbadh"],
        "display_name": "Gol Gumbaz, Station Road, Vijayapura, Karnataka 586101, India",
        "short_name": "Gol Gumbaz Monument",
        "lat": 16.829626,
        "lon": 75.736010,
        "type": "monument",
        "importance": 0.90
    },
    {
        "keywords": ["ibrahim rauza", "ibrahim roza"],
        "display_name": "Ibrahim Rauza, Taj Bawdi Road, Vijayapura, Karnataka 586101, India",
        "short_name": "Ibrahim Rauza",
        "lat": 16.824700,
        "lon": 75.698900,
        "type": "monument",
        "importance": 0.88
    },
    {
        "keywords": ["blde hospital", "bm patil medical college", "shri b.m. patil"],
        "display_name": "BLDE University Shri B.M. Patil Medical College & Hospital, Bangaramma Sajjan Campus, Solapur Road, Vijayapura, Karnataka, India",
        "short_name": "B.M. Patil Medical College",
        "lat": 16.832000,
        "lon": 75.704000,
        "type": "hospital",
        "importance": 0.89
    },
    {
        "keywords": ["sainik school vijayapura", "sainik school"],
        "display_name": "Sainik School, Shastri Nagar, Vijayapura, Karnataka 586102, India",
        "short_name": "Sainik School",
        "lat": 16.815000,
        "lon": 75.740000,
        "type": "school",
        "importance": 0.82
    },
    {
        "keywords": ["vijayapura railway station", "bijapur railway station"],
        "display_name": "Vijayapura Railway Station, Station Road, Yogapur, Vijayapura, Karnataka 586101, India",
        "short_name": "Vijayapura Railway Station",
        "lat": 16.819000,
        "lon": 75.732000,
        "type": "station",
        "importance": 0.84
    }
]

# Major Regional Urban Centers & Centroids for Offline / Fallback Reverse Geocoding
REGIONAL_CENTROIDS = [
    {
        "keywords": ["solapur", "sholapur"],
        "name": "Solapur",
        "display_name": "Solapur, Maharashtra, India",
        "short_name": "Solapur",
        "lat": 17.659900,
        "lon": 75.906400,
        "radius_m": 25000,
        "type": "city"
    },
    {
        "keywords": ["jammu", "jammu city", "jammu tawi"],
        "name": "Jammu",
        "display_name": "Jammu, Jammu and Kashmir, India",
        "short_name": "Jammu",
        "lat": 32.726600,
        "lon": 74.857000,
        "radius_m": 25000,
        "type": "city"
    },
    {
        "keywords": ["vijayapura", "bijapur"],
        "name": "Vijayapura",
        "display_name": "Vijayapura, Karnataka, India",
        "short_name": "Vijayapura",
        "lat": 16.830200,
        "lon": 75.710000,
        "radius_m": 20000,
        "type": "city"
    },
    {
        "keywords": ["belagavi", "belgaum"],
        "name": "Belagavi",
        "display_name": "Belagavi, Karnataka, India",
        "short_name": "Belagavi",
        "lat": 15.849700,
        "lon": 74.497700,
        "radius_m": 20000,
        "type": "city"
    },
    {
        "keywords": ["hubballi", "hubli", "dharwad"],
        "name": "Hubballi",
        "display_name": "Hubballi-Dharwad, Karnataka, India",
        "short_name": "Hubballi",
        "lat": 15.364700,
        "lon": 75.124000,
        "radius_m": 20000,
        "type": "city"
    },
    {
        "keywords": ["bengaluru", "bangalore"],
        "name": "Bengaluru",
        "display_name": "Bengaluru, Karnataka, India",
        "short_name": "Bengaluru",
        "lat": 12.971600,
        "lon": 77.594600,
        "radius_m": 35000,
        "type": "city"
    }
]


def _throttle_request():
    """Ensures at least 1 second interval between Nominatim HTTP requests."""
    global _LAST_REQUEST_TIME
    now = time.time()
    elapsed = now - _LAST_REQUEST_TIME
    if elapsed < _MIN_REQUEST_INTERVAL:
        time.sleep(_MIN_REQUEST_INTERVAL - elapsed)
    _LAST_REQUEST_TIME = time.time()


def _haversine_distance_m(lat1, lon1, lat2, lon2):
    """Calculates great-circle distance in meters between two lat/lon points."""
    R = 6371000.0  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + \
        math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


def search_locations(query, limit=5):
    """
    Searches for locations matching the given query string.
    Returns a list of dicts:
    [
        {
            "display_name": str,
            "short_name": str,
            "lat": float,
            "lon": float,
            "type": str,
            "source": "local" | "nominatim"
        },
        ...
    ]
    """
    if not query or not query.strip():
        return []

    clean_q = query.strip()
    cache_key = clean_q.lower()
    if cache_key in _SEARCH_CACHE:
        return _SEARCH_CACHE[cache_key]

    results = []

    # 1. Match against Curated Local Institutional Landmarks & Regional Hubs
    clean_lower = clean_q.lower()
    for landmark in LOCAL_LANDMARKS:
        for kw in landmark["keywords"]:
            if kw in clean_lower or clean_lower in kw:
                results.append({
                    "display_name": landmark["display_name"],
                    "short_name": landmark["short_name"],
                    "lat": landmark["lat"],
                    "lon": landmark["lon"],
                    "type": landmark["type"],
                    "source": "local"
                })
                break
        if len(results) >= limit:
            break

    # Also match regional centroids if query aligns
    for centroid in REGIONAL_CENTROIDS:
        for kw in centroid["keywords"]:
            if kw == clean_lower or clean_lower in kw:
                # Deduplicate if already present
                if not any(r["short_name"].lower() == centroid["short_name"].lower() for r in results):
                    results.append({
                        "display_name": centroid["display_name"],
                        "short_name": centroid["short_name"],
                        "lat": centroid["lat"],
                        "lon": centroid["lon"],
                        "type": centroid["type"],
                        "source": "regional"
                    })
                break
        if len(results) >= limit:
            break

    # 2. Query OpenStreetMap Nominatim for Indian & Global Addresses
    try:
        _throttle_request()
        headers = {"User-Agent": USER_AGENT}
        params = {
            "q": clean_q,
            "format": "json",
            "addressdetails": 1,
            "limit": limit
        }
        resp = requests.get(NOMINATIM_SEARCH_URL, params=params, headers=headers, timeout=8)
        if resp.status_code == 200:
            osm_items = resp.json()
            for item in osm_items:
                try:
                    lat_f = float(item.get("lat"))
                    lon_f = float(item.get("lon"))
                    d_name = item.get("display_name", "")
                    addr = item.get("address", {})
                    # Build a concise short name
                    short_name = (
                        addr.get("city") or
                        addr.get("town") or
                        addr.get("village") or
                        addr.get("suburb") or
                        addr.get("county") or
                        d_name.split(",")[0]
                    )

                    # Deduplicate if very close to already matched landmark
                    is_duplicate = False
                    for r in results:
                        if _haversine_distance_m(lat_f, lon_f, r["lat"], r["lon"]) < 200:
                            is_duplicate = True
                            break

                    if not is_duplicate:
                        results.append({
                            "display_name": d_name,
                            "short_name": short_name,
                            "lat": lat_f,
                            "lon": lon_f,
                            "type": item.get("type", "location"),
                            "source": "nominatim"
                        })
                except (ValueError, TypeError):
                    continue
    except Exception as e:
        logger.warning(f"Nominatim search failed for '{clean_q}': {e}")

    # Cache result
    if len(_SEARCH_CACHE) >= _MAX_CACHE_SIZE:
        _SEARCH_CACHE.pop(next(iter(_SEARCH_CACHE)))
    _SEARCH_CACHE[cache_key] = results[:limit]
    return results[:limit]


def reverse_geocode(lat, lon):
    """
    Converts latitude and longitude coordinates into a complete readable address.
    Returns:
    {
        "display_name": str,
        "lat": float,
        "lon": float,
        "source": "local_proximity" | "nominatim" | "fallback"
    }
    """
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (ValueError, TypeError):
        return {
            "display_name": "Invalid coordinates",
            "lat": 0.0,
            "lon": 0.0,
            "source": "error"
        }

    cache_key = f"{round(lat_f, 5)},{round(lon_f, 5)}"
    if cache_key in _REVERSE_CACHE:
        return _REVERSE_CACHE[cache_key]

    # 1. Proximity check to known institutional landmarks (e.g. BLDEA CET within 350m)
    for landmark in LOCAL_LANDMARKS:
        dist = _haversine_distance_m(lat_f, lon_f, landmark["lat"], landmark["lon"])
        if dist <= 350.0:
            res = {
                "display_name": landmark["display_name"],
                "lat": lat_f,
                "lon": lon_f,
                "source": "local_proximity",
                "distance_m": round(dist, 1)
            }
            _REVERSE_CACHE[cache_key] = res
            return res

    # 2. Query Nominatim Reverse Geocoding
    try:
        _throttle_request()
        headers = {"User-Agent": USER_AGENT}
        params = {
            "lat": lat_f,
            "lon": lon_f,
            "format": "json",
            "addressdetails": 1
        }
        resp = requests.get(NOMINATIM_REVERSE_URL, params=params, headers=headers, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            d_name = data.get("display_name")
            if d_name:
                res = {
                    "display_name": d_name,
                    "lat": lat_f,
                    "lon": lon_f,
                    "source": "nominatim"
                }
                if len(_REVERSE_CACHE) >= _MAX_CACHE_SIZE:
                    _REVERSE_CACHE.pop(next(iter(_REVERSE_CACHE)))
                _REVERSE_CACHE[cache_key] = res
                return res
    except Exception as e:
        logger.warning(f"Nominatim reverse geocode failed for ({lat_f}, {lon_f}): {e}")

    # 3. Check proximity to Regional Urban Centroids (if Nominatim is slow/unreachable)
    for centroid in REGIONAL_CENTROIDS:
        dist = _haversine_distance_m(lat_f, lon_f, centroid["lat"], centroid["lon"])
        if dist <= centroid.get("radius_m", 20000):
            res = {
                "display_name": f"{centroid['display_name']} ({lat_f:.4f}°N, {lon_f:.4f}°E)",
                "lat": lat_f,
                "lon": lon_f,
                "source": "regional_proximity",
                "distance_m": round(dist, 1)
            }
            _REVERSE_CACHE[cache_key] = res
            return res

    # 4. Fallback for coordinates far from mapped regional centers
    fallback_name = f"Location at {lat_f:.6f}°N, {lon_f:.6f}°E"
    res = {
        "display_name": fallback_name,
        "lat": lat_f,
        "lon": lon_f,
        "source": "fallback"
    }
    return res
