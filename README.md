crear .env
N8N_PORT=5678
N8N_HOST=localhost
N8N_PROTOCOL=http

N8N_BASIC_AUTH_ACTIVE=true
N8N_BASIC_AUTH_USER=loxi1
N8N_BASIC_AUTH_PASSWORD=654123

GENERIC_TIMEZONE=America/Lima
TZ=America/Lima

DB_TYPE=postgresdb
DB_POSTGRESDB_HOST=host.docker.internal
DB_POSTGRESDB_PORT=5432
DB_POSTGRESDB_DATABASE=n8n
DB_POSTGRESDB_USER=postgres
DB_POSTGRESDB_PASSWORD=postgres123
DB_POSTGRESDB_SCHEMA=public


N8N_ENCRYPTION_KEY=wwwwww-zzz-bbb-xx-xxxf
N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS=true
N8N_RUNNERS_ENABLED=true
N8N_RESTRICT_FILE_ACCESS_TO=/files
N8N_BLOCK_FILE_ACCESS_TO_N8N_FILES=false

para leventar en windows
cd app
python -m venv venv
source venv/Scripts/activate
pip install -r requirements.txt

para levanar en ubuntu
