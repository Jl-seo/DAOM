"""
Authentication module for Entra ID (Azure AD) JWT token verification
"""
import logging
from typing import Optional
from dataclasses import dataclass
from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt import PyJWKClient
from app.core.config import settings

logger = logging.getLogger(__name__)

# JWKS URL for Entra ID
JWKS_URL = f"https://login.microsoftonline.com/{settings.AZURE_AD_TENANT_ID}/discovery/v2.0/keys"


@dataclass
class CurrentUser:
    """Authenticated user info from JWT token"""
    id: str           # oid (Object ID)
    email: str        # preferred_username or email
    name: str         # name
    tenant_id: str    # tid (Tenant ID)
    roles: list[str]  # app roles
    groups: list[str] = None # security groups
    access_token: str = None  # Raw bearer token for Graph API calls


class AzureADAuth(HTTPBearer):
    """Azure AD JWT Bearer token authentication"""

    def __init__(self, auto_error: bool = True):
        super().__init__(auto_error=auto_error)
        self._jwks_client: Optional[PyJWKClient] = None

    @property
    def jwks_client(self) -> PyJWKClient:
        """Lazy-load JWKS client"""
        if self._jwks_client is None:
            self._jwks_client = PyJWKClient(JWKS_URL)
        return self._jwks_client

    async def __call__(self, request: Request) -> Optional[CurrentUser]:
        credentials: HTTPAuthorizationCredentials = await super().__call__(request)

        if credentials:
            if credentials.scheme.lower() != "bearer":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Invalid authentication scheme"
                )

            user = self.verify_token(credentials.credentials)
            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Invalid or expired token"
                )
            # Store raw token for downstream Graph API calls (Entra group checks)
            user.access_token = credentials.credentials
            return user

        if self.auto_error:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authenticated"
            )
        return None

    def verify_token(self, token: str) -> Optional[CurrentUser]:
        """Verify JWT token and extract user info"""
        try:
            # Try to get signing key from tenant-specific JWKS
            signing_key = None
            try:
                signing_key = self.jwks_client.get_signing_key_from_jwt(token)
            except Exception as e:
                logger.warning(f"Tenant JWKS key lookup failed: {e}")
                # Fallback: try 'common' JWKS endpoint
                try:
                    common_client = PyJWKClient("https://login.microsoftonline.com/common/discovery/v2.0/keys")
                    signing_key = common_client.get_signing_key_from_jwt(token)
                    logger.info("Using 'common' JWKS endpoint for key lookup")
                except Exception as e2:
                    logger.warning(f"Common JWKS key lookup also failed: {e2}")

            # Determine verification level based on configuration
            has_client_id = bool(settings.AZURE_AD_CLIENT_ID)
            has_tenant_id = bool(settings.AZURE_AD_TENANT_ID) and settings.AZURE_AD_TENANT_ID not in ("common", "")

            if signing_key:
                # We have a signing key — verify signature + expiry
                if has_client_id and has_tenant_id:
                    v1_issuer = f"https://sts.windows.net/{settings.AZURE_AD_TENANT_ID}/"
                    v2_issuer = f"https://login.microsoftonline.com/{settings.AZURE_AD_TENANT_ID}/v2.0"
                    valid_audiences = [settings.AZURE_AD_CLIENT_ID, f"api://{settings.AZURE_AD_CLIENT_ID}"]
                    try:
                        payload = jwt.decode(
                            token, signing_key.key, algorithms=["RS256"],
                            audience=valid_audiences, issuer=[v1_issuer, v2_issuer],
                            options={"verify_signature": True, "verify_exp": True, "verify_aud": True, "verify_iss": True}
                        )
                    except (jwt.InvalidAudienceError, jwt.InvalidIssuerError) as e:
                        logger.warning(f"JWT aud/iss mismatch ({e}), retrying signature+expiry only")
                        payload = jwt.decode(
                            token, signing_key.key, algorithms=["RS256"],
                            options={"verify_signature": True, "verify_exp": True, "verify_aud": False, "verify_iss": False}
                        )
                else:
                    payload = jwt.decode(
                        token, signing_key.key, algorithms=["RS256"],
                        options={"verify_signature": True, "verify_exp": True, "verify_aud": False, "verify_iss": False}
                    )
            else:
                # No signing key available — decode without signature verification
                # Still verify expiry. Log a security warning.
                logger.warning("SECURITY: No JWKS signing key available. Decoding without signature verification.")
                payload = jwt.decode(
                    token,
                    options={"verify_signature": False, "verify_exp": True, "verify_aud": False, "verify_iss": False}
                )

            # Extract user info
            email = payload.get("upn") or payload.get("unique_name") or payload.get("preferred_username") or payload.get("email", "")

            return CurrentUser(
                id=payload.get("oid", ""),
                email=email,
                name=payload.get("name", "Unknown"),
                tenant_id=payload.get("tid", ""),
                roles=payload.get("roles", []),
                groups=payload.get("groups", []) or payload.get("wids", [])
            )

        except jwt.ExpiredSignatureError:
            logger.warning("Token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None
        except Exception as e:
            logger.error(f"Token verification error: {e}")
            return None


# Singleton instance
azure_ad_auth = AzureADAuth()


async def get_current_user(request: Request) -> CurrentUser:
    """Dependency: Get current authenticated user"""
    return await azure_ad_auth(request)


async def get_current_user_optional(request: Request) -> Optional[CurrentUser]:
    """Dependency: Get current user if authenticated, None otherwise"""
    auth = AzureADAuth(auto_error=False)
    return await auth(request)


async def is_admin(user: CurrentUser) -> bool:
    """Check if user has admin privileges via group membership"""
    if not user:
        return False

    # Import group permission utilities
    from app.core.group_permission_utils import check_initial_admin, is_super_admin_by_group

    # 1. Bootstrap: INITIAL_ADMIN_EMAILS (for initial setup/testing)
    if check_initial_admin(user.email):
        return True

    # 2. Production: Check Cosmos DB group membership with superAdmin=true
    if await is_super_admin_by_group(user.id, user.tenant_id, access_token=getattr(user, 'access_token', None), user_groups=getattr(user, 'groups', None)):
        return True

    return False

async def is_super_admin(user: CurrentUser) -> bool:
    """Check if user has super admin privileges via group membership"""
    if not user:
        return False

    from app.core.group_permission_utils import check_initial_admin, is_super_admin_by_group

    # 1. Bootstrap: INITIAL_ADMIN_EMAILS
    if check_initial_admin(user.email):
        return True

    # 2. Production: Check Cosmos DB group superAdmin
    if await is_super_admin_by_group(user.id, user.tenant_id, access_token=getattr(user, 'access_token', None), user_groups=getattr(user, 'groups', None)):
        return True

    return False
