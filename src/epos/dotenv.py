"""Caricamento del file .env dalla radice del progetto.

Stesso comportamento del vecchio gioco: parsing manuale, nessuna dipendenza
esterna. Le variabili già presenti nell'ambiente hanno precedenza sul file.
"""

from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path: str | Path) -> None:
    """Carica le variabili da `path` (se esiste) in os.environ.

    Righe vuote e commenti (#) ignorati; valori fra virgolette normalizzati;
    una variabile già definita nell'ambiente NON viene sovrascritta.
    """

    path = Path(path)
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        if name and name not in os.environ:
            os.environ[name] = value
