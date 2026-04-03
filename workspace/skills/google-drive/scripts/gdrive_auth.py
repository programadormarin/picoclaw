#!/usr/bin/env python3
"""
Google Drive Authentication Module

Handles authentication for both OAuth2 (user accounts) and Service Account (server-to-server).
This module is designed to be imported by other scripts, not run directly.

Usage:
    from gdrive_auth import get_drive_service
    service = get_drive_service()
    files = service.files().list(pageSize=10).execute()

Environment Variables:
    GOOGLE_DRIVE_CREDENTIALS_PATH: Path to credentials.json or service account JSON (required)
    GOOGLE_DRIVE_TOKEN_PATH: Path to save/load OAuth2 token (default: token.json in skill dir)
    GOOGLE_DRIVE_SCOPES: Space-separated OAuth2 scopes (default: full Drive access)
    GOOGLE_DRIVE_IMPERSONATE_USER: Email to impersonate (domain-wide delegation)
"""

import json
import logging
import os
import re
import stat
import sys
import time
from functools import wraps
from pathlib import Path
from typing import Optional

import httplib2
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Default scopes
DEFAULT_SCOPES = ["https://www.googleapis.com/auth/drive"]
SCOPES_MAP = {
    "readonly": "https://www.googleapis.com/auth/drive.readonly",
    "full": "https://www.googleapis.com/auth/drive",
    "file": "https://www.googleapis.com/auth/drive.file",
    "metadata": "https://www.googleapis.com/auth/drive.metadata.readonly",
    "appdata": "https://www.googleapis.com/auth/drive.appdata",
    "metadata.full": "https://www.googleapis.com/auth/drive.metadata",
}

# Skill directory for default token path
SKILL_DIR = Path(__file__).parent
DEFAULT_TOKEN_PATH = SKILL_DIR / "token.json"

# File ID validation pattern (Google Drive IDs are alphanumeric with dashes/underscores)
FILE_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{10,100}$')

# API timeout in seconds
API_TIMEOUT = 30


def validate_credentials_file_permissions(path: Path) -> None:
    """Validate and fix credentials file permissions.
    
    Ensures credentials files are only readable by the owner (0o600).
    
    Args:
        path: Path to credentials file.
    """
    if not path.exists():
        return
    
    try:
        file_stat = path.stat()
        mode = file_stat.st_mode & 0o777
        if mode & 0o077:  # Group or others have any permission
            logger.warning(
                "Credentials file %s has insecure permissions (%o). "
                "Restricting to owner-only.", path, mode
            )
            path.chmod(0o600)
    except (OSError, AttributeError) as e:
        logger.warning("Could not check/fix credentials file permissions: %s", e)


def write_token_securely(token_file: Path, content: str) -> None:
    """Write token file with restrictive permissions (owner read/write only).
    
    Args:
        token_file: Path to token file.
        content: Token JSON content.
    """
    token_file.parent.mkdir(parents=True, exist_ok=True)
    # Create with restrictive permissions (0o600)
    fd = os.open(str(token_file), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, content.encode('utf-8'))
    finally:
        os.close(fd)


def validate_file_id(file_id: str) -> str:
    """Validate Google Drive file ID format.
    
    Args:
        file_id: File ID to validate.
        
    Returns:
        The file_id if valid.
        
    Raises:
        ValueError: If file_id format is invalid.
    """
    if not FILE_ID_PATTERN.match(file_id):
        raise ValueError(
            f"Invalid file ID format: '{file_id}'\n"
            f"File IDs should be 10-100 alphanumeric characters (may include - and _)\n"
            f"Example: https://drive.google.com/file/d/FILE_ID/view"
        )
    return file_id


def retry_on_rate_limit(max_retries: int = 3, backoff_factor: int = 2):
    """Decorator to retry API calls on rate limit or server errors.
    
    Args:
        max_retries: Maximum number of retry attempts.
        backoff_factor: Base for exponential backoff (seconds).
        
    Usage:
        @retry_on_rate_limit(max_retries=3)
        def my_api_call():
            return service.files().list().execute()
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except HttpError as e:
                    status_code = e.resp.status
                    if status_code == 429 or status_code >= 500:
                        if attempt == max_retries - 1:
                            raise
                        wait_time = backoff_factor ** attempt
                        logger.warning(
                            "Rate limited/server error (attempt %d/%d). Retrying in %ds...",
                            attempt + 1, max_retries, wait_time
                        )
                        time.sleep(wait_time)
                    else:
                        raise
            return None  # Should never reach here
        return wrapper
    return decorator


def parse_scopes(scopes_str: Optional[str] = None) -> list[str]:
    """Parse scopes string into a list of scope URLs.

    Args:
        scopes_str: Space-separated scope names or full scope URLs.
                   Known names: readonly, full, file, metadata, appdata, metadata.full

    Returns:
        List of full scope URLs.
    """
    if not scopes_str:
        return DEFAULT_SCOPES.copy()

    scopes = []
    for scope in scopes_str.split():
        if scope in SCOPES_MAP:
            scopes.append(SCOPES_MAP[scope])
        elif scope.startswith("https://"):
            scopes.append(scope)
        else:
            logger.warning("Unknown scope '%s', ignoring", scope)

    return scopes if scopes else DEFAULT_SCOPES.copy()


def detect_auth_type(credentials_path: str) -> str:
    """Detect authentication type from credentials file.

    Args:
        credentials_path: Path to credentials file.

    Returns:
        'oauth2' or 'service_account'

    Raises:
        FileNotFoundError: If credentials file doesn't exist.
        ValueError: If credentials file is invalid.
    """
    path = Path(credentials_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Credentials file not found: {credentials_path}\n"
            f"Set GOOGLE_DRIVE_CREDENTIALS_PATH to your credentials file.\n"
            f"See references/authentication.md for setup instructions."
        )

    # Validate and fix file permissions
    validate_credentials_file_permissions(path)

    with open(path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in credentials file: {e}")

    if "installed" in data or "web" in data:
        return "oauth2"
    elif "type" in data and data["type"] == "service_account":
        return "service_account"
    else:
        raise ValueError(
            "Unrecognized credentials format. Expected OAuth2 (installed/web) "
            "or Service Account (type: service_account)."
        )


def authenticate_oauth2(
    credentials_path: str,
    token_path: Optional[str] = None,
    scopes: Optional[list[str]] = None,
) -> Credentials:
    """Authenticate using OAuth2 (user account).

    Opens a browser for first-time authorization, then saves/reuses token.

    Args:
        credentials_path: Path to OAuth2 credentials.json.
        token_path: Path to save/load token (default: token.json in skill dir).
        scopes: List of OAuth2 scopes.

    Returns:
        Google OAuth2 Credentials object.
    """
    if scopes is None:
        scopes = DEFAULT_SCOPES.copy()

    token_file = Path(token_path) if token_path else DEFAULT_TOKEN_PATH
    creds = None

    # Load existing token if available
    if token_file.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_file), scopes)
            logger.debug("Loaded existing OAuth2 token")
        except Exception as e:
            logger.warning("Failed to load token: %s, will re-authorize", e)
            creds = None

    # If no valid credentials, run the OAuth2 flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing expired OAuth2 token...")
            try:
                creds.refresh(Request())
                logger.info("Token refreshed successfully")
            except Exception as e:
                logger.warning("Token refresh failed: %s, will re-authorize", e)
                creds = None
        else:
            logger.info("Starting OAuth2 authorization flow...")
            logger.info("A browser window will open for authorization.")
            logger.info(
                "If it doesn't open, visit the URL shown and complete authorization."
            )

            flow = InstalledAppFlow.from_client_secrets_file(
                credentials_path, scopes
            )

            # Try to open browser, fall back to manual URL if needed
            try:
                creds = flow.run_local_server(port=0, open_browser=True)
            except Exception as e:
                logger.warning(
                    "Could not open browser automatically: %s", e
                )
                logger.info("Please complete authorization manually:")
                creds = flow.run_local_server(port=0, open_browser=False)

            logger.info("Authorization successful!")

        # Save the credentials for the next run (with secure permissions)
        write_token_securely(token_file, creds.to_json())
        logger.info("Token saved to: %s", token_file)

    return creds


def authenticate_service_account(
    credentials_path: str,
    scopes: Optional[list[str]] = None,
    impersonate_user: Optional[str] = None,
) -> Credentials:
    """Authenticate using Service Account.

    Args:
        credentials_path: Path to service account JSON key file.
        scopes: List of OAuth2 scopes.
        impersonate_user: Email to impersonate (domain-wide delegation).

    Returns:
        Google Service Account Credentials object.
    """
    if scopes is None:
        scopes = DEFAULT_SCOPES.copy()

    logger.debug("Loading service account credentials from: %s", credentials_path)

    creds = ServiceAccountCredentials.from_service_account_file(
        credentials_path, scopes=scopes
    )

    if impersonate_user:
        logger.info("Impersonating user: %s", impersonate_user)
        creds = creds.with_subject(impersonate_user)

    return creds


def get_drive_service(
    credentials_path: Optional[str] = None,
    token_path: Optional[str] = None,
    scopes: Optional[str] = None,
    impersonate_user: Optional[str] = None,
):
    """Create an authenticated Google Drive service client.

    This is the main entry point for authentication. It auto-detects the auth
    method and returns an authenticated Drive API service.

    Args:
        credentials_path: Path to credentials file (env: GOOGLE_DRIVE_CREDENTIALS_PATH).
        token_path: Path to OAuth2 token (env: GOOGLE_DRIVE_TOKEN_PATH).
        scopes: Space-separated scopes (env: GOOGLE_DRIVE_SCOPES).
        impersonate_user: Email to impersonate (env: GOOGLE_DRIVE_IMPERSONATE_USER).

    Returns:
        Authenticated Google Drive API service object.

    Raises:
        EnvironmentError: If GOOGLE_DRIVE_CREDENTIALS_PATH is not set.
        FileNotFoundError: If credentials file doesn't exist.
        ValueError: If credentials file is invalid.
        HttpError: If authentication fails.
    """
    # Read from environment if not provided
    if credentials_path is None:
        credentials_path = os.environ.get("GOOGLE_DRIVE_CREDENTIALS_PATH")
    if token_path is None:
        token_path = os.environ.get("GOOGLE_DRIVE_TOKEN_PATH")
    if scopes is None:
        scopes = os.environ.get("GOOGLE_DRIVE_SCOPES")
    if impersonate_user is None:
        impersonate_user = os.environ.get("GOOGLE_DRIVE_IMPERSONATE_USER")

    if not credentials_path:
        raise EnvironmentError(
            "GOOGLE_DRIVE_CREDENTIALS_PATH environment variable is not set.\n"
            "Please set it to the path of your credentials file.\n"
            "See references/authentication.md for setup instructions."
        )

    # Detect auth type
    auth_type = detect_auth_type(credentials_path)
    logger.info("Using authentication method: %s", auth_type.upper())

    # Parse scopes
    parsed_scopes = parse_scopes(scopes)

    # Authenticate
    if auth_type == "oauth2":
        creds = authenticate_oauth2(
            credentials_path=credentials_path,
            token_path=token_path,
            scopes=parsed_scopes,
        )
    else:
        creds = authenticate_service_account(
            credentials_path=credentials_path,
            scopes=parsed_scopes,
            impersonate_user=impersonate_user,
        )

    # Build the Drive service with timeout
    try:
        http = httplib2.Http(timeout=API_TIMEOUT)
        service = build("drive", "v3", credentials=creds, http=http)
        logger.debug("Drive service created successfully with %ds timeout", API_TIMEOUT)
        return service
    except HttpError as e:
        logger.error("Failed to create Drive service: %s", e)
        raise


def handle_api_error(e: HttpError, context: str = "Operation") -> dict:
    """Parse and format Google API errors into actionable messages.

    Args:
        e: The HttpError exception.
        context: Description of what was being attempted.

    Returns:
        Dictionary with error details and suggested actions.
    """
    status_code = e.resp.status
    reason = "unknown"
    message = str(e)

    try:
        error_body = json.loads(e.content)
        error_detail = error_body.get("error", {})
        reason = error_detail.get("errors", [{}])[0].get("reason", "unknown")
        message = error_detail.get("message", message)
    except (json.JSONDecodeError, KeyError, IndexError):
        pass

    error_info = {
        "status_code": status_code,
        "reason": reason,
        "message": message,
        "context": context,
        "suggested_action": "",
    }

    # Provide actionable guidance based on error type
    if status_code == 401:
        error_info["suggested_action"] = (
            "Authentication failed. Try re-authorizing:\n"
            "  - OAuth2: Delete token.json and run the script again\n"
            "  - Service Account: Verify credentials file is correct"
        )
    elif status_code == 403:
        if reason == "rateLimitExceeded":
            error_info["suggested_action"] = (
                "Rate limit exceeded. Wait a moment and retry. "
                "Scripts include automatic backoff."
            )
        elif reason == "cannotShareFile":
            error_info["suggested_action"] = (
                "Cannot share this file. It may be owned by another user or domain."
            )
        else:
            error_info["suggested_action"] = (
                "Permission denied. Ensure:\n"
                "  - The file is shared with the service account (if using one)\n"
                "  - You have the correct OAuth2 scopes\n"
                "  - The file ID is correct"
            )
    elif status_code == 404:
        error_info["suggested_action"] = (
            "File or folder not found. Verify the ID is correct.\n"
            "File IDs can be found in the URL when viewing the file in Drive:\n"
            "  https://drive.google.com/file/d/FILE_ID/view"
        )
    elif status_code == 409:
        error_info["suggested_action"] = (
            "Conflict: A file with that name may already exist."
        )
    elif status_code >= 500:
        error_info["suggested_action"] = (
            "Google API server error. Wait and retry."
        )

    return error_info


def format_error(error_info: dict) -> str:
    """Format error info dictionary into a human-readable string.

    Args:
        error_info: Dictionary from handle_api_error().

    Returns:
        Formatted error string.
    """
    lines = [
        f"Error: {error_info['context']} failed",
        f"  Status: {error_info['status_code']}",
        f"  Reason: {error_info['reason']}",
        f"  Message: {error_info['message']}",
    ]
    if error_info["suggested_action"]:
        lines.append(f"  Suggested action:\n    {error_info['suggested_action']}")
    return "\n".join(lines)


def print_error_json(error_info: dict) -> None:
    """Print error info as JSON for programmatic consumption.

    Args:
        error_info: Dictionary from handle_api_error().
    """
    print(json.dumps({"error": error_info}, indent=2))


if __name__ == "__main__":
    # Test authentication when run directly
    print("Testing Google Drive authentication...")
    try:
        service = get_drive_service()
        # Quick test: get user profile (for OAuth2) or list files
        about = service.about().get(fields="user,storageQuota").execute()
        print("Authentication successful!")
        print(f"User: {about.get('user', {}).get('displayName', 'Unknown')}")
        if "storageQuota" in about:
            quota = about["storageQuota"]
            used = int(quota.get("usage", 0))
            limit = int(quota.get("limit", 0))
            print(
                f"Storage: {used / 1e9:.2f} GB / {limit / 1e9:.2f} GB used"
                if limit
                else f"Storage: {used / 1e9:.2f} GB used (unlimited)"
            )
    except Exception as e:
        print(f"Authentication failed: {e}", file=sys.stderr)
        sys.exit(1)
