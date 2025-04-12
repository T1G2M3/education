# core/exchange.py
import ccxt
import logging
import sqlite3
import pandas as pd
from datetime import datetime
from decouple import config as env_config

class BinanceConnector:
    def __init__(self, yaml_config):
        self.yaml_config = yaml_config
        self.mode = yaml_config.get('mode', 'dry')
        self.base_currency = yaml_config.get('base_currency', 'BNB')
        self.market_type = yaml_config.get('market_type', 'spot')  # Přidáno
        self.logger = logging.getLogger(__name__)
        
        try:
            self.client = ccxt.binance({
                'apiKey': env_config('BINANCE_API_KEY', default=''),
                'secret': env_config('BINANCE_API_SECRET', default=''),
                'enableRateLimit': True,
                'options': {'defaultType': self.market_type},  # Upraveno
                'timeout': 30000
            })
            
            if self.mode == 'dry':
                self.client.set_sandbox_mode(True)
                self.virtual_balance = 10000.0
                
            self._init_database()
            
        except Exception as e:
            self.logger.error(f"Inicializační chyba: {str(e)}")
            raise

    def _init_database(self):
        """Kompletní inicializace databáze"""
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
        
        # Tabulka pro rozhodnutí
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
        
        # Tabulka pro predikce
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
        """Získání OHLCV dat"""
        try:
            market_type = market_type or self.market_type
            self.client.options['defaultType'] = market_type
            
            return self.client.fetch_ohlcv(symbol, timeframe, limit=limit)
        except Exception as e:
            self.logger.error(f"Chyba: {str(e)}")
            return []


    def execute_trade(self, decision, amount, asset_pair=None, order_type='market', sl=None, tp=None, market_type=None):
        """Provede obchod na zadaném trhu"""
        market_type = market_type or self.market_type
        self.client.options['defaultType'] = market_type
        
        symbol = asset_pair or f"{self.base_currency}/USDT"
        current_price = self.get_current_price(symbol, market_type)
        
        if self.mode == 'dry':
            return self._simulate_trade(decision, amount, symbol, current_price, market_type)
        
        try:
            order = self.client.create_order(
                symbol=symbol,
                type=order_type,
                side=decision.lower(),
                amount=amount,
                price=current_price if order_type == 'limit' else None,
                params=self._get_order_params(sl, tp)
            )
            self._save_trade_to_db(decision, amount, symbol, current_price, market_type)
            return order
            
        except Exception as e:
            self.logger.error(f"Chyba při provádění obchodu: {str(e)}")
            return {'error': str(e)}

    def _get_order_params(self, sl, tp):
        """Připraví parametry pro objednávku se SL/TP"""
        params = {}
        if sl and tp:
            params.update({
                'stopLossPrice': sl,
                'takeProfitPrice': tp
            })
        return params

    def _simulate_trade(self, decision, amount, symbol, price, market_type):
        """Simuluje obchod v dry režimu"""
        conn = sqlite3.connect('data/trading_history.db')
        cursor = conn.cursor()
        
        # Záznam do historie obchodů
        cursor.execute('''
        INSERT INTO trades 
        (timestamp, symbol, side, amount, entry_price, market_type, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            datetime.now(), 
            symbol, 
            decision, 
            amount, 
            price, 
            market_type,
            'OPEN' if decision == 'BUY' else 'CLOSED'
        ))
        
        if decision == 'BUY':
            # Přidání do aktivních pozic
            cursor.execute('''
            INSERT INTO active_positions 
            (symbol, direction, amount, entry_price, stop_loss, take_profit, timestamp, market_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                symbol,
                'LONG',
                amount,
                price,
                price * (1 - float(self.yaml_config['risk_management']['stop_loss']) / 100),
                price * (1 + float(self.yaml_config['risk_management']['take_profit']) / 100),
                datetime.now(),
                market_type
            ))
        
        conn.commit()
        conn.close()
        return {'status': 'simulated', 'price': price}

    def get_current_price(self, symbol=None, market_type=None):
        """Získá aktuální cenu pro daný trh"""
        try:
            market_type = market_type or self.market_type
            self.client.options['defaultType'] = market_type
            
            symbol = symbol or f"{self.base_currency}/USDT"
            return self.client.fetch_ticker(symbol)['last']
        except Exception as e:
            self.logger.error(f"Chyba při získávání ceny: {str(e)}")
            return 0

    def get_portfolio_value(self, market_type=None):
        """Získá hodnotu portfolia pro daný trh"""
        try:
            if self.mode == 'dry':
                return self.virtual_balance
                
            market_type = market_type or self.market_type
            self.client.options['defaultType'] = market_type
            
            balance = self.client.fetch_balance()
            total = balance['total'].get('USDT', 0)
            
            for currency, amount in balance['total'].items():
                if currency != 'USDT' and amount > 0:
                    try:
                        ticker = self.client.fetch_ticker(f"{currency}/USDT")
                        total += amount * ticker['last']
                    except:
                        continue
                        
            return total
            
        except Exception as e:
            self.logger.error(f"Chyba při získávání portfolia: {str(e)}")
            return 0

    def get_24h_change(self, symbol=None, market_type=None):
        """Získá 24h procentuální změnu"""
        try:
            market_type = market_type or self.market_type
            self.client.options['defaultType'] = market_type
            
            symbol = symbol or f"{self.base_currency}/USDT"
            return self.client.fetch_ticker(symbol)['percentage']
            
        except Exception as e:
            self.logger.error(f"Chyba při získávání změny: {str(e)}")
            return 0

    def get_24h_volume(self, symbol=None, market_type=None):
        """Získá 24h objem obchodů"""
        try:
            market_type = market_type or self.market_type
            self.client.options['defaultType'] = market_type
            
            symbol = symbol or f"{self.base_currency}/USDT"
            return self.client.fetch_ticker(symbol)['quoteVolume']
            
        except Exception as e:
            self.logger.error(f"Chyba při získávání objemu: {str(e)}")
            return 0

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
            
            for i, row in df.iterrows():
                current_price = self.get_current_price(row['symbol'], row['market_type'])
                df.at[i, 'current_pnl'] = self._calculate_pnl(row, current_price)
                df.at[i, 'current_price'] = current_price
                
            return df.to_dict('records')
            
        except Exception as e:
            self.logger.error(f"Chyba při získávání pozic: {str(e)}")
            return []

    def _calculate_pnl(self, position, current_price):
        """Vypočítá aktuální P/L pro pozici"""
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
                self.client.options['defaultType'] = position_data['market_type']
                
                order = self.client.create_order(
                    symbol=position_data['symbol'],
                    type='market',
                    side=close_side.lower(),
                    amount=position_data['amount']
                )
                
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

    def get_trade_history(self, limit=100, market_type=None):
        """Získá historii obchodů"""
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
            self.logger.error(f"Chyba při získávání historie: {str(e)}")
            return []

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
