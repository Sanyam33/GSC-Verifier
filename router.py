import os, requests
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, Request, Query, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from urllib.parse import urlencode, quote
from sqlalchemy import text
from models import GSCVerification
from schemas import GSCVerificationCreate, GSCVerificationResult
from db import get_db
from typing import List, Optional

load_dotenv()
gsc_router = APIRouter(prefix="/api/v1/gsc", tags=["GSC"])

TOKEN_URL = "https://oauth2.googleapis.com/token"
GSC_SITES_URL = "https://www.googleapis.com/webmasters/v3/sites"

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
SCOPE = "https://www.googleapis.com/auth/webmasters.readonly openid email"

CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")


def normalize_site(url: str) -> str:
    return (
        url.replace("https://", "")
           .replace("http://", "")
           .replace("sc-domain:", "")
           .replace("www.", "")
           .rstrip("/")
           .lower()
    )


@gsc_router.post("/request-verification")
def request_gsc_verification(
    data: GSCVerificationCreate,
    db: Session = Depends(get_db)
):

    # cleanup old unverified
    db.execute(text("""
    DELETE FROM gsc_verifications
    WHERE verified = false
    AND created_at < NOW() - INTERVAL '15 minutes'
    """))
    db.commit()

    clean_site = normalize_site(str(data.site_url))
    # clean_site = str(data.site_url)
    # create DB record
    record = GSCVerification(
        site_url=clean_site,
        verified=False
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    # state = record id (safe + simple)
    state = str(record.id)

    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state
    }

    auth_url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    return {"auth_url": auth_url}

########################################################

@gsc_router.get("/callback")
def gsc_callback(request: Request, db: Session = Depends(get_db)):
    # 1. Handle user denying consent
    error = request.query_params.get("error")
    if error:
        state = request.query_params.get("state")
        record = db.query(GSCVerification).filter(GSCVerification.id == state).first()
        if record:
            record.verified = False
            db.commit()
        return {"status": "failed", "reason": error}

    code = request.query_params.get("code")
    state = request.query_params.get("state")  # our DB record id

    if not code or not state:
        return {"status": "failed", "reason": "Missing code or state"}

    # 2. Find DB record
    record = db.query(GSCVerification).filter(GSCVerification.id == state).first()
    if not record:
        return {"status": "failed", "reason": "Invalid state"}

    # 3. Exchange code for token
    token_res = requests.post(
        TOKEN_URL,
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    token_data = token_res.json()

    if "access_token" not in token_data:
        return {"status": "failed", "reason": "Token exchange failed", "data": token_data}

    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token")

    # 4. Call GSC API
    sites_res = requests.get(
        GSC_SITES_URL,
        headers={"Authorization": f"Bearer {access_token}"}
    )

    sites_data = sites_res.json()

    if "siteEntry" not in sites_data:
        return {"status": "failed", "reason": "No sites found", "data": sites_data}

    # 5. Check ownership
    requested = normalize_site(record.site_url)

    verified = False
    permission_level = None

    for site in sites_data["siteEntry"]:
        google_site = normalize_site(site["siteUrl"])
        if google_site == requested:
            permission_level = site["permissionLevel"]
            if permission_level in ["siteOwner", "siteFullUser"]:
                verified = True
                record.site_url = site["siteUrl"]
            break

    # 6. Update DB
    record.verified = verified
    record.permission_level = permission_level
    record.access_token = access_token
    record.refresh_token = refresh_token

    db.commit()

    # 7. Redirect back to platform (optional)
    return {
        "requested_site": record.site_url,
        "google_sites": sites_data,
        "verified": verified,
        "permission_level": permission_level
    }


#############################################################

@gsc_router.get("/verify-result", response_model=GSCVerificationResult)
def get_verification_result(
    site_url: str = Query(...),
    db: Session = Depends(get_db)
):

    clean_site = normalize_site(site_url)

    record = (
        db.query(GSCVerification)
        .filter(GSCVerification.site_url == clean_site)
        .order_by(GSCVerification.created_at.desc())
        .first()
    )

    if not record:
        raise HTTPException(status_code=404, detail="Verification record not found")

    return {
        "site_url": record.site_url,
        "verified": record.verified,
        "permission_level": record.permission_level
    }

####################################################

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GSC_QUERY_URL = "https://www.googleapis.com/webmasters/v3/sites/{site_url}/searchAnalytics/query"

def get_access_token(refresh_token: str):
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token"
    }

    resp = requests.post(GOOGLE_TOKEN_URL, data=data)
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to refresh access token")

    return resp.json()["access_token"]



# @gsc_router.get("/metrics")
# def get_gsc_metrics(
#     site_url: str = Query(...),
#     start_date: str = Query(..., example="2026-01-01"),
#     end_date: str = Query(..., example="2026-02-01"),
#     db: Session = Depends(get_db)
# ):

#     # normalize incoming site
#     # site_url = normalize_site(site_url)

#     record = db.query(GSCVerification).filter(
#         GSCVerification.site_url == site_url,
#         GSCVerification.verified == True
#     ).first()


#     if not record:
#         # Fallback: try searching normalized if the exact match fails
#         # (Useful for transition periods)
#         clean = normalize_site(site_url)
#         record = db.query(GSCVerification).filter(
#             GSCVerification.site_url.contains(clean),
#             GSCVerification.verified == True
#         ).first()

#     if not record:
#         raise HTTPException(status_code=404, detail="Verified site not found")

#     access_token = get_access_token(record.refresh_token)

#     headers = {
#         "Authorization": f"Bearer {access_token}",
#         "Content-Type": "application/json"
#     }

#     body = {
#         "startDate": start_date,
#         "endDate": end_date,
#         "dimensions": ["query"],
#         "rowLimit": 50
#     }

#     # google_site = f"sc-domain:{record.site_url}"
#     # encoded_site = quote(google_site, safe="")    

#     encoded_site = quote(record.site_url, safe="")
#     url = GSC_QUERY_URL.format(site_url=encoded_site)

#     resp = requests.post(url, headers=headers, json=body)


#     if resp.status_code != 200:
#         raise HTTPException(status_code=400, detail=resp.text)

#     return resp.json()



@gsc_router.get("/metrics")
def get_gsc_metrics(
    site_url: str = Query(...),
    start_date: str = Query(..., example="2026-01-01"),
    end_date: str = Query(..., example="2026-02-01"),
    # New Dynamic Parameters
    dimensions: List[str] = Query(["query"], description="e.g. query, page, country, device, date"),
    search_type: str = Query("web", description="web, image, video, news, discover, googleNews"),
    row_limit: int = Query(50, ge=1, le=25000),
    db: Session = Depends(get_db)
):
    # 1. Database Lookup (keeping your robust search logic)
    record = db.query(GSCVerification).filter(
        GSCVerification.site_url == site_url,
        GSCVerification.verified == True
    ).first()

    if not record:
        clean = normalize_site(site_url)
        record = db.query(GSCVerification).filter(
            GSCVerification.site_url.contains(clean),
            GSCVerification.verified == True
        ).first()

    if not record:
        raise HTTPException(status_code=404, detail="Verified site not found")

    # 2. Token Refresh
    access_token = get_access_token(record.refresh_token)

    # 3. Dynamic Body Construction & Validation
    # Important: Discover and GoogleNews do not support the 'query' dimension
    final_dimensions = dimensions
    if search_type in ["discover", "googleNews"] and "query" in final_dimensions:
        final_dimensions = [d for d in final_dimensions if d != "query"]

    body = {
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": final_dimensions,
        "type": search_type,  # This handles web, image, video, etc.
        "rowLimit": row_limit
    }

    # 4. GSC API Call
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    encoded_site = quote(record.site_url, safe="")
    url = GSC_QUERY_URL.format(site_url=encoded_site)

    resp = requests.post(url, headers=headers, json=body)

    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail=resp.text)

    return resp.json()