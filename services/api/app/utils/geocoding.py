"""Google Geocoding with cache, spelled-out/digit cross-check and PT-BR errors.

Design rules:

* The app must boot and stay healthy without ``GOOGLE_MAPS_API_KEY`` — geocoding
  simply reports a failure, so deploying before configuring the key is safe.
* The user never sees an HTTP status, an API name or a stack trace. Technical
  detail goes to the server log; she gets one of the messages in ``Messages``.
* The cache is checked before every paid call, and a manual pin correction
  overwrites whatever Google said.
"""

import logging
import os
from typing import Any, Optional

import httpx
from sqlalchemy.orm import Session

from ..models import (
    GEOCODE_CONFIRMED,
    GEOCODE_FAILED,
    GEOCODE_NEEDS_CONFIRMATION,
    GEOCODE_RESOLVED,
    GeocodeCache,
)
from ..schemas import GeocodeResult
from .address_normalizer import normalize_address_key, street_with_digits
from .optimization import haversine

logger = logging.getLogger(__name__)

GOOGLE_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"

# Local tool: the city is fixed. Change these two constants to move cities.
CITY = "Vilhena"
STATE = "RO"
COUNTRY = "Brasil"

# Two results further apart than this mean the address is ambiguous and a human
# has to look at the map.
CROSS_CHECK_THRESHOLD_M = 50

GEOCODE_TIMEOUT_SECONDS = float(os.getenv("GEOCODE_TIMEOUT_SECONDS", "10"))

# Google precision levels we trust without asking the user.
HIGH_CONFIDENCE_LOCATION_TYPES = ("ROOFTOP", "RANGE_INTERPOLATED")
# Ranking used when two queries agree but with different precision.
_LOCATION_TYPE_RANK = {
    "ROOFTOP": 3,
    "RANGE_INTERPOLATED": 2,
    "GEOMETRIC_CENTER": 1,
    "APPROXIMATE": 0,
}


class Messages:
    """Every string here is shown as-is to the user."""

    NOT_CONFIGURED = "Busca de endereços não configurada"
    STREET_NOT_FOUND = "Rua não encontrada"
    NEIGHBORHOOD_NOT_FOUND = "Bairro não encontrado"
    ADDRESS_NOT_FOUND = "Endereço não localizado — confira os dados"
    BAD_CEP = "CEP pode estar incorreto — confira o endereço"
    DIVERGENT = "Dois resultados diferentes — confirme no mapa"
    APPROXIMATE = "Endereço aproximado — confirme no mapa"
    UNAVAILABLE = "Não foi possível localizar agora"


def get_api_key() -> str:
    """Read at call time (not import time) so tests and deploys can set it late."""
    return os.getenv("GOOGLE_MAPS_API_KEY", "")


def build_query(
    street: str,
    number: str,
    neighborhood: str,
    cep: Optional[str] = None,
) -> str:
    parts = [f"{street} {number}".strip(), neighborhood, CITY, STATE, COUNTRY]
    if cep:
        parts.insert(2, f"CEP {cep}")
    return ", ".join(part for part in parts if part)


async def _call_google(query: str, client: httpx.AsyncClient) -> dict[str, Any]:
    """Raw Google call. Returns the decoded payload or a synthetic error status."""
    try:
        response = await client.get(
            GOOGLE_GEOCODE_URL,
            params={"address": query, "key": get_api_key(), "region": "br"},
            timeout=GEOCODE_TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            logger.warning(
                "Google Geocoding HTTP %s for %r: %s",
                response.status_code,
                query,
                response.text[:200],
            )
            return {"status": "HTTP_ERROR"}
        return response.json()
    except Exception as exc:  # timeout, DNS, invalid JSON...
        logger.warning("Google Geocoding call failed for %r: %s", query, exc)
        return {"status": "NETWORK_ERROR"}


def _first_result(payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    results = payload.get("results") or []
    return results[0] if results else None


def _candidate_from_payload(payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Flatten a Google payload into {latitude, longitude, location_type, partial}."""
    result = _first_result(payload)
    if not result:
        return None

    location = (result.get("geometry") or {}).get("location") or {}
    if location.get("lat") is None or location.get("lng") is None:
        return None

    return {
        "latitude": float(location["lat"]),
        "longitude": float(location["lng"]),
        "location_type": (result.get("geometry") or {}).get("location_type", ""),
        "partial_match": bool(result.get("partial_match")),
    }


def _is_high_confidence(candidate: dict[str, Any]) -> bool:
    return (
        not candidate["partial_match"]
        and candidate["location_type"] in HIGH_CONFIDENCE_LOCATION_TYPES
    )


async def _diagnose_failure(
    neighborhood: str, cep: Optional[str], client: httpx.AsyncClient
) -> str:
    """Tell street-level from neighborhood-level failure, for a useful message.

    One extra call, only on the failure path: if the neighborhood alone
    geocodes, the street is what Google could not find.
    """
    if not neighborhood:
        return Messages.ADDRESS_NOT_FOUND

    payload = await _call_google(
        f"{neighborhood}, {CITY}, {STATE}, {COUNTRY}", client
    )
    if payload.get("status") == "OK" and _first_result(payload):
        return Messages.BAD_CEP if cep else Messages.STREET_NOT_FOUND
    return Messages.NEIGHBORHOOD_NOT_FOUND


async def _geocode_query(
    query: str, client: httpx.AsyncClient
) -> tuple[Optional[dict[str, Any]], str]:
    """Returns (candidate, google_status)."""
    payload = await _call_google(query, client)
    status = payload.get("status", "UNKNOWN")
    if status != "OK":
        return None, status
    return _candidate_from_payload(payload), status


async def geocode_address(
    street: str,
    number: str,
    neighborhood: str,
    cep: Optional[str] = None,
    complement: Optional[str] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> GeocodeResult:
    """Geocode one address, cross-checking spelled-out vs numeric street names."""
    if not get_api_key():
        logger.info("GOOGLE_MAPS_API_KEY not set — skipping geocoding")
        return GeocodeResult(status=GEOCODE_FAILED, message=Messages.NOT_CONFIGURED)

    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=GEOCODE_TIMEOUT_SECONDS)
    try:
        candidate, status = await _geocode_query(
            build_query(street, number, neighborhood, cep), client
        )

        # A wrong CEP is a common cause of ZERO_RESULTS — retry without it.
        retried_without_cep = False
        if candidate is None and status == "ZERO_RESULTS" and cep:
            retried_without_cep = True
            candidate, status = await _geocode_query(
                build_query(street, number, neighborhood, None), client
            )

        if candidate is None and status not in ("ZERO_RESULTS", "OK"):
            # OVER_QUERY_LIMIT / REQUEST_DENIED / INVALID_REQUEST / network
            logger.error("Geocoding unavailable (google status=%s)", status)
            return GeocodeResult(
                status=GEOCODE_FAILED, message=Messages.UNAVAILABLE
            )

        # Cross-check only exists to disambiguate spelled-out street numbers.
        digit_variant = street_with_digits(street)
        variant_candidate = None
        if digit_variant:
            variant_candidate, _ = await _geocode_query(
                build_query(digit_variant, number, neighborhood, None if retried_without_cep else cep),
                client,
            )

        if candidate and variant_candidate:
            distance_m = (
                haversine(
                    candidate["latitude"],
                    candidate["longitude"],
                    variant_candidate["latitude"],
                    variant_candidate["longitude"],
                )
                * 1000
            )
            if distance_m > CROSS_CHECK_THRESHOLD_M:
                best = candidate  # show the original spelling first
                return GeocodeResult(
                    latitude=best["latitude"],
                    longitude=best["longitude"],
                    status=GEOCODE_NEEDS_CONFIRMATION,
                    source="google",
                    message=Messages.DIVERGENT,
                    alternatives=[
                        {
                            "latitude": candidate["latitude"],
                            "longitude": candidate["longitude"],
                        },
                        {
                            "latitude": variant_candidate["latitude"],
                            "longitude": variant_candidate["longitude"],
                        },
                    ],
                )

            # They agree: keep the more precise of the two.
            best = max(
                (candidate, variant_candidate),
                key=lambda item: _LOCATION_TYPE_RANK.get(item["location_type"], 0),
            )
            return GeocodeResult(
                latitude=best["latitude"],
                longitude=best["longitude"],
                status=GEOCODE_RESOLVED,
                source="google",
            )

        winner = candidate or variant_candidate
        if winner is None:
            message = (
                Messages.BAD_CEP
                if retried_without_cep
                else await _diagnose_failure(neighborhood, cep, client)
            )
            return GeocodeResult(status=GEOCODE_FAILED, message=message)

        if _is_high_confidence(winner):
            return GeocodeResult(
                latitude=winner["latitude"],
                longitude=winner["longitude"],
                status=GEOCODE_RESOLVED,
                source="google",
            )

        return GeocodeResult(
            latitude=winner["latitude"],
            longitude=winner["longitude"],
            status=GEOCODE_NEEDS_CONFIRMATION,
            source="google",
            message=Messages.APPROXIMATE,
        )
    finally:
        if owns_client:
            await client.aclose()


# ------------------------------------------------------------------- cache


def lookup_cache(
    db: Session, street: str, number: str, neighborhood: str
) -> Optional[GeocodeCache]:
    key = normalize_address_key(street, number, neighborhood, CITY)
    return db.query(GeocodeCache).filter(GeocodeCache.address_key == key).first()


def save_to_cache(
    db: Session,
    street: str,
    number: str,
    neighborhood: str,
    latitude: float,
    longitude: float,
    source: str,
) -> GeocodeCache:
    """Upsert. A ``manual`` entry always wins over a ``google`` one."""
    key = normalize_address_key(street, number, neighborhood, CITY)
    entry = db.query(GeocodeCache).filter(GeocodeCache.address_key == key).first()

    if entry is None:
        entry = GeocodeCache(
            address_key=key,
            latitude=latitude,
            longitude=longitude,
            source=source,
        )
        db.add(entry)
        return entry

    if entry.source == "manual" and source != "manual":
        return entry  # never downgrade a human correction

    entry.latitude = latitude
    entry.longitude = longitude
    entry.source = source
    return entry


async def resolve_address(
    db: Session,
    street: str,
    number: str,
    neighborhood: str,
    cep: Optional[str] = None,
    complement: Optional[str] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> GeocodeResult:
    """Cache first, Google second. Successful results feed the cache back."""
    cached = lookup_cache(db, street, number, neighborhood)
    if cached:
        return GeocodeResult(
            latitude=cached.latitude,
            longitude=cached.longitude,
            status=(
                GEOCODE_CONFIRMED if cached.source == "manual" else GEOCODE_RESOLVED
            ),
            source="cache",
        )

    result = await geocode_address(
        street, number, neighborhood, cep, complement, client=client
    )

    if result.status == GEOCODE_RESOLVED and result.latitude is not None:
        save_to_cache(
            db,
            street,
            number,
            neighborhood,
            result.latitude,
            result.longitude,
            source="google",
        )

    return result
