import pandas as pd
import talib
import numpy as np
from sklearn.preprocessing import StandardScaler
import logging

class DataProcessor:
    def __init__(self, config=None):
        self.config = config or {}
        self.lookback_window = self.config.get('lookback_window', 60)
        self.scaler = StandardScaler()
        self.logger = logging.getLogger(__name__)

    def process_data(self, raw_data):
        try:
            # Kontrola, že raw_data není prázdné
            if not raw_data or len(raw_data) == 0:
                self.logger.warning("Prázdná vstupní data")
                return np.array([])
                
            # Převod dat na DataFrame
            df = pd.DataFrame(raw_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            
            # Technické indikátory
            df['rsi'] = talib.RSI(df['close'], timeperiod=14)
            df['ema_20'] = talib.EMA(df['close'], timeperiod=20)
            df['ema_50'] = talib.EMA(df['close'], timeperiod=50)
            
            # Normalizace
            self.scaler.fit(df[['close']])
            df['scaled_close'] = self.scaler.transform(df[['close']])
            
            # Kontrola dostatku dat
            values = df['scaled_close'].values
            if len(values) < self.lookback_window:
                self.logger.warning(f"Nedostatek dat: {len(values)}/{self.lookback_window}")
                return np.array([])
                
            # Vytvoření sekvencí
            sequences = []
            for i in range(self.lookback_window, len(values)):
                sequences.append(values[i-self.lookback_window:i])
            
            # Ověření, že máme nějaké sekvence
            if not sequences:
                return np.array([])
                
            return np.array(sequences).reshape(-1, self.lookback_window, 1)
            
        except Exception as e:
            self.logger.error(f"Chyba při zpracování dat: {str(e)}")
            # Vrátíme prázdné pole místo vyhození výjimky
            return np.array([])

    def create_scaler(self, features):
        self.scaler.fit(features)
        return self.scaler

    def add_custom_indicator(self, df, indicator_func):
        return indicator_func(df)
