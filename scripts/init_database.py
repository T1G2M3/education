# scripts/init_database.py
import sqlite3
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
import sys
import yaml
import time

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/init_database.log', encoding='utf-8', mode='a') if os.path.exists('logs') else logging.StreamHandler(),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('init_database')

def init_database():
    """Inicializuje databázi s kompletním schématem"""
    logger.info("Inicializace databáze...")
    
    try:
        # Vytvořit adresáře, pokud neexistují
        for directory in ['data', 'logs']:
            if not os.path.exists(directory):
                os.makedirs(directory)
        
        # Kontrola, zda databáze již existuje
        db_exists = os.path.exists('data/trading_history.db')
        
        # Připojení k databázi s timeoutem
        conn = sqlite3.connect('data/trading_history.db', timeout=60)
        cursor = conn.cursor()

        # Tabulka pro obchody
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            amount REAL NOT NULL,
            entry_price REAL NOT NULL,
            exit_price REAL,
            profit REAL,
            status TEXT NOT NULL,
            market_type TEXT NOT NULL DEFAULT 'spot'
        )''')

        # Tabulka equity
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS equity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME NOT NULL,
            equity_value REAL NOT NULL,
            market_type TEXT NOT NULL DEFAULT 'spot'
        )''')

        # Tabulka pro rozhodnutí
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME NOT NULL,
            symbol TEXT NOT NULL,
            signal TEXT NOT NULL,
            confidence REAL NOT NULL,
            action_taken TEXT NOT NULL,
            market_type TEXT NOT NULL DEFAULT 'spot'
        )''')
        
        # Tabulka pro aktivní pozice
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS active_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            direction TEXT NOT NULL,
            amount REAL NOT NULL,
            entry_price REAL NOT NULL,
            stop_loss REAL,
            take_profit REAL,
            timestamp DATETIME NOT NULL,
            market_type TEXT NOT NULL DEFAULT 'spot'
        )''')
        
        # Tabulka pro konfiguraci bota
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bot_config (
                id INTEGER PRIMARY KEY,
                key TEXT UNIQUE NOT NULL,
                value TEXT NOT NULL
            )
        """)
        
        cursor.execute("""
            INSERT OR IGNORE INTO bot_config (id, key, value) VALUES 
            (1, 'is_running', 'false')
        """)
        conn.commit()

        logger.info("Základní schéma databáze vytvořeno")

        # Kontrola a aktualizace schématu
        update_database_schema(conn)
        
        # Import testovacích dat pouze pokud databáze neexistovala
        if not db_exists:
            import_exchange_data(conn)
            
        conn.close()
        logger.info("Databáze úspěšně inicializována")

    except Exception as e:
        logger.error(f"Chyba při inicializaci databáze: {str(e)}")
        logger.error("Podrobnosti: ", exc_info=True)
        # Neskončit celou aplikaci při chybě

def get_trade_history(limit=10):
    """Získá historii obchodů z databáze"""
    max_attempts = 3
    attempt = 0
    
    while attempt < max_attempts:
        try:
            conn = sqlite3.connect('data/trading_history.db', timeout=60)
            df = pd.read_sql(f"SELECT * FROM trades ORDER BY timestamp DESC LIMIT {limit}", conn)
            conn.close()
            return df.to_dict('records') if not df.empty else []
        except sqlite3.OperationalError as e:
            attempt += 1
            logger.warning(f"Databázový lock (pokus {attempt}/{max_attempts}): {str(e)}")
            if attempt < max_attempts:
                time.sleep(1)  # Počkat před dalším pokusem
            else:
                logger.error(f"Dosažen maximální počet pokusů: {str(e)}")
                return []
        except Exception as e:
            logger.error(f"Chyba při získávání historie obchodů: {str(e)}")
            return []

def update_database_schema(conn=None):
    """Aktualizuje schéma databáze pro novější verze"""
    logger.info("Kontrola aktualizací schématu...")
    
    try:
        should_close = False
        if conn is None:
            conn = sqlite3.connect('data/trading_history.db', timeout=60)
            should_close = True
        
        cursor = conn.cursor()

        # 1. Kontrola sloupce market_type v tabulce equity
        cursor.execute("PRAGMA table_info(equity)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'market_type' not in columns:
            logger.info("Přidávám sloupec market_type do tabulky equity")
            cursor.execute('''
            ALTER TABLE equity 
            ADD COLUMN market_type TEXT NOT NULL DEFAULT 'spot'
            ''')

        # 2. Kontrola sloupce status v tabulce trades
        cursor.execute("PRAGMA table_info(trades)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'status' not in columns:
            logger.info("Přidávám sloupec status do tabulky trades")
            cursor.execute('''
            ALTER TABLE trades 
            ADD COLUMN status TEXT NOT NULL DEFAULT 'CLOSED'
            ''')
            
        # 3. Kontrola existence tabulky bot_config
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bot_config'")
        if not cursor.fetchone():
            logger.info("Vytvářím tabulku bot_config")
            cursor.execute('''
            CREATE TABLE bot_config (
                id INTEGER PRIMARY KEY,
                key TEXT UNIQUE NOT NULL,
                value TEXT NOT NULL
            )''')
            # Vložení výchozích hodnot
            cursor.execute("INSERT INTO bot_config (id, key, value) VALUES (1, 'is_running', 'false')")

        conn.commit()
        logger.info("Schéma databáze je aktuální")

        if should_close:
            conn.close()

    except Exception as e:
        logger.error(f"Chyba při aktualizaci schématu: {str(e)}")
        logger.error("Podrobnosti: ", exc_info=True)

def import_exchange_data(conn=None):
    """Generuje testovací data pro všechny trhy"""
    logger.info("Import historických dat...")
    
    should_close = False
    if conn is None:
        conn = sqlite3.connect('data/trading_history.db', timeout=60)
        should_close = True
    
    try:
        config = load_config()
        cursor = conn.cursor()

        # Kontrola, zda již existují data
        cursor.execute("SELECT COUNT(*) FROM equity")
        if cursor.fetchone()[0] > 0:
            logger.info("Data již existují, import přeskočen")
            if should_close:
                conn.close()
            return

        # Vygenerování equity dat
        now = datetime.now()
        initial_value = config.get('virtual_balance', 10000.0)
        market_types = ['spot', 'futures']

        for market in market_types:
            current_value = initial_value
            for i in range(30):
                date = now - timedelta(days=29 - i)
                change = np.random.normal(0.002, 0.01)
                current_value *= (1 + change)
                try:
                    cursor.execute(
                        "INSERT INTO equity (timestamp, equity_value, market_type) VALUES (?, ?, ?)",
                        (date, current_value, market)
                    )
                except sqlite3.Error as e:
                    logger.warning(f"Chyba při vkládání equity záznamu: {str(e)}")

        # Vygenerování obchodů
        symbols = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT']
        for market in market_types:
            for i in range(20):
                trade_date = now - timedelta(days=np.random.randint(1, 30))
                symbol = np.random.choice(symbols)
                side = np.random.choice(['BUY', 'SELL'])
                amount = round(np.random.uniform(0.1, 2.0), 4)
                entry_price = round(np.random.uniform(100, 500), 2)
                profit = calculate_profit(side, amount, entry_price)
                try:
                    cursor.execute(
                        """INSERT INTO trades
                        (timestamp, symbol, side, amount, entry_price, profit, status, market_type)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (trade_date, symbol, side, amount, entry_price, profit, 'CLOSED', market)
                    )
                except sqlite3.Error as e:
                    logger.warning(f"Chyba při vkládání záznamu obchodu: {str(e)}")

        # Vložení výchozího stavu bota
        try:
            cursor.execute("INSERT OR REPLACE INTO bot_config (id, key, value) VALUES (1, 'is_running', 'false')")
            cursor.execute("INSERT OR REPLACE INTO bot_config (id, key, value) VALUES (2, 'stop_loss', ?)", 
                         (config['risk_management'].get('stop_loss', '2%'),))
            cursor.execute("INSERT OR REPLACE INTO bot_config (id, key, value) VALUES (3, 'take_profit', ?)", 
                         (config['risk_management'].get('take_profit', '5%'),))
            cursor.execute("INSERT OR REPLACE INTO bot_config (id, key, value) VALUES (4, 'max_trade_size', ?)", 
                         (str(config['risk_management'].get('max_trade_size', 100)),))
        except sqlite3.Error as e:
            logger.warning(f"Chyba při vkládání konfigurace bota: {str(e)}")

        conn.commit()
        logger.info("Testovací data úspěšně importována")

    except Exception as e:
        logger.error(f"Chyba při importu dat: {str(e)}")
        logger.error("Podrobnosti: ", exc_info=True)
    finally:
        if should_close and conn:
            conn.close()

def calculate_profit(side, amount, entry_price):
    """Vypočítá náhodný profit pro testovací data"""
    profit_chance = np.random.random()
    if profit_chance > 0.3:
        return round(amount * entry_price * np.random.uniform(0.01, 0.05), 2)
    return round(-amount * entry_price * np.random.uniform(0.01, 0.03), 2)

def load_config():
    """Načte konfiguraci ze souboru"""
    default_config = {
        'virtual_balance': 10000.0,
        'base_currency': 'BTC',
        'risk_management': {
            'stop_loss': '2%',
            'take_profit': '5%',
            'max_trade_size': 100
        },
        'strategies': {
            'active': 'ml_strategy'
        }
    }
    
    try:
        if os.path.exists("config/config.yaml"):
            with open("config/config.yaml", encoding='utf-8') as f:
                loaded_config = yaml.safe_load(f)
                return loaded_config or default_config
        else:
            # Vytvoření výchozí konfigurace
            if not os.path.exists("config"):
                os.makedirs("config")
            with open("config/config.yaml", 'w', encoding='utf-8') as f:
                yaml.dump(default_config, f, sort_keys=False)
            logger.info("Vytvořena výchozí konfigurace")
            return default_config
    except Exception as e:
        logger.error(f"Chyba při načítání konfigurace: {str(e)}")
        logger.error("Podrobnosti: ", exc_info=True)
        return default_config

if __name__ == "__main__":
    init_database()
    logger.info("Inicializace dokončena. Databáze je připravena k použití.")
