# services/status_service.py
import asyncio
from datetime import datetime
from logger import logger

# Globale Statusvariablen
_start_time = datetime.now()
_active_users = 0

async def get_status():
    """
    Gibt den aktuellen Bot-Status zurück
    Returns:
        dict: Dictionary mit Statusinformationen
            {'active_users': int, 'uptime': str}
    """
    global _active_users, _start_time
    
    uptime = datetime.now() - _start_time
    uptime_str = str(uptime).split('.')[0]  # Entfernt Mikrosekunden
    
    return {
        'active_users': _active_users,
        'uptime': uptime_str
    }

async def status_update():
    """Sendet regelmäßige Status-Updates"""
    global _active_users, _start_time
    
    while True:
        try:
            # Status aktualisieren
            status = await get_status()
            
            logger.info(
                f"Status Update | "
                f"Aktive User: {status['active_users']} | "
                f"Uptime: {status['uptime']}"
            )
            
            # Alle 5 Minuten aktualisieren
            await asyncio.sleep(300)
            
        except asyncio.CancelledError:
            logger.info("Status-Update wurde abgebrochen")
            break
        except Exception as e:
            logger.error(f"Fehler im Status-Update: {e}")
            await asyncio.sleep(60)  # Bei Fehlern 1 Minute warten

# Testfunktion für lokales Debugging
async def _test_status_service():
    print("Teste Status-Service...")
    print(await get_status())
    await asyncio.sleep(1)
    print(await get_status())

if __name__ == "__main__":
    asyncio.run(_test_status_service())