#!/usr/bin/env python3
"""
Google Drive File Upload and Creation Script

Upload files, create Google Docs/Sheets/Slides, and manage file creation.

Usage:
    # Upload a file to root
    python3 gdrive_upload.py upload --file /path/to/document.pdf

    # Upload to a specific folder
    python3 gdrive_upload.py upload --file /path/to/document.pdf --parent-folder-id "FOLDER_ID"

    # Create a Google Doc from text
    python3 gdrive_upload.py create-doc --title "Meeting Notes" --content "Content here..."

    # Create a Google Sheet from CSV
    python3 gdrive_upload.py create-sheet --title "Data" --csv-file /path/to/data.csv

    # Create a blank Google Doc/Sheet/Slides
    python3 gdrive_upload.py create-blank --type document --title "New Doc"

Environment Variables:
    GOOGLE_DRIVE_CREDENTIALS_PATH: Path to credentials file (required)
    GOOGLE_DRIVE_TOKEN_PATH: Path to OAuth2 token (optional)
    GOOGLE_DRIVE_SCOPES: Space-separated scopes (optional)
"""

import argparse
import json
import logging
import mimetypes
import os
import sys
from pathlib import Path

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

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

# MIME type mappings for Google Workspace conversions
GOOGLE_MIME_TYPES = {
    "document": "application/vnd.google-apps.document",
    "sheet": "application/vnd.google-apps.spreadsheet",
    "slides": "application/vnd.google-apps.presentation",
    "folder": "application/vnd.google-apps.folder",
}

# Import MIME types for common extensions
MIME_TYPE_MAP = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".csv": "text/csv",
    ".html": "text/html",
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".zip": "application/zip",
    ".json": "application/json",
    ".xml": "application/xml",
}


def detect_mime_type(file_path: str) -> str:
    """Detect MIME type from file extension.

    Args:
        file_path: Path to the file.

    Returns:
        MIME type string.
    """
    ext = Path(file_path).suffix.lower()
    if ext in MIME_TYPE_MAP:
        return MIME_TYPE_MAP[ext]

    # Try Python's mimetypes module
    mime_type, _ = mimetypes.guess_type(file_path)
    return mime_type or "application/octet-stream"


def should_convert_to_google_workspace(file_path: str) -> tuple[bool, str]:
    """Determine if a file should be converted to Google Workspace format.

    Args:
        file_path: Path to the file.

    Returns:
        Tuple of (should_convert, google_mime_type).
    """
    ext = Path(file_path).suffix.lower()

    conversion_map = {
        ".txt": GOOGLE_MIME_TYPES["document"],
        ".md": GOOGLE_MIME_TYPES["document"],
        ".doc": GOOGLE_MIME_TYPES["document"],
        ".docx": GOOGLE_MIME_TYPES["document"],
        ".csv": GOOGLE_MIME_TYPES["sheet"],
        ".xls": GOOGLE_MIME_TYPES["sheet"],
        ".xlsx": GOOGLE_MIME_TYPES["sheet"],
        ".ppt": GOOGLE_MIME_TYPES["slides"],
        ".pptx": GOOGLE_MIME_TYPES["slides"],
    }

    if ext in conversion_map:
        return True, conversion_map[ext]

    return False, ""


def upload_file(
    service,
    file_path: str,
    title: str = None,
    parent_folder_id: str = None,
    description: str = None,
    convert: bool = False,
    json_output: bool = False,
) -> dict:
    """Upload a file to Google Drive.

    Args:
        service: Authenticated Drive service.
        file_path: Path to local file.
        title: File name in Drive (default: original filename).
        parent_folder_id: Parent folder ID (default: root).
        description: File description.
        convert: Convert to Google Workspace format if possible.
        json_output: Whether output will be JSON (affects logging).

    Returns:
        File metadata dictionary.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if not path.is_file():
        raise ValueError(f"Path is not a file: {file_path}")

    file_name = title or path.name
    mime_type = detect_mime_type(file_path)
    file_size = path.stat().st_size

    if not json_output:
        logger.info("Uploading: %s (%s, %s)", file_name, mime_type, _format_size(file_size))

    # Prepare file metadata
    file_metadata = {
        "name": file_name,
    }

    if description:
        file_metadata["description"] = description

    if parent_folder_id:
        file_metadata["parents"] = [parent_folder_id]

    # Determine if we should convert to Google Workspace format
    if convert:
        should_convert, google_mime = should_convert_to_google_workspace(file_path)
        if should_convert:
            file_metadata["mimeType"] = google_mime
            if not json_output:
                logger.info("Converting to Google Workspace format: %s", google_mime)

    # Create media upload object
    media = MediaFileUpload(
        str(path),
        mimetype=mime_type,
        resumable=True,  # Enable resumable uploads for large files
        chunksize=1024 * 1024,  # 1MB chunks
    )

    try:
        request = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, name, mimeType, webViewLink, webContentLink, size, createdTime, modifiedTime",
        )

        # Execute with progress tracking for large files
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status and not json_output:
                progress = status.progress() * 100
                logger.info("Upload progress: %.1f%%", progress)

        if not json_output:
            logger.info("Upload complete! File ID: %s", response.get("id"))

        return response

    except HttpError as e:
        error_info = handle_api_error(e, f"Upload file: {file_name}")
        raise


def create_google_doc(
    service,
    title: str,
    content: str = None,
    parent_folder_id: str = None,
    json_output: bool = False,
) -> dict:
    """Create a new Google Doc.

    Args:
        service: Authenticated Drive service.
        title: Document title.
        content: Document content (plain text).
        parent_folder_id: Parent folder ID (default: root).
        json_output: Whether output will be JSON.

    Returns:
        File metadata dictionary.
    """
    # Create the document via Drive API
    file_metadata = {
        "name": title,
        "mimeType": GOOGLE_MIME_TYPES["document"],
    }

    if parent_folder_id:
        file_metadata["parents"] = [parent_folder_id]

    try:
        doc = service.files().create(
            body=file_metadata,
            fields="id, name, mimeType, webViewLink, createdTime, modifiedTime",
        ).execute()

        doc_id = doc.get("id")

        # If content is provided, use Docs API to insert it
        if content:
            try:
                docs_service = _get_docs_service(service._http.credentials)
                requests = [
                    {
                        "insertText": {
                            "location": {"index": 1},
                            "text": content,
                        }
                    }
                ]
                docs_service.documents().batchUpdate(
                    documentId=doc_id,
                    body={"requests": requests},
                ).execute()
                if not json_output:
                    logger.info("Content added to document")
            except Exception as e:
                logger.warning("Could not add content via Docs API: %s", e)
                logger.warning("Document created but content not set. You can edit it manually.")

        if not json_output:
            logger.info("Google Doc created: %s (%s)", title, doc_id)

        return doc

    except HttpError as e:
        error_info = handle_api_error(e, f"Create Google Doc: {title}")
        raise


def create_google_sheet_from_csv(
    service,
    title: str,
    csv_file: str,
    parent_folder_id: str = None,
    json_output: bool = False,
) -> dict:
    """Create a Google Sheet from a CSV file.

    Args:
        service: Authenticated Drive service.
        title: Sheet title.
        csv_file: Path to CSV file.
        parent_folder_id: Parent folder ID (default: root).
        json_output: Whether output will be JSON.

    Returns:
        File metadata dictionary.
    """
    path = Path(csv_file)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_file}")

    file_metadata = {
        "name": title,
        "mimeType": GOOGLE_MIME_TYPES["sheet"],
    }

    if parent_folder_id:
        file_metadata["parents"] = [parent_folder_id]

    media = MediaFileUpload(
        str(path),
        mimetype="text/csv",
        resumable=True,
    )

    try:
        sheet = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, name, mimeType, webViewLink, createdTime, modifiedTime",
        ).execute()

        if not json_output:
            logger.info("Google Sheet created from CSV: %s (%s)", title, sheet.get("id"))

        return sheet

    except HttpError as e:
        error_info = handle_api_error(e, f"Create Google Sheet from CSV: {title}")
        raise


def create_blank_google_file(
    service,
    file_type: str,
    title: str,
    parent_folder_id: str = None,
    json_output: bool = False,
) -> dict:
    """Create a blank Google Doc, Sheet, or Slides.

    Args:
        service: Authenticated Drive service.
        file_type: One of 'document', 'spreadsheet', 'presentation'.
        title: File title.
        parent_folder_id: Parent folder ID (default: root).
        json_output: Whether output will be JSON.

    Returns:
        File metadata dictionary.
    """
    mime_map = {
        "document": GOOGLE_MIME_TYPES["document"],
        "spreadsheet": GOOGLE_MIME_TYPES["sheet"],
        "presentation": GOOGLE_MIME_TYPES["slides"],
    }

    if file_type not in mime_map:
        raise ValueError(
            f"Invalid file type: {file_type}. Must be one of: {', '.join(mime_map.keys())}"
        )

    file_metadata = {
        "name": title,
        "mimeType": mime_map[file_type],
    }

    if parent_folder_id:
        file_metadata["parents"] = [parent_folder_id]

    try:
        file = service.files().create(
            body=file_metadata,
            fields="id, name, mimeType, webViewLink, createdTime, modifiedTime",
        ).execute()

        if not json_output:
            logger.info("Blank Google %s created: %s (%s)", file_type.title(), title, file.get("id"))

        return file

    except HttpError as e:
        error_info = handle_api_error(e, f"Create blank Google {file_type}: {title}")
        raise


def _get_docs_service(credentials):
    """Get authenticated Docs API service.

    Args:
        credentials: OAuth2/Service Account credentials.

    Returns:
        Authenticated Docs API service.
    """
    from googleapiclient.discovery import build
    return build("docs", "v1", credentials=credentials)


def _format_size(size_bytes: int) -> str:
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


def build_parser() -> argparse.ArgumentParser:
    """Build argument parser."""
    parser = argparse.ArgumentParser(
        description="Upload files and create Google Docs/Sheets/Slides",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Upload command
    upload_parser = subparsers.add_parser("upload", help="Upload a file to Drive")
    upload_parser.add_argument(
        "--file", "-f",
        required=True,
        help="Path to file to upload",
    )
    upload_parser.add_argument(
        "--title", "-t",
        help="File name in Drive (default: original filename)",
    )
    upload_parser.add_argument(
        "--parent-folder-id", "-p",
        help="Parent folder ID (default: root)",
    )
    upload_parser.add_argument(
        "--description", "-d",
        help="File description",
    )
    upload_parser.add_argument(
        "--convert", "-c",
        action="store_true",
        help="Convert to Google Workspace format if possible",
    )

    # Create Google Doc
    doc_parser = subparsers.add_parser("create-doc", help="Create a Google Doc")
    doc_parser.add_argument(
        "--title", "-t",
        required=True,
        help="Document title",
    )
    doc_parser.add_argument(
        "--content",
        help="Document content (plain text)",
    )
    doc_parser.add_argument(
        "--content-file",
        help="Read content from file",
    )
    doc_parser.add_argument(
        "--parent-folder-id", "-p",
        help="Parent folder ID (default: root)",
    )

    # Create Google Sheet from CSV
    sheet_parser = subparsers.add_parser("create-sheet", help="Create a Google Sheet from CSV")
    sheet_parser.add_argument(
        "--title", "-t",
        required=True,
        help="Sheet title",
    )
    sheet_parser.add_argument(
        "--csv-file", "-f",
        required=True,
        help="Path to CSV file",
    )
    sheet_parser.add_argument(
        "--parent-folder-id", "-p",
        help="Parent folder ID (default: root)",
    )

    # Create blank Google file
    blank_parser = subparsers.add_parser("create-blank", help="Create a blank Google file")
    blank_parser.add_argument(
        "--type",
        required=True,
        choices=["document", "spreadsheet", "presentation"],
        help="Type of Google file to create",
    )
    blank_parser.add_argument(
        "--title", "-t",
        required=True,
        help="File title",
    )
    blank_parser.add_argument(
        "--parent-folder-id", "-p",
        help="Parent folder ID (default: root)",
    )

    # Global options
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output as JSON",
    )

    return parser


def main():
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

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
        if args.command == "upload":
            result = upload_file(
                service=service,
                file_path=args.file,
                title=args.title,
                parent_folder_id=args.parent_folder_id,
                description=args.description,
                convert=args.convert,
                json_output=args.json_output,
            )

        elif args.command == "create-doc":
            content = args.content
            if args.content_file:
                with open(args.content_file, "r", encoding="utf-8") as f:
                    content = f.read()

            result = create_google_doc(
                service=service,
                title=args.title,
                content=content,
                parent_folder_id=args.parent_folder_id,
                json_output=args.json_output,
            )

        elif args.command == "create-sheet":
            result = create_google_sheet_from_csv(
                service=service,
                title=args.title,
                csv_file=args.csv_file,
                parent_folder_id=args.parent_folder_id,
                json_output=args.json_output,
            )

        elif args.command == "create-blank":
            result = create_blank_google_file(
                service=service,
                file_type=args.type,
                title=args.title,
                parent_folder_id=args.parent_folder_id,
                json_output=args.json_output,
            )

        else:
            parser.print_help()
            sys.exit(1)

        if args.json_output:
            print(json.dumps({"success": True, "file": result}, indent=2))
        else:
            print(f"\nSuccess!")
            print(f"  Name: {result.get('name')}")
            print(f"  ID: {result.get('id')}")
            print(f"  Type: {result.get('mimeType')}")
            if result.get("webViewLink"):
                print(f"  URL: {result.get('webViewLink')}")

    except HttpError as e:
        error_info = handle_api_error(e, f"Command: {args.command}")
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
                "context": f"Command: {args.command}",
                "suggested_action": "Check the error message and try again",
            })
        else:
            print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
