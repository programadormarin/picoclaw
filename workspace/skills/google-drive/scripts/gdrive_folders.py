#!/usr/bin/env python3
"""
Google Drive Folder Management Script

Create, list, delete, and manage folders in Google Drive.

Usage:
    # Create a folder
    python3 gdrive_folders.py create --name "New Folder"

    # Create a folder in a specific parent
    python3 gdrive_folders.py create --name "Subfolder" --parent-folder-id "PARENT_ID"

    # Create nested folders
    python3 gdrive_folders.py create-tree --path "Project/Docs/2024"

    # List folder contents
    python3 gdrive_folders.py list --folder-id "FOLDER_ID"

    # List folder contents recursively
    python3 gdrive_folders.py list --folder-id "FOLDER_ID" --recursive

    # Delete a folder (moves to trash)
    python3 gdrive_folders.py delete --folder-id "FOLDER_ID"

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

FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"


def create_folder(
    service,
    name: str,
    parent_folder_id: str = None,
    description: str = None,
    json_output: bool = False,
) -> dict:
    """Create a folder in Google Drive.

    Args:
        service: Authenticated Drive service.
        name: Folder name.
        parent_folder_id: Parent folder ID (default: root).
        description: Folder description.
        json_output: Whether output will be JSON.

    Returns:
        Folder metadata dictionary.
    """
    file_metadata = {
        "name": name,
        "mimeType": FOLDER_MIME_TYPE,
    }

    if parent_folder_id:
        file_metadata["parents"] = [parent_folder_id]

    if description:
        file_metadata["description"] = description

    try:
        folder = service.files().create(
            body=file_metadata,
            fields="id, name, mimeType, webViewLink, createdTime, modifiedTime, parents",
        ).execute()

        if not json_output:
            location = f"in folder {parent_folder_id}" if parent_folder_id else "in root"
            logger.info("Folder created: %s (%s) %s", name, folder.get("id"), location)

        return folder

    except HttpError as e:
        error_info = handle_api_error(e, f"Create folder: {name}")
        raise


def create_folder_tree(
    service,
    path: str,
    parent_folder_id: str = None,
    json_output: bool = False,
) -> dict:
    """Create a nested folder structure.

    Args:
        service: Authenticated Drive service.
        path: Folder path (e.g., "Project/Docs/2024").
        parent_folder_id: Starting parent folder (default: root).
        json_output: Whether output will be JSON.

    Returns:
        Dictionary with created folder IDs.
    """
    # Split path and filter empty parts
    parts = [p.strip() for p in path.split("/") if p.strip()]

    if not parts:
        raise ValueError("Invalid path: must contain at least one folder name")

    created_folders = []
    current_parent = parent_folder_id

    for part in parts:
        folder = create_folder(
            service=service,
            name=part,
            parent_folder_id=current_parent,
            json_output=json_output,
        )
        created_folders.append({
            "name": part,
            "id": folder.get("id"),
            "parent_id": current_parent,
        })
        current_parent = folder.get("id")

    if not json_output:
        logger.info("Created %d folder(s): %s", len(created_folders), " -> ".join(parts))

    return {
        "path": path,
        "folders": created_folders,
        "leaf_folder_id": current_parent,
    }


def list_folder_contents(
    service,
    folder_id: str = None,
    recursive: bool = False,
    limit: int = 100,
    order_by: str = "folder, name",
    json_output: bool = False,
    _visited_folders: set = None,
) -> list[dict]:
    """List contents of a folder.

    Args:
        service: Authenticated Drive service.
        folder_id: Folder ID (default: root).
        recursive: List contents recursively.
        limit: Maximum number of files to return.
        order_by: Sort order.
        json_output: Whether output will be JSON.
        _visited_folders: Internal parameter to track visited folders (prevents circular refs).

    Returns:
        List of file metadata dictionaries.
    """
    # Initialize visited folders tracker
    if _visited_folders is None:
        _visited_folders = set()

    # Check for circular references
    if folder_id and folder_id in _visited_folders:
        logger.warning("Skipping circular folder reference: %s", folder_id)
        return []
    
    if folder_id:
        _visited_folders.add(folder_id)
    # Build query
    if folder_id:
        query = f"'{folder_id}' in parents and trashed=false"
    else:
        query = "'root' in parents and trashed=false"

    fields = (
        "files(id, name, mimeType, size, createdTime, modifiedTime, "
        "webViewLink, starred, parents, fileExtension), "
        "nextPageToken"
    )

    all_files = []
    page_token = None

    while True:
        request_params = {
            "q": query,
            "pageSize": min(limit, 1000),
            "fields": fields,
            "orderBy": order_by,
        }

        if page_token:
            request_params["pageToken"] = page_token

        try:
            response = service.files().list(**request_params).execute()
        except HttpError as e:
            error_info = handle_api_error(e, f"List folder contents: {folder_id}")
            raise

        files = response.get("files", [])
        all_files.extend(files)

        if len(all_files) >= limit:
            all_files = all_files[:limit]
            break

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    # If recursive, get contents of subfolders
    if recursive:
        folders = [f for f in all_files if f.get("mimeType") == FOLDER_MIME_TYPE]
        for folder in folders:
            if len(all_files) >= limit:
                break
            sub_files = list_folder_contents(
                service=service,
                folder_id=folder.get("id"),
                recursive=True,
                limit=limit - len(all_files),
                order_by=order_by,
                json_output=True,  # Suppress logging for recursive calls
                _visited_folders=_visited_folders,  # Pass visited folders to prevent cycles
            )
            all_files.extend(sub_files)

    return all_files


def delete_folder(
    service,
    folder_id: str,
    permanent: bool = False,
    json_output: bool = False,
) -> None:
    """Delete a folder.

    Args:
        service: Authenticated Drive service.
        folder_id: Folder ID.
        permanent: Permanently delete (skip trash).
        json_output: Whether output will be JSON.
    """
    try:
        if permanent:
            service.files().delete(fileId=folder_id).execute()
            if not json_output:
                logger.info("Folder permanently deleted: %s", folder_id)
        else:
            # Move to trash
            service.files().update(
                fileId=folder_id,
                body={"trashed": True},
            ).execute()
            if not json_output:
                logger.info("Folder moved to trash: %s", folder_id)

    except HttpError as e:
        error_info = handle_api_error(e, f"Delete folder: {folder_id}")
        raise


def format_folder_tree(files: list[dict], indent: str = "") -> str:
    """Format files as a folder tree.

    Args:
        files: List of file metadata.
        indent: Current indentation level.

    Returns:
        Formatted tree string.
    """
    lines = []

    # Separate folders and files
    folders = [f for f in files if f.get("mimeType") == FOLDER_MIME_TYPE]
    regular_files = [f for f in files if f.get("mimeType") != FOLDER_MIME_TYPE]

    # Sort each group
    folders.sort(key=lambda f: f.get("name", "").lower())
    regular_files.sort(key=lambda f: f.get("name", "").lower())

    # Add folders first
    for i, folder in enumerate(folders):
        is_last = (i == len(folders) - 1) and len(regular_files) == 0
        prefix = "└── " if is_last else "├── "
        child_indent = indent + ("    " if is_last else "│   ")
        lines.append(f"{indent}{prefix}📁 {folder.get('name')} ({folder.get('id')})")

    # Then files
    for i, file in enumerate(regular_files):
        is_last = i == len(regular_files) - 1
        prefix = "└── " if is_last else "├── "
        icon = _get_file_icon(file.get("mimeType", ""))
        lines.append(f"{indent}{prefix}{icon} {file.get('name')}")

    return "\n".join(lines)


def _get_file_icon(mime_type: str) -> str:
    """Get emoji icon for file type."""
    if "document" in mime_type:
        return "📝"
    elif "spreadsheet" in mime_type:
        return "📊"
    elif "presentation" in mime_type:
        return "📽️"
    elif "image" in mime_type:
        return "🖼️"
    elif "pdf" in mime_type:
        return "📕"
    elif "video" in mime_type:
        return "🎬"
    elif "audio" in mime_type:
        return "🎵"
    elif "zip" in mime_type or "archive" in mime_type:
        return "📦"
    else:
        return "📄"


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


def _format_datetime(dt_str: str) -> str:
    """Format ISO datetime string."""
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, AttributeError):
        return dt_str


def build_parser() -> argparse.ArgumentParser:
    """Build argument parser."""
    parser = argparse.ArgumentParser(
        description="Manage folders in Google Drive",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s create --name "New Folder"
  %(prog)s create --name "Subfolder" --parent-folder-id "FOLDER_ID"
  %(prog)s create-tree --path "Project/Docs/2024"
  %(prog)s list --folder-id "FOLDER_ID"
  %(prog)s list --folder-id "FOLDER_ID" --recursive
  %(prog)s delete --folder-id "FOLDER_ID"
  %(prog)s delete --folder-id "FOLDER_ID" --permanent
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Create folder
    create_parser = subparsers.add_parser("create", help="Create a folder")
    create_parser.add_argument("--name", "-n", required=True, help="Folder name")
    create_parser.add_argument(
        "--parent-folder-id", "-p",
        help="Parent folder ID (default: root)",
    )
    create_parser.add_argument("--description", "-d", help="Folder description")

    # Create folder tree
    create_tree_parser = subparsers.add_parser("create-tree", help="Create nested folders")
    create_tree_parser.add_argument(
        "--path", "-p",
        required=True,
        help="Folder path (e.g., 'Project/Docs/2024')",
    )
    create_tree_parser.add_argument(
        "--parent-folder-id",
        help="Starting parent folder ID (default: root)",
    )

    # List folder contents
    list_parser = subparsers.add_parser("list", help="List folder contents")
    list_parser.add_argument(
        "--folder-id", "-f",
        help="Folder ID (default: root)",
    )
    list_parser.add_argument(
        "--recursive", "-r",
        action="store_true",
        help="List contents recursively",
    )
    list_parser.add_argument(
        "--limit", "-n",
        type=int,
        default=100,
        help="Maximum number of items (default: 100)",
    )
    list_parser.add_argument(
        "--tree",
        action="store_true",
        help="Display as folder tree",
    )

    # Delete folder
    delete_parser = subparsers.add_parser("delete", help="Delete a folder")
    delete_parser.add_argument("--folder-id", "-f", required=True, help="Folder ID")
    delete_parser.add_argument(
        "--permanent",
        action="store_true",
        help="Permanently delete (skip trash)",
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
        result = None

        if args.command == "create":
            result = create_folder(
                service=service,
                name=args.name,
                parent_folder_id=args.parent_folder_id,
                description=args.description,
                json_output=args.json_output,
            )

        elif args.command == "create-tree":
            result = create_folder_tree(
                service=service,
                path=args.path,
                parent_folder_id=args.parent_folder_id,
                json_output=args.json_output,
            )

        elif args.command == "list":
            files = list_folder_contents(
                service=service,
                folder_id=args.folder_id,
                recursive=args.recursive,
                limit=args.limit,
                json_output=args.json_output,
            )

            if args.json_output:
                result = {"files": files, "count": len(files)}
            else:
                if not files:
                    print("Folder is empty.")
                elif args.tree:
                    print(format_folder_tree(files))
                else:
                    print(f"Found {len(files)} item(s):\n")
                    for i, file in enumerate(files):
                        if i > 0:
                            print()
                        icon = _get_file_icon(file.get("mimeType", ""))
                        name = file.get("name", "Unknown")
                        file_id = file.get("id", "Unknown")
                        size = file.get("size")
                        modified = file.get("modifiedTime")

                        print(f"{icon} {name}")
                        print(f"   ID: {file_id}")
                        if size:
                            print(f"   Size: {_format_size(int(size))}")
                        if modified:
                            print(f"   Modified: {_format_datetime(modified)}")
                        if file.get("webViewLink"):
                            print(f"   URL: {file.get('webViewLink')}")

        elif args.command == "delete":
            delete_folder(
                service=service,
                folder_id=args.folder_id,
                permanent=args.permanent,
                json_output=args.json_output,
            )
            result = {"status": "deleted", "folder_id": args.folder_id}

        else:
            parser.print_help()
            sys.exit(1)

        if result and args.json_output:
            print(json.dumps({"success": True, "result": result}, indent=2))
        elif result and args.command in ("create", "create-tree"):
            print(f"\nSuccess!")
            if args.command == "create":
                print(f"  Name: {result.get('name')}")
                print(f"  ID: {result.get('id')}")
                if result.get("webViewLink"):
                    print(f"  URL: {result.get('webViewLink')}")
            elif args.command == "create-tree":
                print(f"  Created {len(result['folders'])} folder(s)")
                print(f"  Leaf folder: {result['leaf_folder_id']}")

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
