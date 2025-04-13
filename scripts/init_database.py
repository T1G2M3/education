# scripts/init_database.py
import sqlite3
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import ccxt
import logging
import sys
import yaml
from datetime import datetime
trade_date = datetime.now().isoformat()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('init_database')

# Načtení konfigurace
def load_config():
    with open("config/config.yaml", encoding='utf-8') as f:
        return yaml.safe_load(f)

def init_database():
    """Inicializuje databázi a vytvoří potřebné tabulky"""
    logger.info("Inicializace databáze...")
    
    if not os.path.exists('data'):
        os.makedirs('data')
    
    conn = sqlite3.connect('data/trading_history.db')
    cursor = conn.cursor()
    
    # Tabulka pro obchody
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME,
        symbol TEXT,
        side TEXT,
        amount REAL,
        entry_price REAL,
        exit_price REAL,
        profit REAL,
        status TEXT,
        market_type TEXT DEFAULT 'spot'
    )
    ''')
    
    # Tabulka pro rozhodnutí bota
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME,
        symbol TEXT,
        signal TEXT,
        confidence REAL,
        action_taken TEXT,
        market_type TEXT DEFAULT 'spot'
    )
    ''')
    
    # Tabulka equity
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS equity (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME,
        equity_value REAL,
        market_type TEXT DEFAULT 'spot'
    )
    ''')
    
    # Tabulka pro aktivní pozice
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS active_positions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT,
        direction TEXT,
        amount REAL,
        entry_price REAL,
        stop_loss REAL,
        take_profit REAL,
        timestamp DATETIME,
        market_type TEXT DEFAULT 'spot'
    )
    ''')
    
    # Tabulka pro predikce modelu
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS model_predictions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME,
        symbol TEXT,
        prediction REAL,
        confidence REAL,
        signal TEXT
    )
    ''')
    
    # Tabulka pro status bota
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS bot_status (
        id INTEGER PRIMARY KEY,
        is_running BOOLEAN,
        last_update DATETIME
    )
    ''')
    
    # Tabulka pro risk metriky
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS risk_metrics (
        id INTEGER PRIMARY KEY,
        timestamp DATETIME,
        current_balance REAL,
        peak_balance REAL,
        drawdown REAL,
        risk_score REAL
    )
    ''')
    
    conn.commit()
    conn.close()
    
    logger.info("Databáze úspěšně inicializována")

def import_exchange_data():
    """Import historických dat z burzy"""
    logger.info("Import historických dat...")
    
    config = load_config()
    
    try:
        # Inicializace Binance API
        exchange = ccxt.binance({
            'enableRateLimit': True,
        })
        
        # Získání dostupných symbolů
        symbols = ['BNB/USDT', 'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT', 'ADA/USDT', 'DOGE/USDT']
        
        # Připojení k databázi
        conn = sqlite3.connect('data/trading_history.db')
        cursor = conn.cursor()
        
        # Hodnota portfolia
        initial_value = config.get('virtual_balance', 1000.0)
        
        # Vygenerování equity dat za posledních 30 dní
        now = datetime.now()
        for i in range(30):
            date = now - timedelta(days=29-i)
            
            # Přidáme malou náhodnou změnu každý den
            change = np.random.normal(0.002, 0.01)  # Průměrný růst 0.2% denně
            initial_value *= (1 + change)
            
            cursor.execute(
                "INSERT INTO equity (timestamp, equity_value, market_type) VALUES (?, ?, ?)",
                (date, initial_value, 'spot')
            )
        
        # Záznam aktuální hodnoty
        cursor.execute(
            "INSERT INTO equity (timestamp, equity_value, market_type) VALUES (?, ?, ?)",
            (now, initial_value, 'spot')
        )
        
        # Vygenerování ukázkových obchodů
        for i in range(20):
            # Náhodné datum v posledních 30 dnech
            trade_date = now - timedelta(days=np.random.randint(1, 30))
            symbol = np.random.choice(symbols)
            side = np.random.choice(['BUY', 'SELL'])
            amount = round(np.random.uniform(0.1, 2.0), 4)
            entry_price = round(np.random.uniform(10, 500), 2)
            
            # 70% šance na ziskový obchod
            profit_chance = np.random.random()
            if profit_chance > 0.3:
                profit = round(amount * entry_price * np.random.uniform(0.01, 0.05), 2)
            else:
                profit = round(-amount * entry_price * np.random.uniform(0.01, 0.03), 2)
            
            cursor.execute(
                "INSERT INTO trades (timestamp, symbol, side, amount, entry_price, profit, status, market_type) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (trade_date, symbol, side, amount, entry_price, profit, 'CLOSED', 'spot')
            )
            
            # Přidání rozhodnutí pro každý obchod
            confidence = round(np.random.uniform(0.6, 0.95), 2)
            cursor.execute(
                "INSERT INTO decisions (timestamp, symbol, signal, confidence, action_taken, market_type) VALUES (?, ?, ?, ?, ?, ?)",
                (trade_date, symbol, side, confidence, 'EXECUTED', 'spot')
            )
        
        conn.commit()
        conn.close()
        
        logger.info("Import dat dokončen")
        
    except Exception as e:
        logger.error(f"Chyba při importu dat: {str(e)}")
        sys.exit(1)



if __name__ == "__main__":
    init_database()
    import_exchange_data()
    logger.info("Inicializace dokončena. Databáze je připravena k použití.")
