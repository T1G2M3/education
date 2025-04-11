# core/risk_management.py
import time
import logging
from decimal import Decimal

class AdvancedRiskManager:
    def __init__(self, config, exchange):
        self.logger = logging.getLogger(__name__)
        self.exchange = exchange
        self.stop_loss = float(config['risk_management']['stop_loss'].strip('%')) / 100
        self.take_profit = float(config['risk_management']['take_profit'].strip('%')) / 100
        self.max_trade_size = config['risk_management']['max_trade_size']
        self.leverage = config['risk_management']['leverage']
        self.open_positions = []
        self.trade_history = []

    def evaluate_risk(self, decision, current_price, portfolio):
        try:
            self._check_open_positions(current_price)
            position_size = self._calculate_position_size(portfolio)
            return decision if position_size <= self.max_trade_size else "HOLD"
        except Exception as e:
            self.logger.error(f"Chyba v risk managementu: {str(e)}")
            return "HOLD"

    def _check_open_positions(self, current_price):
        for position in self.open_positions.copy():
            price_change = (current_price - position['entry_price']) / position['entry_price']
            
            if position['direction'] == 'LONG':
                if price_change <= -self.stop_loss or price_change >= self.take_profit:
                    self._close_position(position, current_price)
            elif position['direction'] == 'SHORT':
                if price_change >= self.stop_loss or price_change <= -self.take_profit:
                    self._close_position(position, current_price)

    def _close_position(self, position, current_price):
        try:
            if self.exchange.mode == 'dry':
                profit = (current_price - position['entry_price']) * position['amount']
                profit *= -1 if position['direction'] == 'SHORT' else 1
                self._record_trade(position, current_price, profit)
                self.open_positions.remove(position)
                return

            if position['direction'] == 'LONG':
                self.exchange.client.create_market_sell_order(
                    position['symbol'], 
                    position['amount']
                )
            else:
                self.exchange.client.create_market_buy_order(
                    position['symbol'], 
                    position['amount']
                )
            self._record_trade(position, current_price)
            self.open_positions.remove(position)
        except Exception as e:
            self.logger.error(f"Chyba při uzavírání pozice: {str(e)}")

    def _record_trade(self, position, exit_price, profit=None):
        trade = {
            'timestamp': time.time(),
            'direction': position['direction'],
            'entry_price': position['entry_price'],
            'exit_price': exit_price,
            'amount': position['amount'],
            'profit': profit if profit else self._calculate_profit(position, exit_price),
            'symbol': position['symbol']
        }
        self.trade_history.append(trade)

    def _calculate_profit(self, position, exit_price):
        if position['direction'] == 'LONG':
            return (exit_price - position['entry_price']) * position['amount']
        return (position['entry_price'] - exit_price) * position['amount']

    def _calculate_position_size(self, portfolio):
        if self.exchange.mode == 'dry':
            return self.max_trade_size
            
        balance = self.exchange.client.fetch_balance()['total']['USDT']
        return min(
            self.max_trade_size,
            (balance * self.leverage) / 100
        )

    def get_performance_metrics(self):
        wins = [t for t in self.trade_history if t['profit'] > 0]
        return {
            'total_profit': sum(t['profit'] for t in self.trade_history),
            'win_rate': len(wins)/len(self.trade_history) if self.trade_history else 0,
            'profit_factor': sum(t['profit'] for t in wins) / abs(sum(t['profit'] for t in self.trade_history if t['profit'] < 0)) if wins else 0
        }
