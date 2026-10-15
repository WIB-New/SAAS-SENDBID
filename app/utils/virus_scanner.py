"""
StorageHub — Scanner de fichiers malveillants
Niveau 1 : signatures EICAR + magic bytes exécutables + patterns scripts embarqués.
Niveau 2 (optionnel) : VirusTotal API si VIRUSTOTAL_API_KEY est défini.
"""
import re
from typing import Optional

# Signature EICAR — test antivirus standard (ISO/IEC 29066:2011)
_EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"

# Magic bytes d'exécutables / binaires dangereux
_EXEC_MAGIC = [
    (b"\x4d\x5a",       "Windows PE executable (.exe/.dll)"),
    (b"\x7f\x45\x4c\x46", "ELF binary (Linux)"),
    (b"\xfe\xed\xfa\xce", "Mach-O 32-bit (macOS)"),
    (b"\xfe\xed\xfa\xcf", "Mach-O 64-bit (macOS)"),
    (b"\xca\xfe\xba\xbe", "Java class file"),
]

# Patterns d'injection de script (contrôle sur les 8 Ko pour les PDFs)
_SCRIPT_PATTERNS = [
    rb"<script[\s>]",
    rb"javascript\s*:",
    rb"/JS\s+<<",          # JS embarqué dans PDF
    rb"/JavaScript\s+<<",
]


def scan_content(content: bytes, filename: str = "") -> tuple[bool, Optional[str]]:
    """
    Analyse le contenu à la recherche de malware.
    Retourne (is_safe, raison_si_dangereux).
    """
    # 1. EICAR test virus
    if _EICAR in content:
        return False, "EICAR test virus signature detected"

    # 2. Exécutables / binaires
    for magic, label in _EXEC_MAGIC:
        if content[:len(magic)] == magic:
            return False, f"Dangerous file type blocked: {label}"

    # 3. Scripts embarqués dans les PDFs
    if b"%PDF" in content[:1024]:
        sample = content[:16384]
        for pat in _SCRIPT_PATTERNS:
            if re.search(pat, sample, re.IGNORECASE):
                return False, "Suspicious embedded JavaScript detected in PDF"

    return True, None


async def scan_with_virustotal(
    content: bytes, filename: str, api_key: str
) -> tuple[bool, Optional[str]]:
    """
    Scan optionnel via l'API VirusTotal (lookup par hash SHA-256).
    N'uploade pas le fichier — vérifie uniquement si le hash est connu.
    """
    import hashlib
    import httpx

    sha256 = hashlib.sha256(content).hexdigest()
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                f"https://www.virustotal.com/api/v3/files/{sha256}",
                headers={"x-apikey": api_key},
            )
        if resp.status_code == 200:
            stats = (
                resp.json()
                .get("data", {})
                .get("attributes", {})
                .get("last_analysis_stats", {})
            )
            malicious = stats.get("malicious", 0)
            suspicious = stats.get("suspicious", 0)
            if malicious > 0:
                return False, f"VirusTotal: {malicious} engine(s) flagged this file as malicious"
            if suspicious > 2:
                return False, f"VirusTotal: {suspicious} engine(s) flagged this file as suspicious"
    except Exception:
        pass   # VirusTotal indisponible → on laisse passer (dégradation douce)

    return True, None
