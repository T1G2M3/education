import yaml
import dash
from dash import dcc, html, Input, Output
import plotly.graph_objects as go
import pandas as pd
import traceback
from core.exchange import BinanceConnector
from core.data_processor import DataProcessor

def load_config():
    # Oprava - přidáno explicitní kódování UTF-8
    with open("config/config.yaml", encoding='utf-8') as f:
        return yaml.safe_load(f)

config = load_config()

app = dash.Dash(__name__, suppress_callback_exceptions=True)
app.title = "Crypto Trading Bot Pro"

app.layout = html.Div([
    dcc.Store(id='session-data'),
    dcc.Interval(id='update-interval', interval=5*1000),
    
    html.Div([
        html.Div([
            html.H1("💰 Smart Trade Dashboard Pro", className="header"),
            html.H2("🤖 Created TGM", className="header"),
            html.Div([
                dcc.Dropdown(
                    id='timeframe-selector',
                    options=[
                        {'label': '1 Min', 'value': '1m'},
                        {'label': '5 Min', 'value': '5m'},
                        {'label': '15 Min', 'value': '15m'},
                        {'label': '1 Hour', 'value': '1h'}
                    ],
                    value='5m',
                    className="dropdown"
                ),
                dcc.Dropdown(
                    id='asset-selector',
                    options=[
                        {'label': 'BNB/USDT', 'value': 'BNB/USDT'},
                        {'label': 'BTC/USDT', 'value': 'BTC/USDT'}
                    ],
                    value='BNB/USDT',
                    className="dropdown"
                )
            ], className="control-row"),
            
            dcc.Graph(id='main-chart', className="main-chart"),
            
            html.Div([
                html.Div([
                    html.H3("Portfolio Value"),
                    html.Div(id='portfolio-value', className="metric-value"),
                    dcc.Graph(id='equity-curve', className="mini-chart")
                ], className="metric-box"),
                
                html.Div([
                    html.H3("24h Performance"),
                    html.Div(id='daily-change', className="metric-value"),
                    dcc.Graph(id='performance-gauge', className="mini-chart")
                ], className="metric-box"),
                
                html.Div([
                    html.H3("Active Strategy"),
                    html.Div(id='active-strategy', className="metric-value"),
                    html.Button("Strategy Settings", id='strategy-settings-btn', className="control-btn")
                ], className="metric-box")
            ], className="metrics-container"),
            
            html.Div([
                html.Div([
                    html.H3("Trade History"),
                    html.Table(
                        id='trade-history',
                        className="trades-table",
                        children=[html.Tr([
                            html.Th("Time"), 
                            html.Th("Type"),
                            html.Th("Amount"),
                            html.Th("Price"),
                            html.Th("Profit")
                        ])]
                    )
                ], className="trades-panel"),
                
                html.Div([
                    html.H3("Risk Management"),
                    html.Div([
                        html.Label("Stop Loss (%)"),
                        dcc.Input(id='stop-loss-input', type='number', value=2),
                        html.Label("Take Profit (%)"),
                        dcc.Input(id='take-profit-input', type='number', value=5),
                        html.Button("Apply", id='risk-settings-btn', className="control-btn")
                    ], className="risk-controls")
                ], className="risk-panel")
            ], className="bottom-container")
        ], className="main-container")
    ], className="app-container")
])

@app.callback(
    [Output('main-chart', 'figure'),
     Output('portfolio-value', 'children'),
     Output('daily-change', 'children'),
     Output('trade-history', 'children'),
     Output('equity-curve', 'figure'),
     Output('performance-gauge', 'figure')],
    [Input('update-interval', 'n_intervals'),
     Input('timeframe-selector', 'value'),
     Input('asset-selector', 'value')]
)
def update_all(_, timeframe, asset):
    try:
        # Vytvořit instanci Exchange a předat konfiguraci
        exchange = BinanceConnector(config)
        processor = DataProcessor()
        
        # Získání OHLCV dat
        raw_data = exchange.get_real_time_data(symbol=asset, timeframe=timeframe)
        
        # Zpracování pro grafy - musíme použít původní dataframe, ne zpracovaný pro ML
        df = pd.DataFrame(raw_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        
        # Candlestick graf
        fig = go.Figure(data=[
            go.Candlestick(
                x=df.index,
                open=df['open'],
                high=df['high'],
                low=df['low'],
                close=df['close'],
                name='Price'
            )
        ])
        
        # Vzhled grafu
        fig.update_layout(
            xaxis_rangeslider_visible=False,
            plot_bgcolor='#1e1e1e',
            paper_bgcolor='#1e1e1e',
            font=dict(color='white'),
            margin=dict(l=20, r=20, t=40, b=20)
        )
        
        # Portfolio a 24h změna
        portfolio_value = exchange.get_portfolio_value()
        daily_change = exchange.get_24h_change(asset)
        
        # Historie obchodů
        try:
            # Pokud metoda existuje, použijeme ji
            if hasattr(exchange, 'get_recent_trades'):
                trades = exchange.get_recent_trades()
            else:
                # Jinak vytvoříme prázdný seznam
                trades = []
                
        except Exception as trade_error:
            print(f"Chyba při načítání obchodů: {str(trade_error)}")
            trades = []
        
        # Vytvoření řádků tabulky
        trade_rows = [html.Tr([
            html.Td(getattr(trade, 'time', '') if hasattr(trade, 'time') else ''), 
            html.Td(
                getattr(trade, 'type', '') if hasattr(trade, 'type') else '', 
                style={'color': 'green' if getattr(trade, 'type', '') == 'BUY' else 'red'}
            ),
            html.Td(f"{getattr(trade, 'amount', 0):.4f}"),
            html.Td(f"{getattr(trade, 'price', 0):.2f}$"),
            html.Td(
                f"{getattr(trade, 'profit', 0):.2f}$", 
                style={'color': 'green' if getattr(trade, 'profit', 0) >= 0 else 'red'}
            )
        ]) for trade in trades]
        
        # Pokud není žádný obchod, přidáme prázdný řádek
        if not trade_rows:
            trade_rows = [html.Tr([html.Td("No trades yet", colSpan=5)])]
        
        # Equity křivka
        equity_fig = go.Figure(data=go.Scatter(
            x=df.index,
            y=df['close'],
            line=dict(color='#00ff88')
        ))
        
        equity_fig.update_layout(
            plot_bgcolor='#1e1e1e',
            paper_bgcolor='#1e1e1e',
            font=dict(color='white'),
            margin=dict(l=20, r=20, t=20, b=20)
        )
        
        # Gauge pro výkon
        gauge_fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=daily_change,
            domain={'x': [0, 1], 'y': [0, 1]},
            gauge={
                'axis': {'range': [-10, 10]},
                'bar': {'color': "#00ff88" if daily_change >= 0 else "#ff5555"},
                'steps': [
                    {'range': [-10, 0], 'color': "#330000"},
                    {'range': [0, 10], 'color': "#003300"}
                ]
            }
        ))
        
        gauge_fig.update_layout(
            plot_bgcolor='#1e1e1e',
            paper_bgcolor='#1e1e1e',
            font=dict(color='white'),
            margin=dict(l=20, r=20, t=20, b=20)
        )
        
        return fig, f"{portfolio_value:.2f}$", f"{daily_change:.2f}%", trade_rows, equity_fig, gauge_fig
    
    except Exception as e:
        # Logování chyby pro debugging
        print(f"Chyba v dashboard: {str(e)}")
        print(traceback.format_exc())
        
        # Vytvoření prázdných grafů
        empty_fig = go.Figure()
        empty_fig.update_layout(
            plot_bgcolor='#1e1e1e',
            paper_bgcolor='#1e1e1e',
            font=dict(color='white')
        )
        
        empty_table = [html.Tr([html.Td("Data error", colSpan=5)])]
        
        return empty_fig, "0.00$", "0.00%", empty_table, empty_fig, empty_fig

# Přidáme hodnotu active-strategy
@app.callback(
    Output('active-strategy', 'children'),
    [Input('update-interval', 'n_intervals')]
)
def update_strategy_info(_):
    try:
        return config['strategies']['active']
    except:
        return "Unknown"

if __name__ == '__main__':
    app.run_server(debug=True)
