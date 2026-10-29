"""
Punto de entrada de interfaz para el Bot de Telegram de JEV.
Permite ejecutar directamente: `python -m interfaces.telegram_bot` o `python interfaces/telegram_bot.py`.
"""
import sys
from pathlib import Path

# Asegurar que el directorio raíz del proyecto esté en sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from jev.interfaces.telegram_bot import TelegramRemoteInterface, run_bot

if __name__ == "__main__":
    run_bot()
