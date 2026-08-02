"""epos — motore per RPG narrativi single player con LLM Game Master.

Il package root non esegue bootstrap, non muta stato globale e non importa
componenti GUI. I singoli entry point devono inizializzare esplicitamente il
runtime richiesto, per esempio tramite ``epos.resort_bootstrap``.
"""

__version__ = "0.1.0"
