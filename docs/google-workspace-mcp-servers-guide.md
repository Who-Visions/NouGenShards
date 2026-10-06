# Google Workspace Remote MCP Server Configuration & Antigravity Guide

## 1. Overview
Google Workspace provides official remote Model Context Protocol (MCP) servers allowing AI agents (such as Google Antigravity and Claude) to interact securely with Gmail, Drive, Docs, Sheets, Slides, Calendar, Chat, and People.

Reference: `https://developers.google.com/workspace/guides/configure-mcp-servers`

---

## 2. API & Service Enablement

In your Google Cloud project (`PROJECT_ID`):
```bash
# Enable Core Workspace APIs
gcloud services enable \
  gmail.googleapis.com \
  drive.googleapis.com \
  docs.googleapis.com \
  sheets.googleapis.com \
  slides.googleapis.com \
  calendar-json.googleapis.com \
  chat.googleapis.com \
  people.googleapis.com \
  --project=PROJECT_ID

# Enable Workspace MCP APIs
gcloud services enable \
  gmailmcp.googleapis.com \
  drivemcp.googleapis.com \
  docsmcp.googleapis.com \
  sheetsmcp.googleapis.com \
  slidesmcp.googleapis.com \
  calendarmcp.googleapis.com \
  chatmcp.googleapis.com \
  people.googleapis.com \
  --project=PROJECT_ID
```

---

## 3. OAuth 2.0 Credentials & Scopes

### OAuth Client Setup
1. In Google Cloud Console: **Google Auth Platform** > **Clients** > **Create Client**.
2. Application Type: **Web application**.
3. Authorized Redirect URIs:
   - For Antigravity: `https://antigravity.google/oauth-callback`
   - For generic custom apps: match client callback URL.
4. Obtain `OAUTH_CLIENT_ID` and `OAUTH_CLIENT_SECRET`.

### Scopes Required
- Gmail: `https://www.googleapis.com/auth/gmail.readonly`, `https://www.googleapis.com/auth/gmail.compose`
- Drive: `https://www.googleapis.com/auth/drive.readonly`, `https://www.googleapis.com/auth/drive.file`
- Docs: `https://www.googleapis.com/auth/documents.readonly`, `https://www.googleapis.com/auth/documents`
- Sheets: `https://www.googleapis.com/auth/spreadsheets.readonly`, `https://www.googleapis.com/auth/spreadsheets`
- Slides: `https://www.googleapis.com/auth/presentations.readonly`, `https://www.googleapis.com/auth/presentations`
- Calendar: `https://www.googleapis.com/auth/calendar.readonly`, `https://www.googleapis.com/auth/calendar.events`
- Chat: `https://www.googleapis.com/auth/chat.spaces.readonly`, `https://www.googleapis.com/auth/chat.messages`
- People: `https://www.googleapis.com/auth/contacts.readonly`, `https://www.googleapis.com/auth/userinfo.profile`

---

## 4. Antigravity Configuration (`mcp_config.json`)

File location: `~/.gemini/config/mcp_config.json` (also mirrored at `C:\Users\super\.gemini\antigravity-ide\mcp_config.json`):

```json
{
  "mcpServers": {
    "gmail": {
      "serverUrl": "https://gmailmcp.googleapis.com/mcp/v1",
      "oauth": {
        "clientId": "OAUTH_CLIENT_ID",
        "clientSecret": "OAUTH_CLIENT_SECRET"
      }
    },
    "drive": {
      "serverUrl": "https://drivemcp.googleapis.com/mcp/v1",
      "oauth": {
        "clientId": "OAUTH_CLIENT_ID",
        "clientSecret": "OAUTH_CLIENT_SECRET"
      }
    },
    "docs": {
      "serverUrl": "https://docsmcp.googleapis.com/mcp/v1",
      "oauth": {
        "clientId": "OAUTH_CLIENT_ID",
        "clientSecret": "OAUTH_CLIENT_SECRET"
      }
    },
    "sheets": {
      "serverUrl": "https://sheetsmcp.googleapis.com/mcp/v1",
      "oauth": {
        "clientId": "OAUTH_CLIENT_ID",
        "clientSecret": "OAUTH_CLIENT_SECRET"
      }
    },
    "slides": {
      "serverUrl": "https://slidesmcp.googleapis.com/mcp/v1",
      "oauth": {
        "clientId": "OAUTH_CLIENT_ID",
        "clientSecret": "OAUTH_CLIENT_SECRET"
      }
    },
    "calendar": {
      "serverUrl": "https://calendarmcp.googleapis.com/mcp/v1",
      "oauth": {
        "clientId": "OAUTH_CLIENT_ID",
        "clientSecret": "OAUTH_CLIENT_SECRET"
      }
    },
    "chat": {
      "serverUrl": "https://chatmcp.googleapis.com/mcp/v1",
      "oauth": {
        "clientId": "OAUTH_CLIENT_ID",
        "clientSecret": "OAUTH_CLIENT_SECRET"
      }
    },
    "people": {
      "serverUrl": "https://people.googleapis.com/mcp/v1",
      "oauth": {
        "clientId": "OAUTH_CLIENT_ID",
        "clientSecret": "OAUTH_CLIENT_SECRET"
      }
    }
  }
}
```

---

## 5. Client Authentication
- **GUI (Antigravity 2.0 / IDE)**: Settings > Customizations > Installed MCP Servers > Click Authenticate for each service.
- **CLI (`agy`)**: Run `agy mcp authenticate <server-name>` to trigger interactive OAuth flow.
