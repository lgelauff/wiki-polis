# Wiki-Polis v1

The current live deployment. A lightweight Flask app that wraps a hosted pol.is conversation behind Wikimedia OAuth.

---

## Local development

### Prerequisites

- [UV](https://docs.astral.sh/uv/) for Python dependency management
- Python 3.11 or later

### Setup

```bash
git clone https://github.com/lgelauff/wiki-polis
cd wiki-polis
uv sync
```

Create a `.env` file (never commit this):

```bash
cp .env.example .env
```

Edit `.env` with your values:

```
OAUTH_CLIENT_ID=your_client_id
OAUTH_CLIENT_SECRET=your_client_secret
OAUTH_REDIRECT_URI=http://127.0.0.1:5000/oauth-callback
SECRET_KEY=any-random-string-for-local-dev
ADMIN_USERS=YourWikimediaUsername
```

> **Note:** The OAuth consumer is registered for the Toolforge callback URL, so the full OAuth flow won't work locally. Use the dev-login bypass instead.

### Running the app

```bash
FLASK_DEBUG=1 uv run python app.py
```

Visit `http://127.0.0.1:5000` (not `localhost` — use `127.0.0.1`).

### Dev login (bypass OAuth)

With `FLASK_DEBUG=1`:

```
http://127.0.0.1:5000/dev-login?username=YourWikimediaName
```

### Database

Local SQLite at `instance/dev.db` — created automatically on first run.

---

## Deployment (Toolforge)

### 1. Register the tool

Register at https://toolsadmin.wikimedia.org with tool name `wiki-polis`.

### 2. Register OAuth consumer

Register at https://meta.wikimedia.org/wiki/Special:OAuthConsumerRegistration with:
- Callback URL: `https://wiki-polis.toolforge.org/oauth-callback`
- Grants: identify only

### 3. SSH into Toolforge and install uv

```bash
ssh login.toolforge.org
become wiki-polis
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
```

### 4. Clone the repository

```bash
git clone https://github.com/lgelauff/wiki-polis ~/wiki-polis
```

### 5. Create the database

```bash
cat ~/replica.my.cnf
mariadb --defaults-file=$HOME/replica.my.cnf -h tools.db.svc.wikimedia.cloud
```

```sql
CREATE DATABASE `s57499__wiki-polis`
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
EXIT;
```

> Database name must start with your tools prefix (check `~/replica.my.cnf`).

### 6. Set secrets

```bash
toolforge envvars create OAUTH_CLIENT_ID "YOUR_CLIENT_ID"
toolforge envvars create OAUTH_CLIENT_SECRET "YOUR_CLIENT_SECRET"
toolforge envvars create OAUTH_REDIRECT_URI "https://wiki-polis.toolforge.org/oauth-callback"
toolforge envvars create SECRET_KEY "YOUR_RANDOM_SECRET_KEY"
toolforge envvars create ADMIN_USERS "Username1,Username2"
toolforge envvars create DATABASE_URL "mysql+pymysql://USER:PASSWORD@tools.db.svc.wikimedia.cloud/s57499__wiki-polis"  # pragma: allowlist secret
```

### 7. Set up the web service directory

```bash
mkdir -p ~/www/python
ln -s ~/wiki-polis ~/www/python/src
toolforge webservice python3.13 shell
```

Inside the shell:

```bash
python3 -m venv ~/www/python/venv
~/www/python/venv/bin/pip install -e ~/wiki-polis
exit
```

### 8. Start the web service

```bash
cd ~
toolforge webservice --backend=kubernetes python3.13 start
```

### Updating

```bash
bash ~/wiki-polis/deploy.sh
```
