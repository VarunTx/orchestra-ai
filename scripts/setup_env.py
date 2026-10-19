"""Create private local settings; never overwrite an existing file."""
import os
import secrets
from pathlib import Path
path = Path(__file__).resolve().parents[1] / '.env'
if path.exists():
    print('.env already exists; preserved')
else:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as f:
        f.write(f'CONTROL_PLANE_TOKEN={secrets.token_urlsafe(32)}\nPOSTGRES_PASSWORD={secrets.token_urlsafe(24)}\nGEMINI_API_KEY=\nGEMINI_MODEL=gemini-2.5-flash\nENABLE_GEMINI=false\n')
    print('Created private .env')
