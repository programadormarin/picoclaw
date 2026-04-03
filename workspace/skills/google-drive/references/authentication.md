# Google Drive Authentication Setup

This guide covers two authentication methods for the Google Drive skill. Choose the one that fits your use case.

## Method Comparison

| Feature | OAuth2 (User Account) | Service Account |
|---------|----------------------|-----------------|
| **Best for** | Personal use, interactive workflows | Automation, server-to-server |
| **Setup complexity** | Medium | Low |
| **Access** | Your entire Drive | Only files shared with it |
| **Browser required** | Yes (once) | No |
| **Token expiry** | Auto-refreshed | Never expires |
| **Multi-user** | No (single user) | Can impersonate users (domain-wide) |

**Recommendation**: Use OAuth2 for personal assistants, Service Account for automated/bot workflows.

---

## Method 1: OAuth2 (User Account)

### Step 1: Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click **Select a project** → **New Project**
3. Name it (e.g., "PicoClaw Drive") → **Create**
4. Wait for project creation to complete

### Step 2: Enable Google Drive API

1. Navigate to **APIs & Services** → **Library**
2. Search for "Google Drive API"
3. Click **Enable**

### Step 3: Configure OAuth Consent Screen

1. Go to **APIs & Services** → **OAuth consent screen**
2. Choose **External** (for personal use) → **Create**
3. Fill in required fields:
   - **App name**: PicoClaw Drive
   - **User support email**: your email
   - **Developer contact email**: your email
4. Click **Save and Continue**
5. **Scopes**: Add these scopes:
   - `https://www.googleapis.com/auth/drive` (Full Drive access)
   - Or for read-only: `https://www.googleapis.com/auth/drive.readonly`
6. Click **Save and Continue**
7. **Test users**: Add your Google account email → **Save and Continue**
8. Review and click **Back to Dashboard**

> **Note**: While in "Testing" mode, only added test users can access the app. This is fine for personal use. For production, submit for verification.

### Step 4: Create OAuth 2.0 Credentials

1. Go to **APIs & Services** → **Credentials**
2. Click **+ Create Credentials** → **OAuth client ID**
3. Application type: **Desktop app**
4. Name: PicoClaw
5. Click **Create**
6. Download the JSON file → save as `credentials.json`

### Step 5: Configure Environment

```bash
# Path to the downloaded credentials.json
export GOOGLE_DRIVE_CREDENTIALS_PATH="/path/to/credentials.json"

# Optional: customize token storage location
export GOOGLE_DRIVE_TOKEN_PATH="$HOME/.picoclaw/workspace/skills/google-drive/token.json"
```

### Step 6: First-Time Authorization

Run any script for the first time:

```bash
python3 scripts/gdrive_list.py --limit 1
```

This will:
1. Open a browser window
2. Ask you to sign in and grant permissions
3. Save the token to `GOOGLE_DRIVE_TOKEN_PATH` (or `token.json` in the skill directory)

Subsequent runs use the saved token automatically. Tokens refresh automatically.

---

## Method 2: Service Account

### Step 1: Create Google Cloud Project

Same as OAuth2 Step 1-2 above.

### Step 2: Create Service Account

1. Go to **APIs & Services** → **Credentials**
2. Click **+ Create Credentials** → **Service account**
3. Fill in:
   - **Service account name**: picoclaw-drive
   - **Description**: PicoClaw Drive access
4. Click **Create and Continue**
5. Skip role assignment (not needed for personal Drive) → **Continue**
6. Click **Done**

### Step 3: Create Service Account Key

1. Click on the newly created service account
2. Go to **Keys** tab
3. **Add Key** → **Create new key**
4. Choose **JSON** → **Create**
5. Save the downloaded JSON file securely

### Step 4: Share Drive Access

The service account has its own empty Drive. To access your files:

1. Open the service account JSON file
2. Find the `client_email` field (looks like: `picoclaw-drive@project-id.iam.gserviceaccount.com`)
3. Go to Google Drive
4. Share files/folders with this email address (just like sharing with another user)
5. Choose appropriate permission level (Viewer, Commenter, Editor)

> **Important**: The service account can ONLY access files explicitly shared with it. It cannot see your personal Drive files unless you share them.

### Step 5: Configure Environment

```bash
# Path to the service account JSON key file
export GOOGLE_DRIVE_CREDENTIALS_PATH="/path/to/service-account-key.json"

# No token path needed for service accounts
```

### Step 6: Verify Access

```bash
python3 scripts/gdrive_list.py --limit 5
```

You should see files/folders shared with the service account.

---

## Advanced: Domain-Wide Delegation (Service Account)

For G Suite/Google Workspace admins who want the service account to access all users' Drives:

### Step 1: Enable Domain-Wide Delegation

1. In the service account details, go to **Domain-wide Delegation** tab
2. Check **Enable G Suite Domain-wide Delegation**
3. Note the **Unique ID** (client_id)

### Step 2: Authorize in Admin Console

1. Go to [Google Admin Console](https://admin.google.com/)
2. **Security** → **Access and data control** → **API controls**
3. **Manage Domain Wide Delegation**
4. **Add new**
5. Enter:
   - **Client ID**: the unique ID from Step 1
   - **OAuth Scopes**: `https://www.googleapis.com/auth/drive`
6. **Authorize**

### Step 3: Use in Scripts

Set the user to impersonate:

```bash
export GOOGLE_DRIVE_IMPERSONATE_USER="user@yourdomain.com"
```

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GOOGLE_DRIVE_CREDENTIALS_PATH` | Yes | — | Path to OAuth2 credentials.json or service account JSON key |
| `GOOGLE_DRIVE_TOKEN_PATH` | No (OAuth2) | `token.json` in skill dir | Path to save/load OAuth2 token |
| `GOOGLE_DRIVE_SCOPES` | No | Full Drive access | Space-separated OAuth2 scopes |
| `GOOGLE_DRIVE_IMPERSONATE_USER` | No | — | Email to impersonate (domain-wide delegation) |

### Available Scopes

Use `GOOGLE_DRIVE_SCOPES` to limit permissions:

```bash
# Read-only access
export GOOGLE_DRIVE_SCOPES="https://www.googleapis.com/auth/drive.readonly"

# Full access (default)
export GOOGLE_DRIVE_SCOPES="https://www.googleapis.com/auth/drive"

# Specific app access
export GOOGLE_DRIVE_SCOPES="https://www.googleapis.com/auth/drive.file"

# Multiple scopes
export GOOGLE_DRIVE_SCOPES="https://www.googleapis.com/auth/drive https://www.googleapis.com/auth/drive.metadata.readonly"
```

---

## Troubleshooting

### OAuth2 Issues

**"invalid_client" error**
- Verify `credentials.json` is from a Desktop app OAuth client
- Ensure the OAuth consent screen is configured
- Check your Google account is added as a test user

**Token expired or invalid**
- Delete `token.json` and re-authorize
- Tokens should auto-refresh; if not, re-run authorization

**"access_denied" error**
- Ensure you're logged into the correct Google account
- Verify the app is in Testing mode and your account is a test user

### Service Account Issues

**"File not found" for files you own**
- Service accounts have separate Drives
- Share files/folders with the service account email
- Or use domain-wide delegation (G Suite only)

**"Service account key file not found"**
- Verify `GOOGLE_DRIVE_CREDENTIALS_PATH` points to the correct file
- Ensure the file is valid JSON

**"unauthorized_client" error**
- Enable Domain-Wide Delegation in service account settings
- Authorize the client ID in Google Admin Console
- Verify scopes match what was authorized

### General Issues

**"insufficientPermissions" error**
- Check `GOOGLE_DRIVE_SCOPES` includes required permissions
- For OAuth2: delete token.json and re-authorize with correct scopes
- For Service Account: verify Drive API is enabled

**Rate limiting (429 errors)**
- Scripts include automatic retry with exponential backoff
- Reduce request frequency for bulk operations
- Consider using `--json` output to batch process results

---

## Security Best Practices

1. **Never commit credentials** — Add credential files to `.gitignore`
2. **Use least-privilege scopes** — Request only the permissions you need
3. **Rotate service account keys** — Create new keys periodically and delete old ones
4. **Restrict OAuth2 test users** — Only add accounts that need access
5. **Monitor API usage** — Check [Google Cloud Console metrics](https://console.cloud.google.com/apis/dashboard) for unusual activity
6. **Use service accounts for automation** — They don't require user interaction and have better audit trails
