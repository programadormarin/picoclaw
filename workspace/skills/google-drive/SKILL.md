---
name: google-drive
description: "Manage Google Drive files, folders, and documents. Use when the user asks to: (1) List, search, or navigate Drive files and folders, (2) Create new files (Docs, Sheets, Slides, or any file type), (3) Read, download, or export Drive files, (4) Edit or update existing Drive files, (5) Organize folders, move files, or manage Drive structure, (6) Share files or manage permissions. Supports both OAuth2 (user accounts) and Service Account (server-to-server) authentication."
metadata: {"nanobot":{"emoji":"📁","requires":{"bins":["python3"],"env":["GOOGLE_DRIVE_CREDENTIALS_PATH","GOOGLE_DRIVE_TOKEN_PATH"]}}}
---

# Google Drive

Manage Google Drive files, folders, and documents using the official Google API Python client.

## Prerequisites

Install dependencies once:

```bash
pip install -r scripts/requirements.txt
```

Configure credentials (choose one):

**Option A: OAuth2 (user account, recommended for personal use)**
- Set `GOOGLE_DRIVE_CREDENTIALS_PATH` to your `credentials.json` (downloaded from Google Cloud Console)
- First run will open a browser for authorization and save `token.json`
- Set `GOOGLE_DRIVE_TOKEN_PATH` to customize token location (default: `~/.picoclaw/workspace/skills/google-drive/token.json`)

**Option B: Service Account (server-to-server, recommended for automation)**
- Set `GOOGLE_DRIVE_CREDENTIALS_PATH` to your service account JSON key file
- Share Drive files/folders with the service account email (found in the key file)
- No browser authorization needed

See `references/authentication.md` for detailed setup instructions.

## Quick Reference

All scripts support `--help` for full option listings. Common patterns:

```bash
# List recent files
python3 scripts/gdrive_list.py --limit 10

# Search for files
python3 scripts/gdrive_list.py --query "name contains 'report'"

# Create a folder
python3 scripts/gdrive_folders.py create --name "Project Files"

# Upload a file
python3 scripts/gdrive_upload.py upload --file /path/to/local.pdf --parent-folder-id "FOLDER_ID"

# Download a file
python3 scripts/gdrive_download.py --file-id "FILE_ID" --output /path/to/output.pdf

# Read a Google Doc as text
python3 scripts/gdrive_download.py --file-id "DOC_ID" --export-as text

# Edit a file's metadata
python3 scripts/gdrive_edit.py rename --file-id "FILE_ID" --new-name "New Name"
```

## Authentication

Authentication is handled automatically by scripts using environment variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `GOOGLE_DRIVE_CREDENTIALS_PATH` | Yes | Path to `credentials.json` (OAuth2) or service account JSON key |
| `GOOGLE_DRIVE_TOKEN_PATH` | No (OAuth2 only) | Path to save/load OAuth2 token (default: `token.json` in skill dir) |
| `GOOGLE_DRIVE_SCOPES` | No | Space-separated scopes (default: full Drive access) |

Scripts auto-detect auth method based on the credentials file format.

## File Listing and Searching

Use `scripts/gdrive_list.py`:

```bash
# List recent files (default: 20)
python3 scripts/gdrive_list.py --limit 20

# List files in a specific folder
python3 scripts/gdrive_list.py --folder-id "FOLDER_ID"

# Search with query (Google Drive query syntax)
python3 scripts/gdrive_list.py --query "mimeType='application/vnd.google-apps.document'"

# Filter by MIME type
python3 scripts/gdrive_list.py --mime-type "application/vnd.google-apps.spreadsheet"

# List trashed files
python3 scripts/gdrive_list.py --trashed

# Output as JSON for programmatic use
python3 scripts/gdrive_list.py --json
```

Common query patterns:
- `name contains 'keyword'` — search by name
- `modifiedTime > '2024-01-01'` — filter by date
- `starred = true` — starred files only
- `sharedWithMe` — files shared with you

## File Creation and Uploading

Use `scripts/gdrive_upload.py`:

```bash
# Upload a file to root
python3 scripts/gdrive_upload.py upload --file /path/to/document.pdf

# Upload to a specific folder
python3 scripts/gdrive_upload.py upload --file /path/to/document.pdf --parent-folder-id "FOLDER_ID"

# Create a Google Doc from text
python3 scripts/gdrive_upload.py create-doc --title "Meeting Notes" --content "Content here..."

# Create a Google Sheet from CSV
python3 scripts/gdrive_upload.py create-sheet --title "Data" --csv-file /path/to/data.csv

# Create a blank Google Doc/Sheet/Slides
python3 scripts/gdrive_upload.py create-blank --type document --title "New Doc"
python3 scripts/gdrive_upload.py create-blank --type spreadsheet --title "New Sheet"
python3 scripts/gdrive_upload.py create-blank --type presentation --title "New Slides"
```

Supported upload types (auto-detected by extension):
- PDF, DOCX, XLSX, PPTX → converted to Google Workspace format if desired
- TXT, MD → Google Docs
- CSV → Google Sheets
- Images, videos, archives → stored as-is

## File Reading and Downloading

Use `scripts/gdrive_download.py`:

```bash
# Download a file (auto-detects format)
python3 scripts/gdrive_download.py --file-id "FILE_ID" --output /path/to/output

# Export Google Doc as plain text
python3 scripts/gdrive_download.py --file-id "DOC_ID" --export-as text

# Export Google Doc as Markdown
python3 scripts/gdrive_download.py --file-id "DOC_ID" --export-as markdown

# Export Google Doc as PDF
python3 scripts/gdrive_download.py --file-id "DOC_ID" --export-as pdf

# Export Google Sheet as CSV
python3 scripts/gdrive_download.py --file-id "SHEET_ID" --export-as csv

# Export Google Sheet as Excel
python3 scripts/gdrive_download.py --file-id "SHEET_ID" --export-as xlsx

# Export Google Slides as PDF
python3 scripts/gdrive_download.py --file-id "SLIDES_ID" --export-as pdf

# Print file content to stdout (good for text files)
python3 scripts/gdrive_download.py --file-id "FILE_ID" --stdout
```

## File Editing and Updating

Use `scripts/gdrive_edit.py`:

```bash
# Rename a file
python3 scripts/gdrive_edit.py rename --file-id "FILE_ID" --new-name "New Name"

# Move a file to a different folder
python3 scripts/gdrive_edit.py move --file-id "FILE_ID" --to-folder-id "FOLDER_ID"

# Add a file to multiple folders
python3 scripts/gdrive_edit.py add-parents --file-id "FILE_ID" --parent-ids "FOLDER1_ID,FOLDER2_ID"

# Remove a file from a folder
python3 scripts/gdrive_edit.py remove-parents --file-id "FILE_ID" --parent-ids "FOLDER_ID"

# Star/unstar a file
python3 scripts/gdrive_edit.py star --file-id "FILE_ID"
python3 scripts/gdrive_edit.py unstar --file-id "FILE_ID"

# Update file description
python3 scripts/gdrive_edit.py update-metadata --file-id "FILE_ID" --description "New description"

# Append content to a Google Doc
python3 scripts/gdrive_edit.py append-doc --file-id "DOC_ID" --content "New paragraph..."

# Replace content in a Google Doc
python3 scripts/gdrive_edit.py replace-doc --file-id "DOC_ID" --content "Full replacement..."
```

## Folder Management

Use `scripts/gdrive_folders.py`:

```bash
# Create a folder
python3 scripts/gdrive_folders.py create --name "New Folder"

# Create a folder in a specific parent
python3 scripts/gdrive_folders.py create --name "Subfolder" --parent-folder-id "PARENT_ID"

# Create nested folders
python3 scripts/gdrive_folders.py create-tree --path "Project/Docs/2024"

# List folder contents
python3 scripts/gdrive_folders.py list --folder-id "FOLDER_ID"

# List folder contents recursively
python3 scripts/gdrive_folders.py list --folder-id "FOLDER_ID" --recursive

# Delete a folder (moves to trash)
python3 scripts/gdrive_folders.py delete --folder-id "FOLDER_ID"

# Delete permanently
python3 scripts/gdrive_folders.py delete --folder-id "FOLDER_ID" --permanent
```

## File Permissions and Sharing

Use `scripts/gdrive_edit.py`:

```bash
# Share a file with a user
python3 scripts/gdrive_edit.py share --file-id "FILE_ID" --email "user@example.com" --role reader

# Share with writer access
python3 scripts/gdrive_edit.py share --file-id "FILE_ID" --email "user@example.com" --role writer

# Share with anyone link
python3 scripts/gdrive_edit.py share --file-id "FILE_ID" --type anyone --role reader

# List permissions
python3 scripts/gdrive_edit.py list-permissions --file-id "FILE_ID"

# Remove a permission
python3 scripts/gdrive_edit.py remove-permission --file-id "FILE_ID" --permission-id "PERMISSION_ID"
```

Valid roles: `owner`, `organizer`, `fileOrganizer`, `writer`, `commenter`, `reader`
Valid types: `user`, `group`, `domain`, `anyone`

## Error Handling

All scripts include:
- Structured error messages with actionable guidance
- HTTP error code handling with retry suggestions
- Authentication error detection with setup instructions
- Rate limit handling with exponential backoff
- JSON output mode (`--json`) for programmatic error parsing

Common errors:
- `403 Forbidden` — check file permissions or share the file with the service account
- `404 Not Found` — verify the file/folder ID is correct
- `401 Unauthorized` — re-run authentication or check credentials
- `403 rateLimitExceeded` — wait and retry (scripts include automatic backoff)

## Best Practices

- Use `--json` flag when integrating with other tools or scripts
- Prefer `--folder-id` over `--query` for listing specific folders (faster)
- Google Workspace files (Docs, Sheets, Slides) must be exported, not downloaded directly
- Service accounts can only access files explicitly shared with them
- Large file uploads (>10MB) use resumable upload automatically
- Always use file IDs (not names) for operations when possible — names are not unique
