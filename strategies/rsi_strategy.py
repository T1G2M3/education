# strategies/rsi_strategy.py
import talib
import numpy as np
from strategies.base_strategy import BaseStrategy
from core.data_processor import DataProcessor
from ai.model_loader import ModelLoader

class RSIStrategy(BaseStrategy):
    def __init__(self, 
                 rsi_period=14,
                 ema_short=20,
                 ema_long=50,
                 volume_threshold=1.5,
                 ai_confirmation=True):
        
        self.rsi_period = rsi_period
        self.ema_short = ema_short
        self.ema_long = ema_long
        self.volume_threshold = volume_threshold
        self.ai_confirmation = ai_confirmation
        self.ai_model = ModelLoader('ai/models/rsi_boost_model.h5').load() if ai_confirmation else None
        self.data_processor = DataProcessor()

    def analyze(self, data):
        df = self.data_processor.process_data(data)
        
        # Výpočet indikátorů
        df['rsi'] = talib.RSI(df['close'], timeperiod=self.rsi_period)
        df['ema_short'] = talib.EMA(df['close'], timeperiod=self.ema_short)
        df['ema_long'] = talib.EMA(df['close'], timeperiod=self.ema_long)
        df['volume_ma'] = talib.SMA(df['volume'], timeperiod=20)
        
        # Generování základních signálů
        df['base_signal'] = 0
        df.loc[
            (df['rsi'] < 30) & 
            (df['ema_short'] > df['ema_long']) & 
            (df['volume'] > df['volume_ma'] * self.volume_threshold), 
            'base_signal'
        ] = 1  # Nákup
        
        df.loc[
            (df['rsi'] > 70) & 
            (df['ema_short'] < df['ema_long']), 
            'base_signal'
        ] = -1  # Prodej
        
        # AI potvrzení signálů
        if self.ai_confirmation:
            df = self._apply_ai_filter(df)
            
        # Rozhodovací logika
        latest_signal = df['final_signal'].iloc[-1]
        
        if latest_signal == 1:
            return "BUY"
        elif latest_signal == -1:
            return "SELL"
        return "HOLD"

    def _apply_ai_filter(self, df):
        # Příprava vstupních dat pro AI model
        features = df[['close', 'volume', 'rsi', 'ema_short', 'ema_long']]
        features = (features - features.mean()) / features.std()  # Normalizace
        
        # Predikce
        predictions = self.ai_model.predict(features.values[-100:])  # Použij posledních 100 období
        df['ai_confidence'] = predictions
        
        # Kombinace signálů
        df['final_signal'] = np.where(
            (df['base_signal'] != 0) & (df['ai_confidence'] > 0.65),
            df['base_signal'],
            0
        )
        
        return df

    def get_params(self):
        return {
            'rsi_period': self.rsi_period,
            'ema_short': self.ema_short,
            'ema_long': self.ema_long,
            'volume_threshold': self.volume_threshold,
            'ai_confirmation': self.ai_confirmation
        }

    def set_params(self, **params):
        for key, value in params.items():
            if hasattr(self, key):
                setattr(self, key, value)
