# ui/performance_dashboard.py
import dash
from dash import dcc, html, Input, Output
import plotly.express as px
import pandas as pd
import sqlite3
import logging

# Konfigurace loggeru
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/performance_dashboard.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def create_dashboard(app):
    """Vytvoří layout pro dashboard výkonu"""
    app.layout = html.Div([
        dcc.Interval(id='update-interval', interval=60*1000),
        html.H1("Obchodní Performance", style={'textAlign': 'center', 'color': '#00ff88'}),
        dcc.Graph(id='equity-curve'),
        html.Div([
            html.Div([
                html.H3("Sharpe Ratio"),
                html.Div(id='sharpe-ratio', className="metric-value")
            ], className='metric-box'),
            html.Div([
                html.H3("Win Rate"),
                html.Div(id='win-rate', className="metric-value")
            ], className='metric-box')
        ], className='metrics-container'),
        html.Div(id='error-message', style={'color': '#ff5555', 'textAlign': 'center'})
    ])
    '''
    @app.callback(
        [Output('equity-curve', 'figure'),
         Output('sharpe-ratio', 'children'),
         Output('win-rate', 'children')],
        [Input('update-interval', 'n_intervals')]
    )
    '''
    def update_metrics(n):
        """Aktualizuje metriky výkonu"""
        try:
            conn = sqlite3.connect('data/trading_history.db', timeout=30)
            query = "SELECT timestamp, profit FROM trades ORDER BY timestamp ASC"
            df = pd.read_sql(query, conn, parse_dates=['timestamp'])
            conn.close()

            if df.empty:
                logger.warning("Prázdná databáze")
                return (px.line(title="Žádná data"), "N/A", "N/A")

            # Kontrola existence sloupce
            if 'profit' not in df.columns:
                raise ValueError("Chybějící sloupec 'profit' v datech")

            df['cumulative_profit'] = df['profit'].cumsum()
            
            # Oprava pro prázdná data
            if len(df) < 2:
                return (px.line(title="Nedostatek dat"), "N/A", "N/A")

            sharpe_ratio = calculate_sharpe(df)
            win_rate = calculate_win_rate(df)

            fig = px.line(df, x='timestamp', y='cumulative_profit', 
                        title="Křivka kapitálu")
            fig.update_layout(template='plotly_dark')
            
            return (fig, f"{sharpe_ratio:.2f}", f"{win_rate:.1%}")
            
        except Exception as e:
            logger.error(f"Chyba: {str(e)}")
            return (px.line(title="Chyba"), "Chyba", "Chyba")
        


    def calculate_sharpe(df):
        """Vypočítá Sharpe Ratio na základě zisků"""
        try:
            returns = df['profit'].pct_change().dropna()
            mean_return = returns.mean()
            std_return = returns.std()
            sharpe_ratio = mean_return / std_return * (252 ** 0.5)  # Annualized Sharpe Ratio
            return sharpe_ratio if not pd.isna(sharpe_ratio) else 0.0
        except Exception as e:
            logger.error(f"Chyba při výpočtu Sharpe Ratio: {str(e)}")
            return 0.0

    def calculate_win_rate(df):
        """Vypočítá Win Rate na základě obchodů"""
        try:
            win_trades = len(df[df['profit'] > 0])
            total_trades = len(df)
            return win_trades / total_trades if total_trades > 0 else 0.0
        except Exception as e:
            logger.error(f"Chyba při výpočtu Win Rate: {str(e)}")
            return 0.0

if __name__ == '__main__':
    app = dash.Dash(__name__)
    create_dashboard(app)
    app.run(debug=True)
