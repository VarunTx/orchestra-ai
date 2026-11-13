"""Reports get screenshotted, so evidence is scrubbed of anything shaped like a credential."""
import re

MASK='[redacted]'
RULES=[
    (re.compile(r'(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{8,}'),r'\1'+MASK),
    (re.compile(r'(?i)\b([A-Z0-9_]*(?:TOKEN|SECRET|KEY|PASSWORD|PASSWD|PWD)[A-Z0-9_]*\s*[=:]\s*)("[^"]*"|\'[^\']*\'|\S+)'),r'\1'+MASK),
    (re.compile(r'://[^/\s:@]+:[^@\s]+@'),'://'+MASK+'@'),
    (re.compile(r'\b(?:sk|pk|rk)-[A-Za-z0-9_-]{16,}'),MASK),
    (re.compile(r'\bgh[pousr]_[A-Za-z0-9]{20,}'),MASK),
    (re.compile(r'\bxox[abpr]-[A-Za-z0-9-]{10,}'),MASK),
    (re.compile(r'\bAKIA[0-9A-Z]{16}\b'),MASK),
    (re.compile(r'\b[A-Fa-f0-9]{32,}\b'),MASK),
    (re.compile(r'[A-Za-z0-9+_-]{40,}={0,2}'),MASK),
]


def redact(text):
    if not text: return text
    for pattern,replacement in RULES: text=pattern.sub(replacement,text)
    return text
