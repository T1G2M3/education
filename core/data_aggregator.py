# core/data_aggregator.py
import ccxt
from coinmetrics.api_client import CoinMetricsClient

class DataAggregator:
    def __init__(self):
        self.sources = {
            'binance': ccxt.binance(),
            'coinmetrics': CoinMetricsClient(),
            'kraken': ccxt.kraken()
        }

    def get_combined_data(self, symbol='BNB'):
        dfs = []
        for source_name, client in self.sources.items():
            try:
                data = client.fetch_ohlcv(f'{symbol}/USDT', '1h')
                df = pd.DataFrame(data)
                df['source'] = source_name
                dfs.append(df)
            except Exception as e:
                print(f"Chyba při načítání z {source_name}: {str(e)}")
        
        combined_df = pd.concat(dfs)
        return combined_df.pivot_table(
            index='timestamp',
            columns='source',
            values='close'
        ).ffill()
