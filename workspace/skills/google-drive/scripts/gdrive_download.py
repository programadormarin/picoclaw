#!/usr/bin/env python3
"""
Google Drive File Download and Export Script

Download files and export Google Docs/Sheets/Slides to various formats.

Usage:
    # Download a file (auto-detects format)
    python3 gdrive_download.py --file-id "FILE_ID" --output /path/to/output

    # Export Google Doc as plain text
    python3 gdrive_download.py --file-id "DOC_ID" --export-as text

    # Export Google Doc as Markdown
    python3 gdrive_download.py --file-id "DOC_ID" --export-as markdown

    # Export Google Doc as PDF
    python3 gdrive_download.py --file-id "DOC_ID" --export-as pdf

    # Export Google Sheet as CSV
    python3 gdrive_download.py --file-id "SHEET_ID" --export-as csv

    # Print file content to stdout
    python3 gdrive_download.py --file-id "FILE_ID" --stdout

Environment Variables:
    GOOGLE_DRIVE_CREDENTIALS_PATH: Path to credentials file (required)
    GOOGLE_DRIVE_TOKEN_PATH: Path to OAuth2 token (optional)
    GOOGLE_DRIVE_SCOPES: Space-separated scopes (optional)
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

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

# Export MIME types for Google Workspace files
EXPORT_MIME_TYPES = {
    "document": {
        "html": "text/html",
        "text": "text/plain",
        "markdown": "text/markdown",
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "rtf": "application/rtf",
        "odt": "application/vnd.oasis.opendocument.text",
        "epub": "application/epub+zip",
    },
    "sheet": {
        "csv": "text/csv",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pdf": "application/pdf",
        "ods": "application/x-vnd.oasis.opendocument.spreadsheet",
        "tsv": "text/tab-separated-values",
        "html": "text/html",
        "zip": "application/zip",  # Multiple sheets as CSVs in ZIP
    },
    "slides": {
        "pdf": "application/pdf",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "txt": "text/plain",
        "jpg": "image/jpeg",
        "png": "image/png",
        "svg": "image/svg+xml",
    },
    "drawing": {
        "svg": "image/svg+xml",
        "png": "image/png",
        "jpg": "image/jpeg",
        "pdf": "application/pdf",
    },
}

# Detect Google Workspace file type from MIME type
WORKSPACE_MIME_MAP = {
    "application/vnd.google-apps.document": "document",
    "application/vnd.google-apps.spreadsheet": "sheet",
    "application/vnd.google-apps.presentation": "slides",
    "application/vnd.google-apps.drawing": "drawing",
}


def get_file_metadata(service, file_id: str) -> dict:
    """Get file metadata from Google Drive.

    Args:
        service: Authenticated Drive service.
        file_id: The file ID.

    Returns:
        File metadata dictionary.
    """
    try:
        return service.files().get(
            fileId=file_id,
            fields="id, name, mimeType, size, createdTime, modifiedTime, exportLinks, webContentLink",
        ).execute()
    except HttpError as e:
        error_info = handle_api_error(e, f"Get file metadata: {file_id}")
        raise


def detect_file_type(metadata: dict) -> str:
    """Detect the type of a Google Workspace file.

    Args:
        metadata: File metadata dictionary.

    Returns:
        File type string (document, sheet, slides, drawing) or 'binary'.
    """
    mime_type = metadata.get("mimeType", "")
    return WORKSPACE_MIME_MAP.get(mime_type, "binary")


def download_binary_file(
    service,
    file_id: str,
    output_path: str,
    json_output: bool = False,
) -> dict:
    """Download a non-Google-Workspace file.

    Args:
        service: Authenticated Drive service.
        file_id: The file ID.
        output_path: Path to save the file.
        json_output: Whether output will be JSON.

    Returns:
        Download result dictionary.
    """
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    try:
        request = service.files().get_media(fileId=file_id)

        with open(output, "wb") as f:
            downloader = MediaIoBaseDownload(f, request, chunksize=1024 * 1024)
            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status and not json_output:
                    logger.info("Download progress: %.1f%%", status.progress() * 100)

        file_size = output.stat().st_size
        if not json_output:
            logger.info("Downloaded: %s (%s)", output, _format_size(file_size))

        return {
            "file_id": file_id,
            "output_path": str(output),
            "size": file_size,
            "status": "success",
        }

    except HttpError as e:
        error_info = handle_api_error(e, f"Download file: {file_id}")
        raise


def export_google_file(
    service,
    file_id: str,
    export_format: str,
    output_path: str = None,
    stdout: bool = False,
    json_output: bool = False,
) -> dict:
    """Export a Google Workspace file to a specific format.

    Args:
        service: Authenticated Drive service.
        file_id: The file ID.
        export_format: Export format (text, pdf, csv, xlsx, etc.).
        output_path: Path to save the exported file.
        stdout: Print content to stdout instead of saving.
        json_output: Whether output will be JSON.

    Returns:
        Export result dictionary.
    """
    # Get file metadata to determine type
    metadata = get_file_metadata(service, file_id)
    file_type = detect_file_type(metadata)
    file_name = metadata.get("name", "unknown")

    if file_type == "binary":
        raise ValueError(
            f"File '{file_name}' is not a Google Workspace file. "
            f"Use download mode instead. MIME type: {metadata.get('mimeType')}"
        )

    # Get export MIME type
    if file_type not in EXPORT_MIME_TYPES:
        raise ValueError(f"Unsupported file type: {file_type}")

    if export_format not in EXPORT_MIME_TYPES[file_type]:
        available = ", ".join(EXPORT_MIME_TYPES[file_type].keys())
        raise ValueError(
            f"Unsupported export format '{export_format}' for {file_type}. "
            f"Available: {available}"
        )

    export_mime = EXPORT_MIME_TYPES[file_type][export_format]

    # Determine output path if not provided
    if output_path is None and not stdout:
        ext_map = {
            "text": ".txt",
            "markdown": ".md",
            "html": ".html",
            "pdf": ".pdf",
            "docx": ".docx",
            "rtf": ".rtf",
            "odt": ".odt",
            "epub": ".epub",
            "csv": ".csv",
            "xlsx": ".xlsx",
            "ods": ".ods",
            "tsv": ".tsv",
            "zip": ".zip",
            "pptx": ".pptx",
            "txt": ".txt",
            "jpg": ".jpg",
            "png": ".png",
            "svg": ".svg",
        }
        ext = ext_map.get(export_format, f".{export_format}")
        output_path = f"{file_name}{ext}"

    try:
        request = service.files().export_media(
            fileId=file_id,
            mimeType=export_mime,
        )

        if stdout:
            # Download to memory and print
            import io
            buffer = io.BytesIO()
            downloader = MediaIoBaseDownload(buffer, request, chunksize=1024 * 1024)
            done = False
            while not done:
                status, done = downloader.next_chunk()

            # For text formats, decode and print
            if export_mime.startswith("text/") or export_mime == "text/csv":
                buffer.seek(0)
                content = buffer.read().decode("utf-8", errors="replace")
                print(content, end="")
            else:
                # For binary formats, write to stdout as bytes
                buffer.seek(0)
                sys.stdout.buffer.write(buffer.read())

            return {
                "file_id": file_id,
                "file_name": file_name,
                "export_format": export_format,
                "export_mime": export_mime,
                "output": "stdout",
                "status": "success",
            }
        else:
            # Save to file
            output = Path(output_path)
            output.parent.mkdir(parents=True, exist_ok=True)

            with open(output, "wb") as f:
                downloader = MediaIoBaseDownload(f, request, chunksize=1024 * 1024)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    if status and not json_output:
                        logger.info("Export progress: %.1f%%", status.progress() * 100)

            file_size = output.stat().st_size
            if not json_output:
                logger.info(
                    "Exported: %s -> %s (%s)",
                    file_name,
                    output,
                    _format_size(file_size),
                )

            return {
                "file_id": file_id,
                "file_name": file_name,
                "export_format": export_format,
                "export_mime": export_mime,
                "output_path": str(output),
                "size": file_size,
                "status": "success",
            }

    except HttpError as e:
        error_info = handle_api_error(e, f"Export file: {file_id} as {export_format}")
        raise


def download_file(
    service,
    file_id: str,
    output_path: str = None,
    export_as: str = None,
    stdout: bool = False,
    json_output: bool = False,
) -> dict:
    """Download or export a file from Google Drive.

    Automatically detects whether the file is a Google Workspace file
    and chooses the appropriate download method.

    Args:
        service: Authenticated Drive service.
        file_id: The file ID.
        output_path: Path to save the file.
        export_as: Export format for Google Workspace files.
        stdout: Print content to stdout.
        json_output: Whether output will be JSON.

    Returns:
        Result dictionary.
    """
    # Get file metadata
    metadata = get_file_metadata(service, file_id)
    file_type = detect_file_type(metadata)

    if file_type != "binary":
        # Google Workspace file - must export
        if not export_as:
            available = ", ".join(EXPORT_MIME_TYPES.get(file_type, {}).keys())
            raise ValueError(
                f"File '{metadata.get('name')}' is a Google {file_type.title()}. "
                f"Specify --export-as format. Available: {available}"
            )
        return export_google_file(
            service=service,
            file_id=file_id,
            export_format=export_as,
            output_path=output_path,
            stdout=stdout,
            json_output=json_output,
        )
    else:
        # Regular file - download directly
        if export_as:
            logger.warning(
                "--export-as is ignored for non-Google-Workspace files"
            )
        return download_binary_file(
            service=service,
            file_id=file_id,
            output_path=output_path or metadata.get("name", "downloaded_file"),
            json_output=json_output,
        )


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
        description="Download and export files from Google Drive",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --file-id "FILE_ID" --output ./download.pdf
  %(prog)s --file-id "DOC_ID" --export-as text
  %(prog)s --file-id "DOC_ID" --export-as markdown --output ./notes.md
  %(prog)s --file-id "SHEET_ID" --export-as csv
  %(prog)s --file-id "DOC_ID" --stdout
  %(prog)s --file-id "FILE_ID" --json

Export formats by file type:
  Google Docs:    text, markdown, html, pdf, docx, rtf, odt, epub
  Google Sheets:  csv, xlsx, pdf, ods, tsv, html, zip
  Google Slides:  pdf, pptx, txt, jpg, png, svg
        """,
    )

    parser.add_argument(
        "--file-id", "-f",
        required=True,
        help="File ID to download",
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file path (default: auto-generated from file name)",
    )
    parser.add_argument(
        "--export-as", "-e",
        choices=[
            "text", "markdown", "html", "pdf", "docx", "rtf", "odt", "epub",
            "csv", "xlsx", "ods", "tsv", "zip",
            "pptx", "txt", "jpg", "png", "svg",
        ],
        help="Export format for Google Workspace files",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print content to stdout instead of saving to file",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output as JSON",
    )
    parser.add_argument(
        "--info",
        action="store_true",
        help="Only show file info, don't download",
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
        if args.info:
            # Just show file info
            metadata = get_file_metadata(service, args.file_id)
            if args.json_output:
                print(json.dumps(metadata, indent=2))
            else:
                print(f"Name: {metadata.get('name')}")
                print(f"ID: {metadata.get('id')}")
                print(f"Type: {metadata.get('mimeType')}")
                if metadata.get("size"):
                    print(f"Size: {_format_size(int(metadata['size']))}")
                if metadata.get("modifiedTime"):
                    print(f"Modified: {metadata['modifiedTime']}")
                if metadata.get("webViewLink"):
                    print(f"URL: {metadata['webViewLink']}")
        else:
            result = download_file(
                service=service,
                file_id=args.file_id,
                output_path=args.output,
                export_as=args.export_as,
                stdout=args.stdout,
                json_output=args.json_output,
            )

            if args.json_output:
                print(json.dumps(result, indent=2))
            else:
                print(f"\nSuccess!")
                print(f"  File: {result.get('file_name', 'Unknown')}")
                if result.get("output_path"):
                    print(f"  Saved to: {result['output_path']}")
                if result.get("size"):
                    print(f"  Size: {_format_size(result['size'])}")

    except HttpError as e:
        error_info = handle_api_error(e, f"Download file: {args.file_id}")
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
                "context": f"Download file: {args.file_id}",
                "suggested_action": "Check the error message and try again",
            })
        else:
            print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
