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
        f.write(
            f'CONTROL_PLANE_TOKEN={secrets.token_urlsafe(32)}\n'
            f'POSTGRES_PASSWORD={secrets.token_urlsafe(24)}\n'
            f'OWNER_PASSWORD={secrets.token_urlsafe(18)}\n'
            f'SECRET_KEY={secrets.token_urlsafe(48)}\n'
            'GEMINI_API_KEY=\n'
            'GEMINI_MODEL=gemini-2.5-flash\n'
            'ENABLE_GEMINI=false\n'
        )
    print('Created private .env (owner password and API token are inside)')
