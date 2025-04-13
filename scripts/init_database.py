# scripts/init_database.py
import sqlite3
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
import sys
import yaml

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('init_database')

def init_database():
    """Inicializuje databázi s kompletním schématem"""
    logger.info("Inicializace databáze...")
    
    try:
        if not os.path.exists('data'):
            os.makedirs('data')
        
        # Kontrola, zda databáze již existuje
        db_exists = os.path.exists('data/trading_history.db')
        
        conn = sqlite3.connect('data/trading_history.db')
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

        conn.commit()
        logger.info("Základní schéma databáze vytvořeno")

        # Kontrola a aktualizace schématu
        update_database_schema(conn)
        
        if not db_exists:
            import_exchange_data()
            
        conn.close()
        logger.info("Databáze úspěšně inicializována")

    except Exception as e:
        logger.error(f"Chyba při inicializaci databáze: {str(e)}")
        sys.exit(1)

def get_trade_history(limit=10):
    try:
        conn = sqlite3.connect('data/trading_history.db', timeout=30)
        df = pd.read_sql(f"SELECT * FROM trades ORDER BY timestamp DESC LIMIT {limit}", conn)
        conn.close()
        return df.to_dict('records') if not df.empty else []
    except sqlite3.OperationalError as e:
        logger.error(f"Databázový lock: {str(e)}")
        return []
    except Exception as e:
        logger.error(f"Chyba: {str(e)}")
        return []

def update_database_schema(conn=None):
    """Aktualizuje schéma databáze pro novější verze"""
    logger.info("Kontrola aktualizací schématu...")
    
    try:
        should_close = False
        if conn is None:
            conn = sqlite3.connect('data/trading_history.db')
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

        conn.commit()
        logger.info("Schéma databáze je aktuální")

        if should_close:
            conn.close()

    except Exception as e:
        logger.error(f"Chyba při aktualizaci schématu: {str(e)}")
        raise

def import_exchange_data():
    """Generuje testovací data pro všechny trhy"""
    logger.info("Import historických dat...")
    
    try:
        config = load_config()
        conn = sqlite3.connect('data/trading_history.db')
        cursor = conn.cursor()

        # Vygenerování equity dat
        now = datetime.now()
        initial_value = config.get('virtual_balance', 10000.0)
        market_types = ['spot', 'futures']

        for market in market_types:
            current_value = initial_value
            for i in range(30):
                date = now - timedelta(days=29-i)
                change = np.random.normal(0.002, 0.01)
                current_value *= (1 + change)
                
                cursor.execute(
                    "INSERT INTO equity (timestamp, equity_value, market_type) VALUES (?, ?, ?)",
                    (date, current_value, market)
                )

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
                
                cursor.execute(
                    """INSERT INTO trades 
                    (timestamp, symbol, side, amount, entry_price, profit, status, market_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (trade_date, symbol, side, amount, entry_price, profit, 'CLOSED', market)
                )

        conn.commit()
        conn.close()
        logger.info("Testovací data úspěšně importována")

    except Exception as e:
        logger.error(f"Chyba při importu dat: {str(e)}")
        sys.exit(1)

def calculate_profit(side, amount, entry_price):
    """Vypočítá náhodný profit pro testovací data"""
    profit_chance = np.random.random()
    if profit_chance > 0.3:
        return round(amount * entry_price * np.random.uniform(0.01, 0.05), 2)
    return round(-amount * entry_price * np.random.uniform(0.01, 0.03), 2)

def load_config():
    """Načte konfiguraci ze souboru"""
    try:
        with open("config/config.yaml", encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Chyba při načítání konfigurace: {str(e)}")
        return {}

if __name__ == "__main__":
    init_database()
    update_database_schema()
    import_exchange_data()
    logger.info("Inicializace dokončena. Databáze je připravena k použití.")
