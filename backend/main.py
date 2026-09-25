import os
import sqlite3
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from database import get_db, init_db
import models
import schemas
import trust

init_db()

app = FastAPI(
    title="DoorStep Trust Network API",
    description=(
        "A community-verification layer on top of Google's Plus Codes. "
        "Households register a Plus Code; neighbours vouch for it; the "
        "resulting trust score helps a delivery rider, ambulance driver, "
        "or new visitor sanity-check an address before travelling there."
    ),
    version="1.0.0",
)

allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in allowed_origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _to_household_out(conn: sqlite3.Connection, household: dict) -> schemas.HouseholdOut:
    vouches = models.list_vouches(conn, household["id"])
    count = len(vouches)
    return schemas.HouseholdOut(
        id=household["id"],
        name=household["name"],
        locality=household["locality"],
        plus_code=household["plus_code"],
        landmark=household["landmark"],
        latitude=household["latitude"],
        longitude=household["longitude"],
        created_at=household["created_at"],
        vouch_count=count,
        trust_score=trust.trust_score(count),
        trust_tier=trust.trust_tier(count),
        vouches=vouches,
    )


@app.get("/", tags=["meta"])
def root():
    return {
        "service": "doorstep-trust-network-api",
        "status": "ok",
        "docs": "/docs",
    }


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}


@app.post(
    "/households",
    response_model=schemas.HouseholdOut,
    status_code=201,
    tags=["households"],
)
def create_household(payload: schemas.HouseholdCreate, conn: sqlite3.Connection = Depends(get_db)):
    coords = trust.decode_plus_code(payload.plus_code)
    if coords is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "That doesn't look like a valid full Plus Code. Full codes "
                "look like '7JVW52GR+2Q' (8-11 characters, includes a '+'). "
                "Generate one for free at plus.codes or in Google Maps."
            ),
        )

    existing = models.get_household_by_plus_code(conn, payload.plus_code)
    if existing:
        raise HTTPException(
            status_code=409,
            detail="A household is already registered with this Plus Code.",
        )

    lat, lng = coords
    household = models.create_household(
        conn,
        name=payload.name.strip(),
        locality=payload.locality.strip(),
        plus_code=payload.plus_code,
        landmark=(payload.landmark or "").strip() or None,
        phone=(payload.phone or "").strip() or None,
        latitude=lat,
        longitude=lng,
    )
    return _to_household_out(conn, household)


@app.get("/households", response_model=List[schemas.HouseholdSummary], tags=["households"])
def list_households(
    locality: Optional[str] = Query(None, description="Filter by locality (partial match)"),
    conn: sqlite3.Connection = Depends(get_db),
):
    households = models.list_households(conn, locality)
    result = []
    for h in households:
        count = len(models.list_vouches(conn, h["id"]))
        result.append(
            schemas.HouseholdSummary(
                id=h["id"],
                name=h["name"],
                locality=h["locality"],
                plus_code=h["plus_code"],
                vouch_count=count,
                trust_score=trust.trust_score(count),
                trust_tier=trust.trust_tier(count),
            )
        )
    return result


def _get_household_or_404(plus_code: str, conn: sqlite3.Connection) -> dict:
    household = models.get_household_by_plus_code(conn, plus_code.strip().upper())
    if not household:
        raise HTTPException(
            status_code=404,
            detail="No household is registered with that Plus Code yet.",
        )
    return household


@app.get(
    "/households/{plus_code}",
    response_model=schemas.HouseholdOut,
    tags=["households"],
)
def get_household(plus_code: str, conn: sqlite3.Connection = Depends(get_db)):
    return _to_household_out(conn, _get_household_or_404(plus_code, conn))


@app.post(
    "/households/{plus_code}/vouch",
    response_model=schemas.HouseholdOut,
    tags=["households"],
)
def vouch_for_household(
    plus_code: str, payload: schemas.VouchCreate, conn: sqlite3.Connection = Depends(get_db)
):
    household = _get_household_or_404(plus_code, conn)
    existing_vouches = models.list_vouches(conn, household["id"])

    for v in existing_vouches:
        same_phone = payload.voucher_phone and v["voucher_phone"] == payload.voucher_phone
        same_name_no_phone = not payload.voucher_phone and v["voucher_name"].lower() == payload.voucher_name.strip().lower()
        if same_phone or same_name_no_phone:
            raise HTTPException(
                status_code=409,
                detail="This person has already vouched for this household.",
            )

    models.create_vouch(
        conn,
        household_id=household["id"],
        voucher_name=payload.voucher_name.strip(),
        voucher_phone=(payload.voucher_phone or "").strip() or None,
        relation=payload.relation.strip(),
        note=(payload.note or "").strip() or None,
    )
    return _to_household_out(conn, household)


@app.get(
    "/trust-score/{plus_code}",
    response_model=schemas.HouseholdSummary,
    tags=["households"],
)
def quick_trust_check(plus_code: str, conn: sqlite3.Connection = Depends(get_db)):
    h = _get_household_or_404(plus_code, conn)
    count = len(models.list_vouches(conn, h["id"]))
    return schemas.HouseholdSummary(
        id=h["id"],
        name=h["name"],
        locality=h["locality"],
        plus_code=h["plus_code"],
        vouch_count=count,
        trust_score=trust.trust_score(count),
        trust_tier=trust.trust_tier(count),
    )


@app.post("/sms/simulate", response_model=schemas.SmsSimulateResponse, tags=["offline-fallback"])
def simulate_sms(payload: schemas.SmsSimulateRequest, conn: sqlite3.Connection = Depends(get_db)):
    text = payload.message.strip()
    parts = text.split()

    if len(parts) < 2 or parts[0].upper() != "TRUST":
        return schemas.SmsSimulateResponse(
            reply="Send: TRUST <PlusCode>  e.g. TRUST 7JVW52GR+2Q"
        )

    code = parts[1].strip().upper()
    if not trust.is_valid_full_plus_code(code):
        return schemas.SmsSimulateResponse(
            reply=f"'{code}' isn't a valid Plus Code. Full codes include a '+', e.g. 7JVW52GR+2Q."
        )

    household = models.get_household_by_plus_code(conn, code)

    if not household:
        return schemas.SmsSimulateResponse(
            reply=f"No record for {code} yet. Travel with normal caution."
        )

    count = len(models.list_vouches(conn, household["id"]))
    tier = trust.trust_tier(count)
    reply = (
        f"{code}: {household['name']}, {household['locality']}. "
        f"Trust: {tier} ({count} vouch{'es' if count != 1 else ''})."
    )
    return schemas.SmsSimulateResponse(reply=reply)
