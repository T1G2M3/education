import ccxt
import time
from decimal import Decimal
import pandas as pd
import logging
from decouple import config as env_config

class BinanceConnector:
    def __init__(self, yaml_config):
        self.yaml_config = yaml_config
        self.mode = yaml_config.get('mode', 'dry')
        self.base_currency = yaml_config.get('base_currency', 'BNB')
        self.logger = logging.getLogger(__name__)
        
        # Inicializace API klienta
        try:
            self.client = ccxt.binance({
                'apiKey': env_config('BINANCE_API_KEY', default=''),
                'secret': env_config('BINANCE_API_SECRET', default=''),
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'spot',
                    'adjustForTimeDifference': True
                },
                'timeout': 30000  # Zvýšený timeout
            })
            
            # Nastavení dry režimu
            if self.mode == 'dry':
                self.client.set_sandbox_mode(True)
                self.virtual_balance = float(yaml_config.get('virtual_balance', 1000.0))
                
            # Historie obchodů pro dry režim
            self.trades_history = []
                
            # Risk management bude inicializován externě
            self.risk_manager = None
        except Exception as e:
            self.logger.error(f"Chyba při inicializaci Binance klienta: {str(e)}")
            raise

    def get_real_time_data(self, symbol=None, timeframe=None, limit=500):
        try:
            if not symbol:
                symbol = f"{self.base_currency}/USDT"
            if not timeframe:
                timeframe = self.yaml_config['strategies']['params'].get('timeframe', '15m')
                
            # V dry režimu vygenerujeme dummy data, pokud neprojde API volání
            try:
                return self.client.fetch_ohlcv(symbol, timeframe, limit=limit)
            except Exception as e:
                if self.mode == 'dry':
                    self.logger.warning(f"Používám dummy data kvůli chybě: {str(e)}")
                    return self._generate_dummy_data(limit)
                else:
                    raise
        except Exception as e:
            self.logger.error(f"Chyba při získávání dat: {str(e)}")
            return []

    def _generate_dummy_data(self, limit=500):
        """Generuje testovací data pro vývoj"""
        import numpy as np
        from datetime import datetime, timedelta
        
        now = datetime.now()
        data = []
        price = 300.0
        
        for i in range(limit):
            timestamp = int((now - timedelta(minutes=i)).timestamp() * 1000)
            close = price * (1 + np.random.normal(0, 0.001))
            high = close * (1 + abs(np.random.normal(0, 0.001)))
            low = close * (1 - abs(np.random.normal(0, 0.001)))
            open_price = close * (1 + np.random.normal(0, 0.001))
            volume = np.random.normal(100, 10)
            
            data.insert(0, [timestamp, open_price, high, low, close, volume])
            price = close
            
        return data

    def execute_trade(self, decision, amount, order_type='market', sl=None, tp=None):
        symbol = f"{self.base_currency}/USDT"
        
        if self.mode == 'dry':
            self.logger.info(f"[DRY RUN] {decision} {amount} {symbol}")
            if hasattr(self, 'risk_manager') and self.risk_manager:
                self._update_virtual_position(decision, amount, sl, tp)
            
            # Zaznamenání obchodu pro historii
            current_price = self.get_current_price()
            self.record_trade(decision, amount, current_price)
            
            return {'status': 'simulated'}
        
        try:
            order_params = {
                'symbol': symbol,
                'amount': amount,
                'params': {}
            }
            
            if sl or tp:
                order_params['params'] = {
                    'stopLossPrice': str(sl) if sl else None,
                    'takeProfitPrice': str(tp) if tp else None
                }
            
            if order_type == 'market':
                return self.client.create_market_order(
                    side='buy' if decision == 'BUY' else 'sell',
                    **order_params
                )
            elif order_type == 'limit':
                return self.client.create_limit_order(
                    price=self.get_current_price(),
                    **order_params
                )
                
        except Exception as e:
            self.logger.error(f"Trade error: {str(e)}")
            return {'error': str(e)}

    def _update_virtual_position(self, decision, amount, sl, tp):
        if not hasattr(self, 'risk_manager') or not self.risk_manager:
            return
            
        price = self.get_current_price()
        self.risk_manager.open_positions.append({
            'direction': 'LONG' if decision == 'BUY' else 'SHORT',
            'entry_price': price,
            'amount': amount,
            'stop_loss': sl,
            'take_profit': tp,
            'timestamp': time.time(),
            'symbol': f"{self.base_currency}/USDT"
        })

    def get_current_price(self, symbol=None):
        try:
            if not symbol:
                symbol = f"{self.base_currency}/USDT"
                
            # V dry režimu vygenerujeme dummy cenu, pokud neprojde API volání
            try:
                ticker = self.client.fetch_ticker(symbol)
                return ticker['last']
            except Exception as e:
                if self.mode == 'dry':
                    import random
                    dummy_price = 300.0 * (1 + random.uniform(-0.01, 0.01))
                    self.logger.warning(f"Používám dummy cenu: {dummy_price}")
                    return dummy_price
                else:
                    raise
        except Exception as e:
            self.logger.error(f"Chyba při získávání aktuální ceny: {str(e)}")
            return 0

    def get_portfolio_value(self):
        try:
            if self.mode == 'dry':
                return self.virtual_balance
                
            balance = self.client.fetch_balance()
            return balance['total'].get('USDT', 0)
        except Exception as e:
            self.logger.error(f"Chyba při získávání hodnoty portfolia: {str(e)}")
            return 0

    def get_24h_change(self, symbol=None):
        try:
            if not symbol:
                symbol = f"{self.base_currency}/USDT"
                
            # V dry režimu vygenerujeme dummy hodnotu, pokud neprojde API volání
            try:
                ticker = self.client.fetch_ticker(symbol)
                return ticker['percentage']
            except Exception as e:
                if self.mode == 'dry':
                    import random
                    dummy_change = random.uniform(-5, 5)
                    self.logger.warning(f"Používám dummy změnu: {dummy_change}%")
                    return dummy_change
                else:
                    raise
        except Exception as e:
            self.logger.error(f"Chyba při získávání 24h změny: {str(e)}")
            return 0
    
    def get_recent_trades(self, limit=10):
        """Vrací historii obchodů"""
        try:
            if self.mode == 'dry':
                return self.trades_history[-limit:] if hasattr(self, 'trades_history') else []
            else:
                try:
                    trades = self.client.fetch_my_trades(symbol=f"{self.base_currency}/USDT", limit=limit)
                    return [self._format_trade(t) for t in trades]
                except Exception as e:
                    self.logger.error(f"Chyba při načítání obchodů: {str(e)}")
                    return []
        except Exception as e:
            self.logger.error(f"Chyba v get_recent_trades: {str(e)}")
            return []
            
    def _format_trade(self, trade):
        """Formátuje surová data z API do jednotného formátu"""
        return {
            'time': pd.to_datetime(trade['timestamp'], unit='ms') if 'timestamp' in trade else pd.Timestamp.now(),
            'type': trade.get('side', '').upper(),
            'amount': float(trade.get('amount', 0)),
            'price': float(trade.get('price', 0)),
            'profit': float(trade.get('profit', 0))
        }
        
    def record_trade(self, direction, amount, price, exit_price=None):
        """Zaznamenává obchod do historie"""
        profit = 0
        if exit_price:
            profit = (exit_price - price) * amount
            if direction == 'SELL':
                profit = -profit
                
        trade = {
            'time': pd.Timestamp.now(),
            'type': direction,
            'amount': amount,
            'price': price,
            'profit': profit
        }
        
        if not hasattr(self, 'trades_history'):
            self.trades_history = []
            
        self.trades_history.append(trade)
        return trade
