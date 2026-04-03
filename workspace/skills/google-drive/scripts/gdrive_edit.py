#!/usr/bin/env python3
"""
Google Drive File Editing and Updating Script

Rename, move, share, and modify files in Google Drive.

Usage:
    # Rename a file
    python3 gdrive_edit.py rename --file-id "FILE_ID" --new-name "New Name"

    # Move a file to a different folder
    python3 gdrive_edit.py move --file-id "FILE_ID" --to-folder-id "FOLDER_ID"

    # Share a file with a user
    python3 gdrive_edit.py share --file-id "FILE_ID" --email "user@example.com" --role reader

    # List permissions
    python3 gdrive_edit.py list-permissions --file-id "FILE_ID"

    # Append content to a Google Doc
    python3 gdrive_edit.py append-doc --file-id "DOC_ID" --content "New paragraph..."

Environment Variables:
    GOOGLE_DRIVE_CREDENTIALS_PATH: Path to credentials file (required)
    GOOGLE_DRIVE_TOKEN_PATH: Path to OAuth2 token (optional)
    GOOGLE_DRIVE_SCOPES: Space-separated scopes (optional)
"""

import argparse
import json
import logging
import sys

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

# Valid permission roles
VALID_ROLES = [
    "owner", "organizer", "fileOrganizer", "writer", "commenter", "reader"
]

# Valid permission types
VALID_TYPES = ["user", "group", "domain", "anyone"]


def rename_file(
    service,
    file_id: str,
    new_name: str,
    json_output: bool = False,
) -> dict:
    """Rename a file in Google Drive.

    Args:
        service: Authenticated Drive service.
        file_id: The file ID.
        new_name: New file name.
        json_output: Whether output will be JSON.

    Returns:
        Updated file metadata.
    """
    try:
        updated_file = service.files().update(
            fileId=file_id,
            body={"name": new_name},
            fields="id, name, mimeType, webViewLink, modifiedTime",
        ).execute()

        if not json_output:
            logger.info("Renamed to: %s", new_name)

        return updated_file

    except HttpError as e:
        error_info = handle_api_error(e, f"Rename file: {file_id}")
        raise


def move_file(
    service,
    file_id: str,
    to_folder_id: str,
    json_output: bool = False,
) -> dict:
    """Move a file to a different folder.

    This removes the file from its current parent folders and adds it
    to the specified folder.

    Args:
        service: Authenticated Drive service.
        file_id: The file ID.
        to_folder_id: Destination folder ID.
        json_output: Whether output will be JSON.

    Returns:
        Updated file metadata.
    """
    try:
        # Get current parents
        file_metadata = service.files().get(
            fileId=file_id,
            fields="parents",
        ).execute()

        current_parents = ",".join(file_metadata.get("parents", []))

        # Move the file
        updated_file = service.files().update(
            fileId=file_id,
            addParents=to_folder_id,
            removeParents=current_parents,
            fields="id, name, mimeType, parents, webViewLink, modifiedTime",
        ).execute()

        if not json_output:
            logger.info("Moved to folder: %s", to_folder_id)

        return updated_file

    except HttpError as e:
        error_info = handle_api_error(e, f"Move file: {file_id}")
        raise


def add_parents(
    service,
    file_id: str,
    parent_ids: list[str],
    json_output: bool = False,
) -> dict:
    """Add a file to additional folders (without removing from current ones).

    Args:
        service: Authenticated Drive service.
        file_id: The file ID.
        parent_ids: List of folder IDs to add.
        json_output: Whether output will be JSON.

    Returns:
        Updated file metadata.
    """
    try:
        updated_file = service.files().update(
            fileId=file_id,
            addParents=",".join(parent_ids),
            fields="id, name, mimeType, parents, webViewLink, modifiedTime",
        ).execute()

        if not json_output:
            logger.info("Added to %d folder(s)", len(parent_ids))

        return updated_file

    except HttpError as e:
        error_info = handle_api_error(e, f"Add parents to file: {file_id}")
        raise


def remove_parents(
    service,
    file_id: str,
    parent_ids: list[str],
    json_output: bool = False,
) -> dict:
    """Remove a file from specific folders.

    Args:
        service: Authenticated Drive service.
        file_id: The file ID.
        parent_ids: List of folder IDs to remove from.
        json_output: Whether output will be JSON.

    Returns:
        Updated file metadata.
    """
    try:
        updated_file = service.files().update(
            fileId=file_id,
            removeParents=",".join(parent_ids),
            fields="id, name, mimeType, parents, webViewLink, modifiedTime",
        ).execute()

        if not json_output:
            logger.info("Removed from %d folder(s)", len(parent_ids))

        return updated_file

    except HttpError as e:
        error_info = handle_api_error(e, f"Remove parents from file: {file_id}")
        raise


def star_file(
    service,
    file_id: str,
    json_output: bool = False,
) -> dict:
    """Star a file.

    Args:
        service: Authenticated Drive service.
        file_id: The file ID.
        json_output: Whether output will be JSON.

    Returns:
        Updated file metadata.
    """
    try:
        updated_file = service.files().update(
            fileId=file_id,
            body={"starred": True},
            fields="id, name, mimeType, starred, webViewLink, modifiedTime",
        ).execute()

        if not json_output:
            logger.info("File starred")

        return updated_file

    except HttpError as e:
        error_info = handle_api_error(e, f"Star file: {file_id}")
        raise


def unstar_file(
    service,
    file_id: str,
    json_output: bool = False,
) -> dict:
    """Unstar a file.

    Args:
        service: Authenticated Drive service.
        file_id: The file ID.
        json_output: Whether output will be JSON.

    Returns:
        Updated file metadata.
    """
    try:
        updated_file = service.files().update(
            fileId=file_id,
            body={"starred": False},
            fields="id, name, mimeType, starred, webViewLink, modifiedTime",
        ).execute()

        if not json_output:
            logger.info("File unstarred")

        return updated_file

    except HttpError as e:
        error_info = handle_api_error(e, f"Unstar file: {file_id}")
        raise


def update_metadata(
    service,
    file_id: str,
    description: str = None,
    starred: bool = None,
    json_output: bool = False,
) -> dict:
    """Update file metadata.

    Args:
        service: Authenticated Drive service.
        file_id: The file ID.
        description: New description.
        starred: Set starred status.
        json_output: Whether output will be JSON.

    Returns:
        Updated file metadata.
    """
    body = {}
    if description is not None:
        body["description"] = description
    if starred is not None:
        body["starred"] = starred

    try:
        updated_file = service.files().update(
            fileId=file_id,
            body=body,
            fields="id, name, mimeType, description, starred, webViewLink, modifiedTime",
        ).execute()

        if not json_output:
            logger.info("Metadata updated")

        return updated_file

    except HttpError as e:
        error_info = handle_api_error(e, f"Update metadata: {file_id}")
        raise


def share_file(
    service,
    file_id: str,
    email: str = None,
    role: str = "reader",
    perm_type: str = "user",
    domain: str = None,
    send_notification: bool = True,
    email_message: str = None,
    json_output: bool = False,
) -> dict:
    """Share a file with a user, group, domain, or anyone.

    Args:
        service: Authenticated Drive service.
        file_id: The file ID.
        email: Email address (for user/group type).
        role: Permission role (reader, writer, commenter, etc.).
        perm_type: Permission type (user, group, domain, anyone).
        domain: Domain name (for domain type).
        send_notification: Send email notification.
        email_message: Custom email message.
        json_output: Whether output will be JSON.

    Returns:
        Permission metadata.
    """
    if role not in VALID_ROLES:
        raise ValueError(f"Invalid role: {role}. Must be one of: {', '.join(VALID_ROLES)}")

    if perm_type not in VALID_TYPES:
        raise ValueError(f"Invalid type: {perm_type}. Must be one of: {', '.join(VALID_TYPES)}")

    # Build permission body
    permission = {"type": perm_type, "role": role}

    if perm_type in ("user", "group") and email:
        permission["emailAddress"] = email
    elif perm_type == "domain" and domain:
        permission["domain"] = domain
    elif perm_type == "anyone":
        pass  # No additional fields needed
    elif perm_type in ("user", "group") and not email:
        raise ValueError(f"Email is required for type '{perm_type}'")

    try:
        new_permission = service.permissions().create(
            fileId=file_id,
            body=permission,
            sendNotificationEmail=send_notification and perm_type in ("user", "group"),
            emailMessage=email_message,
            fields="id, type, role, emailAddress, domain, displayName",
        ).execute()

        if not json_output:
            target = email or domain or "anyone"
            logger.info("Shared with %s (%s): %s", target, perm_type, role)

        return new_permission

    except HttpError as e:
        error_info = handle_api_error(e, f"Share file: {file_id}")
        raise


def list_permissions(
    service,
    file_id: str,
    json_output: bool = False,
) -> list[dict]:
    """List all permissions on a file.

    Args:
        service: Authenticated Drive service.
        file_id: The file ID.
        json_output: Whether output will be JSON.

    Returns:
        List of permission dictionaries.
    """
    try:
        permissions = service.permissions().list(
            fileId=file_id,
            fields="permissions(id, type, role, emailAddress, domain, displayName)",
        ).execute()

        perm_list = permissions.get("permissions", [])

        if not json_output:
            if not perm_list:
                print("No permissions found.")
            else:
                print(f"Permissions for file ID: {file_id}\n")
                for perm in perm_list:
                    target = (
                        perm.get("emailAddress")
                        or perm.get("domain")
                        or perm.get("type")
                    )
                    print(f"  ID: {perm.get('id')}")
                    print(f"  Type: {perm.get('type')}")
                    print(f"  Role: {perm.get('role')}")
                    print(f"  Target: {target}")
                    if perm.get("displayName"):
                        print(f"  Name: {perm.get('displayName')}")
                    print()

        return perm_list

    except HttpError as e:
        error_info = handle_api_error(e, f"List permissions: {file_id}")
        raise


def remove_permission(
    service,
    file_id: str,
    permission_id: str,
    json_output: bool = False,
) -> None:
    """Remove a permission from a file.

    Args:
        service: Authenticated Drive service.
        file_id: The file ID.
        permission_id: The permission ID to remove.
        json_output: Whether output will be JSON.
    """
    try:
        service.permissions().delete(
            fileId=file_id,
            permissionId=permission_id,
        ).execute()

        if not json_output:
            logger.info("Permission removed: %s", permission_id)

    except HttpError as e:
        error_info = handle_api_error(e, f"Remove permission: {permission_id}")
        raise


def append_to_google_doc(
    service,
    file_id: str,
    content: str,
    content_file: str = None,
    json_output: bool = False,
) -> dict:
    """Append content to a Google Doc.

    Args:
        service: Authenticated Drive service.
        file_id: The document ID.
        content: Content to append.
        content_file: Read content from file instead.
        json_output: Whether output will be JSON.

    Returns:
        Document metadata.
    """
    if content_file:
        with open(content_file, "r", encoding="utf-8") as f:
            content = f.read()

    try:
        # First, get the document to find the end index
        docs_service = _get_docs_service(service._http.credentials)
        doc = docs_service.documents().get(documentId=file_id).execute()

        # Find the end of the document (handle empty documents)
        doc_content = doc.get("body", {}).get("content", [])
        if not doc_content:
            end_index = 1  # Default for empty documents
        else:
            end_index = doc_content[-1]["endIndex"]

        # Append content
        requests = [
            {
                "insertText": {
                    "location": {"index": end_index - 1},
                    "text": "\n" + content,
                }
            }
        ]

        docs_service.documents().batchUpdate(
            documentId=file_id,
            body={"requests": requests},
        ).execute()

        # Get updated document info
        drive_file = service.files().get(
            fileId=file_id,
            fields="id, name, mimeType, webViewLink, modifiedTime",
        ).execute()

        if not json_output:
            logger.info("Content appended to: %s", drive_file.get("name"))

        return drive_file

    except HttpError as e:
        error_info = handle_api_error(e, f"Append to document: {file_id}")
        raise


def replace_google_doc(
    service,
    file_id: str,
    content: str,
    content_file: str = None,
    json_output: bool = False,
) -> dict:
    """Replace all content in a Google Doc.

    Args:
        service: Authenticated Drive service.
        file_id: The document ID.
        content: New content.
        content_file: Read content from file instead.
        json_output: Whether output will be JSON.

    Returns:
        Document metadata.
    """
    if content_file:
        with open(content_file, "r", encoding="utf-8") as f:
            content = f.read()

    try:
        docs_service = _get_docs_service(service._http.credentials)

        # Get document to find content range
        doc = docs_service.documents().get(documentId=file_id).execute()

        # Find the content start and end (skip document title, handle empty docs)
        content_start = 1
        doc_body_content = doc.get("body", {}).get("content", [])
        if not doc_body_content:
            content_end = 1  # Empty document
        else:
            content_end = doc_body_content[-1]["endIndex"] - 1

        # Delete existing content and insert new content
        requests = [
            {
                "deleteContentRange": {
                    "range": {
                        "startIndex": content_start,
                        "endIndex": content_end,
                    }
                }
            },
            {
                "insertText": {
                    "location": {"index": content_start},
                    "text": content,
                }
            },
        ]

        docs_service.documents().batchUpdate(
            documentId=file_id,
            body={"requests": requests},
        ).execute()

        # Get updated document info
        drive_file = service.files().get(
            fileId=file_id,
            fields="id, name, mimeType, webViewLink, modifiedTime",
        ).execute()

        if not json_output:
            logger.info("Content replaced in: %s", drive_file.get("name"))

        return drive_file

    except HttpError as e:
        error_info = handle_api_error(e, f"Replace document content: {file_id}")
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


def build_parser() -> argparse.ArgumentParser:
    """Build argument parser."""
    parser = argparse.ArgumentParser(
        description="Edit and update files in Google Drive",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Rename
    rename_parser = subparsers.add_parser("rename", help="Rename a file")
    rename_parser.add_argument("--file-id", "-f", required=True, help="File ID")
    rename_parser.add_argument("--new-name", "-n", required=True, help="New file name")

    # Move
    move_parser = subparsers.add_parser("move", help="Move a file to a folder")
    move_parser.add_argument("--file-id", "-f", required=True, help="File ID")
    move_parser.add_argument("--to-folder-id", "-t", required=True, help="Destination folder ID")

    # Add parents
    add_parents_parser = subparsers.add_parser("add-parents", help="Add file to additional folders")
    add_parents_parser.add_argument("--file-id", "-f", required=True, help="File ID")
    add_parents_parser.add_argument(
        "--parent-ids", "-p", required=True,
        help="Comma-separated folder IDs",
    )

    # Remove parents
    remove_parents_parser = subparsers.add_parser("remove-parents", help="Remove file from folders")
    remove_parents_parser.add_argument("--file-id", "-f", required=True, help="File ID")
    remove_parents_parser.add_argument(
        "--parent-ids", "-p", required=True,
        help="Comma-separated folder IDs",
    )

    # Star
    star_parser = subparsers.add_parser("star", help="Star a file")
    star_parser.add_argument("--file-id", "-f", required=True, help="File ID")

    # Unstar
    unstar_parser = subparsers.add_parser("unstar", help="Unstar a file")
    unstar_parser.add_argument("--file-id", "-f", required=True, help="File ID")

    # Update metadata
    metadata_parser = subparsers.add_parser("update-metadata", help="Update file metadata")
    metadata_parser.add_argument("--file-id", "-f", required=True, help="File ID")
    metadata_parser.add_argument("--description", "-d", help="New description")

    # Share
    share_parser = subparsers.add_parser("share", help="Share a file")
    share_parser.add_argument("--file-id", "-f", required=True, help="File ID")
    share_parser.add_argument("--email", "-e", help="Email address to share with")
    share_parser.add_argument(
        "--role", "-r",
        default="reader",
        choices=VALID_ROLES,
        help="Permission role (default: reader)",
    )
    share_parser.add_argument(
        "--type", "-t",
        default="user",
        choices=VALID_TYPES,
        help="Permission type (default: user)",
    )
    share_parser.add_argument("--domain", help="Domain name (for domain type)")
    share_parser.add_argument(
        "--no-notification",
        action="store_true",
        help="Don't send email notification",
    )
    share_parser.add_argument("--message", "-m", help="Email message")

    # List permissions
    list_perms_parser = subparsers.add_parser("list-permissions", help="List file permissions")
    list_perms_parser.add_argument("--file-id", "-f", required=True, help="File ID")

    # Remove permission
    remove_perm_parser = subparsers.add_parser("remove-permission", help="Remove a permission")
    remove_perm_parser.add_argument("--file-id", "-f", required=True, help="File ID")
    remove_perm_parser.add_argument("--permission-id", "-p", required=True, help="Permission ID")

    # Append to doc
    append_parser = subparsers.add_parser("append-doc", help="Append content to a Google Doc")
    append_parser.add_argument("--file-id", "-f", required=True, help="Document ID")
    append_parser.add_argument("--content", "-c", help="Content to append")
    append_parser.add_argument("--content-file", help="Read content from file")

    # Replace doc
    replace_parser = subparsers.add_parser("replace-doc", help="Replace content in a Google Doc")
    replace_parser.add_argument("--file-id", "-f", required=True, help="Document ID")
    replace_parser.add_argument("--content", "-c", help="New content")
    replace_parser.add_argument("--content-file", help="Read content from file")

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

        if args.command == "rename":
            result = rename_file(service, args.file_id, args.new_name, args.json_output)

        elif args.command == "move":
            result = move_file(service, args.file_id, args.to_folder_id, args.json_output)

        elif args.command == "add-parents":
            parent_ids = [p.strip() for p in args.parent_ids.split(",")]
            result = add_parents(service, args.file_id, parent_ids, args.json_output)

        elif args.command == "remove-parents":
            parent_ids = [p.strip() for p in args.parent_ids.split(",")]
            result = remove_parents(service, args.file_id, parent_ids, args.json_output)

        elif args.command == "star":
            result = star_file(service, args.file_id, args.json_output)

        elif args.command == "unstar":
            result = unstar_file(service, args.file_id, args.json_output)

        elif args.command == "update-metadata":
            result = update_metadata(
                service, args.file_id,
                description=args.description,
                json_output=args.json_output,
            )

        elif args.command == "share":
            result = share_file(
                service,
                file_id=args.file_id,
                email=args.email,
                role=args.role,
                perm_type=args.type,
                domain=args.domain,
                send_notification=not args.no_notification,
                email_message=args.message,
                json_output=args.json_output,
            )

        elif args.command == "list-permissions":
            result = list_permissions(service, args.file_id, args.json_output)

        elif args.command == "remove-permission":
            result = remove_permission(
                service, args.file_id, args.permission_id, args.json_output
            )

        elif args.command == "append-doc":
            if not args.content and not args.content_file:
                parser.error("--content or --content-file is required for append-doc")
            result = append_to_google_doc(
                service, args.file_id,
                content=args.content,
                content_file=args.content_file,
                json_output=args.json_output,
            )

        elif args.command == "replace-doc":
            if not args.content and not args.content_file:
                parser.error("--content or --content-file is required for replace-doc")
            result = replace_google_doc(
                service, args.file_id,
                content=args.content,
                content_file=args.content_file,
                json_output=args.json_output,
            )

        else:
            parser.print_help()
            sys.exit(1)

        if result and args.json_output:
            print(json.dumps({"success": True, "result": result}, indent=2))
        elif result and not isinstance(result, list):
            print(f"\nSuccess!")
            print(f"  Name: {result.get('name', 'N/A')}")
            print(f"  ID: {result.get('id', 'N/A')}")
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
