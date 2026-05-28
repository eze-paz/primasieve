# Sandpie Deployment Guide

## Git Pull Deployment (Current)

### Workflow
1. Edit files locally in `projects/sandpie/`
2. Run: `python scripts/deploy_git_pull.py "commit message"`
3. Script pushes to GitHub via API
4. Script SSHs to gasn2cloud and runs `git pull origin main`
5. Server mirrors GitHub exactly

### Prerequisites
- `.ssh/github_token` - GitHub PAT
- `.ssh/gasn2cloud_ed25519` - SSH key

### Server Setup
```
/opt/bitnami/apache2/htdocs/public/sandpie/   <- git clone of Eze-DP/sandpie
/opt/bitnami/apache2/htdocs/public/sdk/        <- rewrite rules to /sandpie/
```

### File Structure
```
sandpie/
  sandpie.html              # Main app
  sandpie-test.html         # Test version
  sandpie.js                # Core JS
  modules/
    artifacts.js            # Sidebar extensions
    images.js
    notifications.js
    webllm.js
    wllama.js
  variants/
    sandpie-lightweight.html
    sandpie-webllm.html     # (moved from root)
    sandpie-wllama.html     # (moved from root)
```

### Old Method (Deprecated)
The previous `scripts/sandpie_deploy.py` used SCP/base64 chunk upload.
Replaced with git pull for reliability.
