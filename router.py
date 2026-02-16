import os, requests, httpx
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, Request, Query, HTTPException, status
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


# @gsc_router.post("/request-verification")
# def request_gsc_verification(
#     data: GSCVerificationCreate,
#     db: Session = Depends(get_db)
# ):

#     # cleanup old unverified
#     db.execute(text("""
#     DELETE FROM gsc_verifications
#     WHERE verified = false
#     AND created_at < NOW() - INTERVAL '15 minutes'
#     """))
#     db.commit()

#     clean_site = normalize_site(str(data.site_url))
#     # clean_site = str(data.site_url)
#     # create DB record
#     record = GSCVerification(
#         site_url=clean_site,
#         verified=False
#     )
#     db.add(record)
#     db.commit()
#     db.refresh(record)

#     # state = record id (safe + simple)
#     state = str(record.id)

#     params = {
#         "client_id": CLIENT_ID,
#         "redirect_uri": REDIRECT_URI,
#         "response_type": "code",
#         "scope": SCOPE,
#         "access_type": "offline",
#         "prompt": "consent",
#         "state": state
#     }

#     auth_url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

#     return {"auth_url": auth_url}


import logging

# Set up logging to catch DB errors in production
logger = logging.getLogger(__name__)

@gsc_router.post("/request-verification", status_code=status.HTTP_201_CREATED)
def request_gsc_verification(
    data: GSCVerificationCreate, 
    db: Session = Depends(get_db)
):
    try:
        db.execute(text("""
            DELETE FROM gsc_verifications 
            WHERE verified = false 
            AND created_at < NOW() - INTERVAL '15 minutes'
        """))
        
        # 2. Normalize and Prepare Record
        clean_site = normalize_site(str(data.site_url))
        
        new_record = GSCVerification(
            site_url=clean_site,
            verified=False
        )
        
        db.add(new_record)
        db.commit()
        db.refresh(new_record)

        # 3. Construct OAuth URL
        state = str(new_record.id)
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
        return {"auth_url": auth_url, "id": state}

    except exc.SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error during verification request: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initialize verification. Please try again later."
        )


########################################################

# @gsc_router.get("/callback")
# def gsc_callback(request: Request, db: Session = Depends(get_db)):
#     # 1. Handle user denying consent
#     error = request.query_params.get("error")
#     if error:
#         state = request.query_params.get("state")
#         record = db.query(GSCVerification).filter(GSCVerification.id == state).first()
#         if record:
#             record.verified = False
#             db.commit()
#         return {"status": "failed", "reason": error}

#     code = request.query_params.get("code")
#     state = request.query_params.get("state")  # our DB record id

#     if not code or not state:
#         return {"status": "failed", "reason": "Missing code or state"}

#     # 2. Find DB record
#     record = db.query(GSCVerification).filter(GSCVerification.id == state).first()
#     if not record:
#         return {"status": "failed", "reason": "Invalid state"}

#     # 3. Exchange code for token
#     token_res = requests.post(
#         TOKEN_URL,
#         data={
#             "client_id": CLIENT_ID,
#             "client_secret": CLIENT_SECRET,
#             "code": code,
#             "grant_type": "authorization_code",
#             "redirect_uri": REDIRECT_URI,
#         },
#         headers={"Content-Type": "application/x-www-form-urlencoded"},
#     )

#     token_data = token_res.json()

#     if "access_token" not in token_data:
#         return {"status": "failed", "reason": "Token exchange failed", "data": token_data}

#     access_token = token_data["access_token"]
#     refresh_token = token_data.get("refresh_token")

#     # 4. Call GSC API
#     sites_res = requests.get(
#         GSC_SITES_URL,
#         headers={"Authorization": f"Bearer {access_token}"}
#     )

#     sites_data = sites_res.json()

#     if "siteEntry" not in sites_data:
#         return {"status": "failed", "reason": "No sites found", "data": sites_data}

#     # 5. Check ownership
#     requested = normalize_site(record.site_url)

#     verified = False
#     permission_level = None

#     for site in sites_data["siteEntry"]:
#         google_site = normalize_site(site["siteUrl"])
#         if google_site == requested:
#             permission_level = site["permissionLevel"]
#             if permission_level in ["siteOwner", "siteFullUser"]:
#                 verified = True
#                 record.site_url = site["siteUrl"]
#             break

#     # 6. Update DB
#     record.verified = verified
#     record.permission_level = permission_level
#     record.access_token = access_token
#     record.refresh_token = refresh_token

#     db.commit()

#     # 7. Redirect back to platform (optional)
#     return {
#         "requested_site": record.site_url,
#         "google_sites": sites_data,
#         "verified": verified,
#         "permission_level": permission_level
#     }
USER_INFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

@gsc_router.get("/callback")
async def gsc_callback(request: Request, db: Session = Depends(get_db)):
    # 1. Handle user denying consent or Google errors
    error = request.query_params.get("error")
    state = request.query_params.get("state")
    
    if not state:
        raise HTTPException(status_code=400, detail="Missing state parameter")

    record = db.query(GSCVerification).filter(GSCVerification.id == state).first()
    if not record:
        raise HTTPException(status_code=404, detail="Invalid state/session")

    if error:
        record.verified = False
        db.commit()
        return {"status": "failed", "reason": error}

    code = request.query_params.get("code")
    if not code:
        return {"status": "failed", "reason": "No authorization code provided"}

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        # 2. Exchange code for tokens
        token_res = await client.post(
            TOKEN_URL,
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": REDIRECT_URI,
            }
        )
        
        if token_res.status_code != 200:
            return {"status": "failed", "reason": "Token exchange failed", "details": token_res.json()}
        
        token_data = token_res.json()
        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token") # Note: Only sent on first consent

        # 3. Get User Details (to fill your new fields)
        user_res = await client.get(
            USER_INFO_URL,
            headers={"Authorization": f"Bearer {access_token}"}
        )
        user_data = user_res.json() if user_res.status_code == 200 else {}

        # 4. Get GSC Sites
        sites_res = await client.get(
            GSC_SITES_URL,
            headers={"Authorization": f"Bearer {access_token}"}
        )
        sites_data = sites_res.json()

        if "siteEntry" not in sites_data:
            return {"status": "failed", "reason": "No sites found in this Google account"}

        # 5. Ownership & Data Sync Logic
        requested_normalized = normalize_site(record.site_url)
        verified = False
        permission_level = None

        for site in sites_data["siteEntry"]:
            if normalize_site(site["siteUrl"]) == requested_normalized:
                permission_level = site["permissionLevel"]
                if permission_level in ["siteOwner", "siteFullUser"]:
                    verified = True
                    # IMPORTANT: Save the EXACT URL from Google for the metrics API to work
                    record.site_url = site["siteUrl"]
                break

        # 6. Final DB Update (Populating your new fields)
        record.verified = verified
        record.permission_level = permission_level
        record.access_token = access_token
        
        # Only update refresh_token if Google sent a new one
        if refresh_token:
            record.refresh_token = refresh_token
            
        # Filling your new fields
        record.google_id = user_data.get("sub")    # 'sub' is the unique Google User ID
        record.email_id = user_data.get("email")   # The user's email address
        
        db.commit()

    return {
        "status": "success" if verified else "unverified",
        "email": record.email_id,
        "site": record.site_url,
        "verified": verified
    }


#############################################################

# @gsc_router.get("/verify-result", response_model=GSCVerificationResult)
# def get_verification_result(
#     site_url: str = Query(...),
#     db: Session = Depends(get_db)
# ):

#     # clean_site = normalize_site(site_url)

#     record = (
#         db.query(GSCVerification)
#         .filter(GSCVerification.site_url == site_url)
#         .order_by(GSCVerification.created_at.desc())
#         .first()
#     )

#     if not record:
#         raise HTTPException(status_code=404, detail="Verification record not found")

#     return {
#         "site_url": record.site_url,
#         "verified": record.verified,
#         "permission_level": record.permission_level
#     }

@gsc_router.get("/verify-result", response_model=GSCVerificationResult)
def get_verification_result(
    site_url: str = Query(..., description="The URL to check verification status for"),
    db: Session = Depends(get_db)
):
    clean_site = normalize_site(site_url)

    record = (
        db.query(GSCVerification)
        .filter(
            (GSCVerification.site_url == site_url) | 
            (GSCVerification.site_url == clean_site)
        )
        .order_by(GSCVerification.created_at.desc())
        .first()
    )

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"No verification history found for {site_url}"
        )

    return {
        "site_url": record.site_url,
        "verified": record.verified,
        "permission_level": record.permission_level
    }


####################################################

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GSC_QUERY_URL = "https://www.googleapis.com/webmasters/v3/sites/{site_url}/searchAnalytics/query"

# def get_access_token(refresh_token: str):
#     data = {
#         "client_id": CLIENT_ID,
#         "client_secret": CLIENT_SECRET,
#         "refresh_token": refresh_token,
#         "grant_type": "refresh_token"
#     }

#     resp = requests.post(GOOGLE_TOKEN_URL, data=data)
#     if resp.status_code != 200:
#         raise HTTPException(status_code=400, detail="Failed to refresh access token")

#     return resp.json()["access_token"]





# @gsc_router.get("/metrics")
# def get_gsc_metrics(
#     site_url: str = Query(...),
#     start_date: str = Query(..., example="2026-01-01"),
#     end_date: str = Query(..., example="2026-02-01"),
#     # New Dynamic Parameters
#     dimensions: List[str] = Query(["query"], description="e.g. query, page, country, device, date"),
#     search_type: str = Query("web", description="web, image, video, news, discover, googleNews"),
#     row_limit: int = Query(50, ge=1, le=25000),
#     db: Session = Depends(get_db)
# ):
#     # 1. Database Lookup (keeping your robust search logic)
#     record = db.query(GSCVerification).filter(
#         GSCVerification.site_url == site_url,
#         GSCVerification.verified == True
#     ).first()

#     if not record:
#         clean = normalize_site(site_url)
#         record = db.query(GSCVerification).filter(
#             GSCVerification.site_url.contains(clean),
#             GSCVerification.verified == True
#         ).first()

#     if not record:
#         raise HTTPException(status_code=404, detail="Verified site not found")

#     # 2. Token Refresh
#     access_token = get_access_token(record.refresh_token)

#     # 3. Dynamic Body Construction & Validation
#     # Important: Discover and GoogleNews do not support the 'query' dimension
#     final_dimensions = dimensions
#     if search_type in ["discover", "googleNews"] and "query" in final_dimensions:
#         final_dimensions = [d for d in final_dimensions if d != "query"]

#     body = {
#         "startDate": start_date,
#         "endDate": end_date,
#         "dimensions": final_dimensions,
#         "type": search_type,  # This handles web, image, video, etc.
#         "rowLimit": row_limit
#     }

#     # 4. GSC API Call
#     headers = {
#         "Authorization": f"Bearer {access_token}",
#         "Content-Type": "application/json"
#     }
    
#     encoded_site = quote(record.site_url, safe="")
#     url = GSC_QUERY_URL.format(site_url=encoded_site)

#     resp = requests.post(url, headers=headers, json=body)

#     if resp.status_code != 200:
#         raise HTTPException(status_code=400, detail=resp.text)

#     return resp.json()


TIMEOUT = httpx.Timeout(10.0, connect=5.0)

async def get_access_token(refresh_token: str):
    """Refreshes the Google OAuth token asynchronously."""
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token"
    }

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            resp = await client.post(GOOGLE_TOKEN_URL, data=data)
            resp.raise_for_status() # Automatically raises exception for 4xx/5xx
            return resp.json()["access_token"]
        except httpx.HTTPStatusError as e:
            # Handle specific Google Auth errors
            error_detail = e.response.json().get("error_description", "Token refresh failed")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=error_detail)
        except httpx.RequestError:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Google Auth service unreachable")

@gsc_router.get("/metrics")
async def get_gsc_metrics(
    site_url: str = Query(...),
    start_date: str = Query(..., example="2026-01-01"),
    end_date: str = Query(..., example="2026-02-01"),
    dimensions: List[str] = Query(["query"]),
    search_type: str = Query("web"),
    row_limit: int = Query(50, ge=1, le=25000),
    db: Session = Depends(get_db)
):

    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be before end_date")
    # 1. Database Lookup (Remains synchronous as SQLAlchemy/Postgres drivers usually are)
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
        raise HTTPException(status_code=404, detail="Site not verified or record not found")

    # 2. Asynchronous Token Refresh
    access_token = await get_access_token(record.refresh_token)

    # 3. Request Preparation
    final_dimensions = [d for d in dimensions if d != "query"] if search_type in ["discover", "googleNews"] else dimensions

    body = {
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": final_dimensions,
        "type": search_type,
        "rowLimit": row_limit
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    # 4. Asynchronous API Call with Connection Pooling
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        encoded_site = quote(record.site_url, safe="")
        url = GSC_QUERY_URL.format(site_url=encoded_site)
        
        try:
            resp = await client.post(url, headers=headers, json=body)

            resp.raise_for_status()
            return resp.json()
            
        except httpx.HTTPStatusError as e:
            # Pass the GSC specific error (like 403 permissions) back to the user
            raise HTTPException(status_code=e.response.status_code, detail=e.response.json())
        except httpx.RequestError:
            raise HTTPException(status_code=503, detail="Search Console API is currently unavailable")

        
        
        
        # if resp.status_code != 200:
        # try:
        #     google_error = resp.json()
        # except:
        #     google_error = resp.text

        # raise HTTPException(
        #     status_code=502,
        #     detail={
        #         "source": "google_search_console",
        #         "message": "Failed to fetch metrics",
        #         "google_error": google_error
        #     }
        # )


# # Constant for revoking tokens
# GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"

# @gsc_router.delete("/disconnect", status_code=status.HTTP_200_OK)
# async def disconnect_gsc_site(
#     site_url: str = Query(...),
#     db: Session = Depends(get_db)
# ):

#     # 1. Find the record
#     record = db.query(GSCVerification).filter(
#         GSCVerification.site_url == site_url,
#         GSCVerification.verified == True
#     ).first()

#     if not record:
#         # If it doesn't exist, we consider the job "done" (Idempotent)
#         return {"message": "Site was not connected or already removed."}

#     # 2. Attempt to Revoke Token (Best Effort)
#     # We use the refresh_token if available as it's more powerful
#     token_to_revoke = record.refresh_token or record.access_token
    
#     if token_to_revoke:
#         async with httpx.AsyncClient(timeout=TIMEOUT) as client:
#             try:
#                 # Google expects the token as a query parameter or form data
#                 await client.post(
#                     f"{GOOGLE_REVOKE_URL}?token={token_to_revoke}",
#                     headers={"Content-Type": "application/x-www-form-urlencoded"}
#                 )
#             except Exception as e:
#                 # We log this but don't stop the deletion. 
#                 # User might have already revoked access manually.
#                 print(f"Token revocation failed (already revoked?): {e}")

#     # 3. Delete from Database
#     try:
#         db.delete(record)
#         db.commit()
#     except Exception as e:
#         db.rollback()
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Database error during disconnection."
#         )

#     return {
#         "status": "success",
#         "message": f"Successfully disconnected {site_url} and revoked access tokens."
#     }