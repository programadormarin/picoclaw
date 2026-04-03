#!/usr/bin/env python3
"""
Google Drive File Listing and Search Script

List, search, and filter files in Google Drive.

Usage:
    # List recent files
    python3 gdrive_list.py --limit 10

    # Search with query
    python3 gdrive_list.py --query "name contains 'report'"

    # List files in a folder
    python3 gdrive_list.py --folder-id "FOLDER_ID"

    # Filter by MIME type
    python3 gdrive_list.py --mime-type "application/vnd.google-apps.document"

    # Output as JSON
    python3 gdrive_list.py --json

    # List trashed files
    python3 gdrive_list.py --trashed

Environment Variables:
    GOOGLE_DRIVE_CREDENTIALS_PATH: Path to credentials file (required)
    GOOGLE_DRIVE_TOKEN_PATH: Path to OAuth2 token (optional)
    GOOGLE_DRIVE_SCOPES: Space-separated scopes (optional)
"""

import argparse
import json
import logging
import sys
from datetime import datetime

from googleapiclient.errors import HttpError

from gdrive_auth import (
    format_error,
    get_drive_service,
    handle_api_error,
    print_error_json,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Common MIME types for reference
MIME_TYPES = {
    "document": "application/vnd.google-apps.document",
    "sheet": "application/vnd.google-apps.spreadsheet",
    "slides": "application/vnd.google-apps.presentation",
    "folder": "application/vnd.google-apps.folder",
    "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "png": "image/png",
    "jpg": "image/jpeg",
    "gif": "image/gif",
    "zip": "application/zip",
}


def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    if size_bytes == 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    unit_index = 0
    size = float(size_bytes)
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    return f"{size:.1f} {units[unit_index]}"


def format_datetime(dt_str: str) -> str:
    """Format ISO datetime string to readable format."""
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, AttributeError):
        return dt_str


def list_files(
    service,
    query: str = None,
    folder_id: str = None,
    mime_type: str = None,
    limit: int = 20,
    trashed: bool = False,
    order_by: str = "modifiedTime desc",
    fields: str = None,
) -> list[dict]:
    """List files from Google Drive.

    Args:
        service: Authenticated Drive service.
        query: Search query (Google Drive query syntax).
        folder_id: List files in specific folder.
        mime_type: Filter by MIME type.
        limit: Maximum number of files to return.
        trashed: Include trashed files.
        order_by: Sort order.
        fields: Specific fields to request.

    Returns:
        List of file metadata dictionaries.
    """
    # Build query parts
    query_parts = []

    if folder_id:
        query_parts.append(f"'{folder_id}' in parents")

    if mime_type:
        # Resolve shorthand MIME types
        if mime_type in MIME_TYPES:
            mime_type = MIME_TYPES[mime_type]
        query_parts.append(f"mimeType='{mime_type}'")

    if query:
        query_parts.append(query)

    if trashed:
        query_parts.append("trashed=true")
    else:
        query_parts.append("trashed=false")

    full_query = " and ".join(query_parts) if query_parts else None

    # Default fields if not specified
    if fields is None:
        fields = (
            "files(id, name, mimeType, size, createdTime, modifiedTime, "
            "webViewLink, webContentLink, starred, trashed, parents, "
            "owners(displayName, emailAddress), fileExtension), "
            "nextPageToken, incompleteSearch"
        )

    all_files = []
    page_token = None

    while True:
        request_params = {
            "pageSize": min(limit, 1000),  # Max page size is 1000
            "fields": fields,
            "orderBy": order_by,
        }

        if full_query:
            request_params["q"] = full_query
        if page_token:
            request_params["pageToken"] = page_token

        try:
            response = service.files().list(**request_params).execute()
        except HttpError as e:
            error_info = handle_api_error(e, "List files")
            raise

        files = response.get("files", [])
        all_files.extend(files)

        # Check if we've reached the limit
        if len(all_files) >= limit:
            all_files = all_files[:limit]
            break

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return all_files


def format_file_output(file: dict, include_url: bool = True) -> str:
    """Format a single file's metadata for display.

    Args:
        file: File metadata dictionary.
        include_url: Whether to include URLs in output.

    Returns:
        Formatted string representation.
    """
    name = file.get("name", "Unknown")
    file_id = file.get("id", "Unknown")
    mime_type = file.get("mimeType", "Unknown")
    size = file.get("size")
    created = file.get("createdTime")
    modified = file.get("modifiedTime")
    starred = file.get("starred", False)
    trashed = file.get("trashed", False)
    owners = file.get("owners", [])
    file_ext = file.get("fileExtension", "")

    # Determine file type icon
    type_icon = "📄"
    if "folder" in mime_type:
        type_icon = "📁"
    elif "document" in mime_type:
        type_icon = "📝"
    elif "spreadsheet" in mime_type:
        type_icon = "📊"
    elif "presentation" in mime_type:
        type_icon = "📽️"
    elif "image" in mime_type:
        type_icon = "🖼️"
    elif "pdf" in mime_type:
        type_icon = "📕"

    lines = [
        f"{type_icon} {name}",
        f"   ID: {file_id}",
        f"   Type: {mime_type}",
    ]

    if size is not None:
        lines.append(f"   Size: {format_file_size(int(size))}")
    if modified:
        lines.append(f"   Modified: {format_datetime(modified)}")
    if created:
        lines.append(f"   Created: {format_datetime(created)}")
    if owners:
        owner_names = ", ".join(
            o.get("displayName", o.get("emailAddress", "Unknown")) for o in owners
        )
        lines.append(f"   Owner: {owner_names}")
    if starred:
        lines.append("   ⭐ Starred")
    if trashed:
        lines.append("   🗑️ Trashed")
    if file_ext:
        lines.append(f"   Extension: .{file_ext}")

    if include_url:
        web_view = file.get("webViewLink")
        if web_view:
            lines.append(f"   URL: {web_view}")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Build argument parser."""
    parser = argparse.ArgumentParser(
        description="List and search files in Google Drive",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --limit 10
  %(prog)s --query "name contains 'report'"
  %(prog)s --folder-id "FOLDER_ID"
  %(prog)s --mime-type document
  %(prog)s --trashed
  %(prog)s --json --limit 50

Common query patterns:
  name contains 'keyword'        - Search by name
  modifiedTime > '2024-01-01'    - Filter by date
  starred = true                 - Starred files
  sharedWithMe                   - Files shared with you
  fullText contains 'content'    - Search file contents
        """,
    )

    parser.add_argument(
        "--query", "-q",
        help="Search query (Google Drive query syntax)",
    )
    parser.add_argument(
        "--folder-id", "-f",
        help="List files in specific folder (by folder ID)",
    )
    parser.add_argument(
        "--mime-type", "-m",
        help="Filter by MIME type (e.g., document, sheet, folder, pdf)",
    )
    parser.add_argument(
        "--limit", "-n",
        type=int,
        default=20,
        help="Maximum number of files to return (default: 20)",
    )
    parser.add_argument(
        "--trashed",
        action="store_true",
        help="Include trashed files",
    )
    parser.add_argument(
        "--order-by",
        default="modifiedTime desc",
        help="Sort order (default: modifiedTime desc)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output as JSON",
    )
    parser.add_argument(
        "--fields",
        help="Specific fields to request (advanced)",
    )

    return parser


def main():
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args()

    try:
        service = get_drive_service()
    except Exception as e:
        if args.json_output:
            print_error_json({
                "status_code": 500,
                "reason": "auth_failed",
                "message": str(e),
                "context": "Authentication",
                "suggested_action": "Check credentials and environment variables",
            })
        else:
            print(f"Authentication failed: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        files = list_files(
            service=service,
            query=args.query,
            folder_id=args.folder_id,
            mime_type=args.mime_type,
            limit=args.limit,
            trashed=args.trashed,
            order_by=args.order_by,
            fields=args.fields,
        )

        if args.json_output:
            print(json.dumps({"files": files, "count": len(files)}, indent=2))
        else:
            if not files:
                print("No files found.")
                return

            print(f"Found {len(files)} file(s):\n")
            for i, file in enumerate(files):
                if i > 0:
                    print()
                print(format_file_output(file))

    except HttpError as e:
        error_info = handle_api_error(e, "List files")
        if args.json_output:
            print_error_json(error_info)
        else:
            print(format_error(error_info), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        if args.json_output:
            print_error_json({
                "status_code": 500,
                "reason": "error",
                "message": str(e),
                "context": "List files",
                "suggested_action": "Check the error message and try again",
            })
        else:
            print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
