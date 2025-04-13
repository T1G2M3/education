# core/exchange.py
import time
import ccxt
import logging
import sqlite3
import pandas as pd
from datetime import datetime
from decouple import config as env_config

logger = logging.getLogger(__name__)
logger = logging.getLogger('dashboard')

# Konfigurace loggeru
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/dashboard.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)


class BinanceConnector:
    def __init__(self, yaml_config):
        self.yaml_config = yaml_config
        self.mode = yaml_config.get('mode', 'dry')
        self.base_currency = yaml_config.get('base_currency', 'BNB')
        self.market_type = yaml_config.get('market_type', 'spot')
        
        try:
            self.client = ccxt.binance({
                'apiKey': env_config('BINANCE_API_KEY', default=''),
                'secret': env_config('BINANCE_API_SECRET', default=''),
                'enableRateLimit': True,
                'options': {'defaultType': self.market_type},
                'timeout': 30000
            })
            
            if self.mode == 'dry':
                self.client.set_sandbox_mode(True)
                self.virtual_balance = 10000.0
                
            self._init_database()
            
        except Exception as e:
            logger.error(f"Chyba při inicializaci: {str(e)}")
            raise

    def _init_database(self):
        """Inicializuje databázové schéma s podporou market_type"""
        conn = sqlite3.connect('data/trading_history.db')
        cursor = conn.cursor()
        
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
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS equity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME NOT NULL,
            equity_value REAL NOT NULL,
            market_type TEXT NOT NULL DEFAULT 'spot'
        )''')
        
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
        
        conn.commit()
        conn.close()
    
    def get_market_pairs(self):
        """Získání dostupných obchodních párů"""
        try:
            return ['BNB/USDT', 'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT', 'ADA/USDT', 'DOGE/USDT']
        except Exception as e:
            self.logger.error(f"Chyba: {str(e)}")
            return []

    def get_real_time_data(self, symbol, timeframe='15m', limit=100, market_type=None):
        """Získá OHLCV data s retry mechanismem"""
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                # Původní kód volání API
                data = self.client.fetch_ohlcv(symbol, timeframe, limit=limit)
                return data
            except Exception as e:
                logger.warning(f"Pokus {attempt+1}/{max_retries} selhal: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                else:
                    logger.error(f"Všechny pokusy selhaly: {str(e)}")
                    return []


    def get_test_data(self, symbol, timeframe='15m', limit=100):
        """Vrátí testovací data pro vývoj"""
        now = int(datetime.now().timestamp() * 1000)
        base_price = 30000 if 'BTC' in symbol else 2000 if 'ETH' in symbol else 300
        
        return [
            [now - 3600000 * i, 
            base_price + i*10, 
            base_price + i*15, 
            base_price + i*5, 
            base_price + i*12, 
            1000 + i*100] 
            for i in range(limit)
        ]
    
    def get_portfolio_value(self, market_type=None):
        """Získá hodnotu portfolia pro daný trh"""
        original_type = self.client.options['defaultType']
        try:
            market_type = market_type or self.market_type
            
            if self.mode == 'dry':
                return self.virtual_balance
                
            self.client.options['defaultType'] = market_type
            
            balance = self.client.fetch_balance()
            total = balance['total'].get('USDT', 0)
            
            for currency, amount in balance['total'].items():
                if currency != 'USDT' and amount > 0:
                    try:
                        ticker = self.client.fetch_ticker(f"{currency}/USDT")
                        total += amount * ticker['last']
                    except Exception as e:
                        logger.warning(f"Chyba při hodnotění {currency}: {str(e)}")
                        continue
                        
            return total
            
        except Exception as e:
            logger.error(f"Chyba při získávání portfolia: {str(e)}")
            return 0
        finally:
            self.client.options['defaultType'] = original_type

    def get_24h_change(self, symbol=None, market_type=None):
        """Získá 24h procentuální změnu ceny"""
        original_type = self.client.options['defaultType']
        try:
            market_type = market_type or self.market_type
            self.client.options['defaultType'] = market_type
            
            symbol = symbol or f"{self.base_currency}/USDT"
            return self.client.fetch_ticker(symbol)['percentage']
            
        except Exception as e:
            logger.error(f"Chyba při získávání změny: {str(e)}")
            return 0
        finally:
            self.client.options['defaultType'] = original_type

    def get_active_positions(self, market_type=None):
        """Získá aktivní pozice pro daný trh"""
        try:
            conn = sqlite3.connect('data/trading_history.db')
            query = "SELECT * FROM active_positions"
            params = []
            
            if market_type:
                query += " WHERE market_type = ?"
                params.append(market_type)
                
            df = pd.read_sql(query, conn, params=params)
            conn.close()
            
            if not df.empty:
                return []
                
            for i, row in df.iterrows():
                current_price = self.get_current_price(row['symbol'], row['market_type'])
                df.at[i, 'current_price'] = current_price
                df.at[i, 'pnl'] = self._calculate_pnl(row, current_price)
                
            return df.to_dict('records')
            
        except Exception as e:
            logger.error(f"Chyba při získávání pozic: {str(e)}")
            return []

    def execute_trade(self, symbol, side, amount, order_type='market', price=None, market_type=None):
        """Provede obchod na daném trhu"""
        original_type = self.client.options['defaultType']
        try:
            market_type = market_type or self.market_type
            self.client.options['defaultType'] = market_type
            
            if self.mode == 'dry':
                return self._simulate_trade(symbol, side, amount, market_type)
                
            order = self.client.create_order(
                symbol=symbol,
                type=order_type,
                side=side,
                amount=amount,
                price=price
            )
            
            self._save_trade_to_db(symbol, side, amount, price, market_type)
            return order
            
        except Exception as e:
            logger.error(f"Chyba při provádění obchodu: {str(e)}")
            return None
        finally:
            self.client.options['defaultType'] = original_type

    def _simulate_trade(self, symbol, side, amount, market_type):
        """Simuluje obchod v testovacím režimu"""
        try:
            price = self.get_current_price(symbol, market_type)
            conn = sqlite3.connect('data/trading_history.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO trades 
                (timestamp, symbol, side, amount, entry_price, status, market_type)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                datetime.now(),
                symbol,
                side,
                amount,
                price,
                'SIMULATED',
                market_type
            ))
            
            conn.commit()
            conn.close()
            return {'status': 'simulated', 'price': price}
            
        except Exception as e:
            logger.error(f"Chyba simulace obchodu: {str(e)}")
            return None
    
    def get_current_price(self, symbol=None, market_type=None):
        """Získá aktuální cenu pro daný trh"""
        original_type = self.client.options['defaultType']
        try:
            market_type = market_type or self.market_type
            self.client.options['defaultType'] = market_type
            
            symbol = symbol or f"{self.base_currency}/USDT"
            return self.client.fetch_ticker(symbol)['last']
        except Exception as e:
            self.logger.error(f"Chyba při získávání ceny: {str(e)}")
            return 0
        finally:
            self.client.options['defaultType'] = original_type

    def get_trade_history(self, market_type=None, limit=100):
        """Získá historii obchodů pro daný trh"""
        try:
            conn = sqlite3.connect('data/trading_history.db')
            query = "SELECT * FROM trades"
            params = []
            
            if market_type:
                query += " WHERE market_type = ?"
                params.append(market_type)
                
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            df = pd.read_sql(query, conn, params=params)
            conn.close()
            return df.to_dict('records')
            
        except Exception as e:
            logger.error(f"Chyba při získávání historie: {str(e)}")
            return []

    def get_24h_volume(self, symbol=None, market_type=None):
        """Získá 24h objem obchodů"""
        original_type = self.client.options['defaultType']
        try:
            market_type = market_type or self.market_type
            self.client.options['defaultType'] = market_type
            
            symbol = symbol or f"{self.base_currency}/USDT"
            return self.client.fetch_ticker(symbol)['quoteVolume']
        except Exception as e:
            self.logger.error(f"Chyba při získávání objemu: {str(e)}")
            return 0
        finally:
            self.client.options['defaultType'] = original_type

    def _calculate_pnl(self, position, current_price):
        """Vypočítá aktuální zisk/ztrátu pro pozici"""
        if position['direction'] == 'LONG':
            return (current_price - position['entry_price']) * position['amount']
        return (position['entry_price'] - current_price) * position['amount']

    def close_position(self, position_id):
        """Kompletní implementace uzavření pozice"""
        try:
            conn = sqlite3.connect('data/trading_history.db')
            cursor = conn.cursor()
            
            # Získání dat o pozici
            cursor.execute("SELECT * FROM active_positions WHERE id = ?", (position_id,))
            position = cursor.fetchone()
            
            if not position:
                conn.close()
                return {'error': 'Pozice nenalezena'}
            
            # Rozparsování výsledku dotazu
            position_data = {
                'id': position[0],
                'symbol': position[1],
                'direction': position[2],
                'amount': position[3],
                'entry_price': position[4],
                'stop_loss': position[5],
                'take_profit': position[6],
                'timestamp': position[7],
                'market_type': position[8]
            }

            # Získání aktuální ceny
            current_price = self.get_current_price(
                position_data['symbol'], 
                position_data['market_type']
            )

            # Výpočet P/L
            if position_data['direction'] == 'LONG':
                profit = (current_price - position_data['entry_price']) * position_data['amount']
                close_side = 'SELL'
            else:
                profit = (position_data['entry_price'] - current_price) * position_data['amount']
                close_side = 'BUY'

            if self.mode == 'dry':
                # Simulace uzavření pozice
                self.virtual_balance += position_data['entry_price'] * position_data['amount'] + profit
                
                cursor.execute('''
                UPDATE trades 
                SET exit_price = ?, profit = ?, status = 'CLOSED'
                WHERE symbol = ? AND side = ? AND status = 'OPEN'
                ''', (current_price, profit, position_data['symbol'], 'BUY'))
                
            else:
                # Reálné uzavření pozice
                original_type = self.client.options['defaultType']
                self.client.options['defaultType'] = position_data['market_type']
                
                order = self.client.create_order(
                    symbol=position_data['symbol'],
                    type='market',
                    side=close_side.lower(),
                    amount=position_data['amount']
                )
                
                self.client.options['defaultType'] = original_type
                
                # Aktualizace obchodu v databázi
                cursor.execute('''
                UPDATE trades 
                SET exit_price = ?, profit = ?, status = 'CLOSED'
                WHERE symbol = ? AND side = ? AND status = 'OPEN'
                ''', (current_price, profit, position_data['symbol'], 'BUY'))

            # Odstranění z aktivních pozic
            cursor.execute("DELETE FROM active_positions WHERE id = ?", (position_id,))
            
            # Záznam o uzavření do historie
            cursor.execute('''
            INSERT INTO trades 
            (timestamp, symbol, side, amount, entry_price, exit_price, profit, status, market_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                datetime.now(),
                position_data['symbol'],
                close_side,
                position_data['amount'],
                position_data['entry_price'],
                current_price,
                profit,
                'CLOSED',
                position_data['market_type']
            ))
            
            conn.commit()
            conn.close()
            
            return {
                'status': 'success',
                'profit': profit,
                'closed_price': current_price,
                'position_id': position_id
            }
            
        except Exception as e:
            self.logger.error(f"Chyba při uzavírání pozice {position_id}: {str(e)}")
            return {'error': str(e)}

    def update_bot_status(self, is_running):
        """Aktualizuje stav bota v databázi"""
        try:
            conn = sqlite3.connect('data/trading_history.db')
            cursor = conn.cursor()
            
            cursor.execute('''
            INSERT OR REPLACE INTO bot_config (id, key, value)
            VALUES (1, 'is_running', ?)
            ''', ('true' if is_running else 'false',))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"Chyba při aktualizaci stavu bota: {str(e)}")

    def get_bot_status(self):
        """Získá aktuální stav bota z databáze"""
        try:
            conn = sqlite3.connect('data/trading_history.db')
            cursor = conn.cursor()
            
            cursor.execute("SELECT value FROM bot_config WHERE key = 'is_running'")
            result = cursor.fetchone()
            conn.close()
            
            return result[0] == 'true' if result else False
            
        except Exception as e:
            self.logger.error(f"Chyba při získávání stavu bota: {str(e)}")
            return False

    def update_risk_parameters(self, stop_loss, take_profit, max_trade_size):
        """Aktualizuje parametry rizikového managementu"""
        try:
            self.yaml_config['risk_management']['stop_loss'] = stop_loss
            self.yaml_config['risk_management']['take_profit'] = take_profit
            self.yaml_config['risk_management']['max_trade_size'] = max_trade_size
            
            # Uložení do databáze
            conn = sqlite3.connect('data/trading_history.db')
            cursor = conn.cursor()
            
            cursor.execute('''
            INSERT OR REPLACE INTO bot_config (id, key, value)
            VALUES 
                (2, 'stop_loss', ?),
                (3, 'take_profit', ?),
                (4, 'max_trade_size', ?)
            ''', (stop_loss, take_profit, max_trade_size))
            
            conn.commit()
            conn.close()
            
            return True
        except Exception as e:
            self.logger.error(f"Chyba při aktualizaci parametrů: {str(e)}")
            return False

    def get_risk_parameters(self):
        """Získá aktuální parametry rizikového managementu"""
        try:
            conn = sqlite3.connect('data/trading_history.db')
            cursor = conn.cursor()
            
            cursor.execute("SELECT key, value FROM bot_config WHERE key IN ('stop_loss', 'take_profit', 'max_trade_size')")
            results = cursor.fetchall()
            conn.close()
            
            params = {row[0]: row[1] for row in results}
            return {
                'stop_loss': params.get('stop_loss', '2%'),
                'take_profit': params.get('take_profit', '5%'),
                'max_trade_size': params.get('max_trade_size', '100')
            }
            
        except Exception as e:
            self.logger.error(f"Chyba při získávání parametrů: {str(e)}")
            return self.yaml_config['risk_management']
        


# Zbývající pomocné metody a konfigurace
if __name__ == '__main__':
    # Testovací inicializace
    config = {
        'mode': 'dry',
        'base_currency': 'BTC',
        'risk_management': {
            'stop_loss': '2%',
            'take_profit': '5%',
            'max_trade_size': 100
        }
    }
    
    exchange = BinanceConnector(config)
    print("Inicializace úspěšná!")
