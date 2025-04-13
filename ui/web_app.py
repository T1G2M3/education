# ui/web_app.py
import logging
logging.basicConfig(level=logging.INFO)
from dash.exceptions import PreventUpdate
import dash
from dash import dcc, html, Input, Output, State, callback_context
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import sqlite3
import os
from datetime import datetime, timedelta
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
import flask
from werkzeug.security import generate_password_hash, check_password_hash
from core.exchange import BinanceConnector
import yaml
import traceback
import dash_bootstrap_components as dbc
from scripts.init_database import import_exchange_data


# Konfigurace loggeru
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/dashboard.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('dashboard')

# Zajištění existence adresářů
if not os.path.exists('data'):
    os.makedirs('data')
if not os.path.exists('logs'):
    os.makedirs('logs')

# Inicializace Flask serveru
server = flask.Flask(__name__)
server.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'tajny-klic-pro-aplikaci-1234')

# Inicializace Login Manageru
login_manager = LoginManager()
login_manager.init_app(server)
login_manager.login_view = '/login'

# Třída uživatele
class User(UserMixin):
    def __init__(self, user_id, username, role):
        self.id = user_id
        self.username = username
        self.role = role

# Demo uživatelé
users_db = {
    'admin': {
        'password': generate_password_hash('admin123'),
        'role': 'admin'
    },
    'user': {
        'password': generate_password_hash('user123'),
        'role': 'user'
    }
}

@login_manager.user_loader
def load_user(user_id):
    if user_id in users_db:
        return User(user_id, user_id, users_db[user_id]['role'])
    return None

# Inicializace databáze
def init_database():
    conn = sqlite3.connect('data/trading_history.db')
    cursor = conn.cursor()
    
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
        market_type TEXT
    )''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME,
        symbol TEXT,
        signal TEXT,
        confidence REAL,
        action_taken TEXT,
        market_type TEXT
    )''')
    
    conn.commit()
    conn.close()

init_database()




# Načtení konfigurace
def load_config():
    with open("config/config.yaml", encoding='utf-8') as f:
        return yaml.safe_load(f)

config = load_config()
exchange = BinanceConnector(config)
available_pairs = exchange.get_market_pairs()

# Inicializace Dash aplikace
app = dash.Dash(
    __name__,
    server=server,
    suppress_callback_exceptions=True,
    external_stylesheets=[dbc.themes.DARKLY],
    title="Crypto Trading Bot Pro"
)

# Přihlašovací layout
login_layout = html.Div([
    html.Div([
        html.Div([
            html.H1("Smart Trade Dashboard Pro", className="login-header"),
            html.H2("Přihlášení", className="login-subtitle"),
            dcc.Input(id='username-input', type='text', placeholder='Uživatelské jméno', className="login-input"),
            dcc.Input(id='password-input', type='password', placeholder='Heslo', className="login-input"),
            html.Button('Přihlásit se', id='login-button', className="login-button"),
            html.Div(id='login-error', className="login-error")
        ], className="login-container")
    ], className="login-page")
])

dbc.Spinner(
    children=[dcc.Graph(id='main-chart')],
    color="primary",
    type="grow"
)


# Hlavní layout
app_layout = html.Div([
    dcc.Location(id='url', refresh=False),
    dcc.Store(id='session-data'),
    dcc.Interval(id='update-interval', interval=60*1000), # 1 minuta dcc.Interval(id='update-interval', interval=60*1000)
    
    html.Div([
        html.Div([
            html.H3("Smart Trade Dashboard Pro", className="nav-title"),
            html.Div(id='user-info', className="user-info"),
            html.Button('Odhlásit se', id='logout-button', className="logout-button")
        ], className="navbar-content")
    ], className="navbar"),
    
    html.Div([
        dcc.Tabs(id='main-tabs', value='dashboard', children=[
            dcc.Tab(label='Dashboard', value='dashboard'),
            dcc.Tab(label='Multi-Chart', value='multi-chart'),
            dcc.Tab(label='Performance', value='performance'),
            dcc.Tab(label='Settings', value='settings'),
            dcc.Tab(label='Logs', value='logs'),
        ]),
        html.Div(id='tabs-content')
    ], className="main-container")
])

# Callback pro ukládání nastavení rizika
@app.callback(
    Output('bot-status-text', 'children'),
    [Input('save-settings', 'n_clicks'),
     Input('save-strategy-settings', 'n_clicks'),
     Input('save-risk-settings', 'n_clicks')],
    [State('mode-setting', 'value'),
     State('market-type-setting', 'value'),
     State('base-currency-setting', 'value'),
     State('refresh-interval-setting', 'value'),
     State('strategy-setting', 'value'),
     State('confidence-threshold-setting', 'value'),
     State('strategy-timeframe-setting', 'value'),
     State('global-stop-loss-setting', 'value'),
     State('global-take-profit-setting', 'value'),
     State('global-trade-size-setting', 'value'),
     State('leverage-setting', 'value')],
    prevent_initial_call=True
)

def save_settings(
    risk_clicks, general_clicks, strategy_clicks, risk_global_clicks,
    stop_loss, take_profit, trade_amount,
    mode, market_type, base_currency, refresh_interval,
    strategy, confidence_threshold, strategy_timeframe,
    global_stop_loss, global_take_profit, global_trade_size, leverage):
    
    # Kontrola, zda je uživatel admin
    if not current_user.is_authenticated or current_user.role != 'admin':
        return "Unauthorized"
    
    ctx = callback_context
    if not ctx.triggered:
        return "Idle"
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    try:
        # Načtení aktuální konfigurace
        with open("config/config.yaml", 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            
        if trigger_id == 'risk-settings-btn' and risk_clicks:
            # Aktualizace hodnot rizika z dashboardu
            config['risk_management']['stop_loss'] = f"{stop_loss}%"
            config['risk_management']['take_profit'] = f"{take_profit}%"
            config['risk_management']['max_trade_size'] = trade_amount
            
            # Uložení konfigurace
            with open("config/config.yaml", 'w', encoding='utf-8') as f:
                yaml.dump(config, f, sort_keys=False)
                
            return "Risk settings updated"
            
        elif trigger_id == 'save-settings' and general_clicks:
            # Aktualizace obecných nastavení
            config['mode'] = mode
            config['market_type'] = market_type
            config['base_currency'] = base_currency
            config['api_settings']['refresh_interval'] = refresh_interval
            
            # Uložení konfigurace
            with open("config/config.yaml", 'w', encoding='utf-8') as f:
                yaml.dump(config, f, sort_keys=False)
                
            return "General settings updated"
            
        elif trigger_id == 'save-strategy-settings' and strategy_clicks:
            # Aktualizace nastavení strategie
            config['strategies']['active'] = strategy
            config['strategies']['params']['confidence_threshold'] = confidence_threshold
            config['strategies']['params']['timeframe'] = strategy_timeframe
            
            # Uložení konfigurace
            with open("config/config.yaml", 'w', encoding='utf-8') as f:
                yaml.dump(config, f, sort_keys=False)
                
            return "Strategy settings updated"
            
        elif trigger_id == 'save-risk-settings' and risk_global_clicks:
            # Aktualizace globálních nastavení rizika
            config['risk_management']['stop_loss'] = f"{global_stop_loss}%"
            config['risk_management']['take_profit'] = f"{global_take_profit}%"
            config['risk_management']['max_trade_size'] = global_trade_size
            config['risk_management']['leverage'] = leverage
            
            # Uložení konfigurace
            with open("config/config.yaml", 'w', encoding='utf-8') as f:
                yaml.dump(config, f, sort_keys=False)
                
            return "Risk settings updated"
            
        return "Settings unchanged"
    
    except Exception as e:
        logger.error(f"Chyba při ukládání nastavení: {str(e)}")
        return f"Error: {str(e)}"


# Dynamický routing
app.layout = html.Div([
    dcc.Location(id='url', refresh=False),
    html.Div(id='page-content')
])

@app.callback(
    Output('page-content', 'children'),
    [Input('url', 'pathname')]
)
def display_page(pathname):
    if pathname == '/login':
        return login_layout
    elif current_user.is_authenticated:
        return app_layout
    return login_layout

# Callback pro přihlášení
@app.callback(
    [Output('login-error', 'children'),
     Output('url', 'pathname')],
    [Input('login-button', 'n_clicks')],
    [State('username-input', 'value'),
     State('password-input', 'value')]
)
def login_user_callback(n_clicks, username, password):
    if n_clicks and username and password:
        if username in users_db and check_password_hash(users_db[username]['password'], password):
            user = User(username, username, users_db[username]['role'])
            login_user(user)
            return "", "/"
        return "Neplatné přihlašovací údaje", dash.no_update
    return "", dash.no_update

# Callback pro odhlášení
@app.callback(
    Output('url', 'pathname', allow_duplicate=True),
    [Input('logout-button', 'n_clicks')],
    prevent_initial_call=True
)
def logout_callback(n_clicks):
    if n_clicks:
        logout_user()
        return '/login'
    return dash.no_update

# Zobrazení informací o přihlášeném uživateli
@app.callback(
    Output('user-info', 'children'),
    [Input('url', 'pathname')]
)
def display_user_info(pathname):
    if current_user.is_authenticated:
        return html.Div([
            html.Span(f"Přihlášený uživatel: {current_user.username}"),
            html.Span(f" (Role: {current_user.role})", style={"color": "#00ff88" if current_user.role == "admin" else "#ffcc00"})
        ])
    return ""

# Layout záložky Dashboard
def create_dashboard_layout():
    return html.Div([
        # Ovládací prvky
        html.Div([
            dcc.Dropdown(
                id='market-type-selector',
                options=[
                    {'label': 'Spot', 'value': 'spot'},
                    {'label': 'Futures', 'value': 'futures'},
                ],
                value='spot',
                className="dropdown",
                style={'width': '200px'}
            ),
            dcc.Dropdown(
                id='timeframe-selector',
                options=[
                    {'label': '1 Min', 'value': '1m'},
                    {'label': '5 Min', 'value': '5m'},
                    {'label': '15 Min', 'value': '15m'},
                    {'label': '30 Min', 'value': '30m'},
                    {'label': '1 Hour', 'value': '1h'},
                    {'label': '4 Hour', 'value': '4h'},
                ],
                value='15m',
                className="dropdown",
                style={'width': '200px'}
            ),
            dcc.Dropdown(
                id='asset-selector',
                options=[{'label': pair, 'value': pair} for pair in available_pairs],
                value=config['base_currency'] + '/USDT',
                className="dropdown",
                style={'width': '200px'}
            ),
            html.Button('Start Bot', id='start-bot-btn', className='control-btn'),
            html.Button('Stop Bot', id='stop-bot-btn', className='control-btn', style={'background-color': '#ff5555'}),
        ], className="control-row"),
        
        # Hlavní graf
        dcc.Graph(id='main-chart', className="main-chart"),
        
        # Metriky a statistiky
        html.Div([
            html.Div([
                html.H3("Portfolio Value"),
                html.Div(id='portfolio-value', className="metric-value"),
                dcc.Graph(id='equity-curve', className="mini-chart")
            ], className="metric-box"),
            
            html.Div([
                html.H3("Performance"),
                html.Div(id='daily-change', className="metric-value"),
                dcc.Graph(id='performance-gauge', className="mini-chart")
            ], className="metric-box"),
            
            html.Div([
                html.H3("Trading Stats"),
                html.Div(id='trading-stats', className="performance-metrics", children=[
                    html.Div([
                        html.Div("Win Rate", className="metric-label"),
                        html.Div(id='win-rate', className="metric-value"),
                    ], className="metric-card"),
                    html.Div([
                        html.Div("Profit Factor", className="metric-label"),
                        html.Div(id='profit-factor', className="metric-value"),
                    ], className="metric-card"),
                    html.Div([
                        html.Div("Total Trades", className="metric-label"),
                        html.Div(id='total-trades', className="metric-value"),
                    ], className="metric-card"),
                ]),
            ], className="metric-box"),
        ], className="metrics-container"),
        
        # Spodní sekce
        html.Div([
            # Historie obchodů
            html.Div([
                html.H3("Trade History"),
                html.Div(id='trade-history-container', style={'overflow-y': 'auto', 'max-height': '300px'}, children=[
                    html.Table(
                        id='trade-history',
                        className="trades-table",
                        children=[html.Tr([
                            html.Th("Time"), 
                            html.Th("Type"),
                            html.Th("Pair"),
                            html.Th("Amount"),
                            html.Th("Price"),
                            html.Th("Profit")
                        ])]
                    )
                ])
            ], className="trades-panel"),
            
            # Risk management a nastavení
            html.Div([
                html.H3("Risk Management"),
                html.Div([
                    html.Label("Stop Loss (%)"),
                    dcc.Input(id='stop-loss-input', type='number', value=float(config['risk_management']['stop_loss'].strip('%')), min=0.1, max=50, step=0.1),
                    html.Label("Take Profit (%)"),
                    dcc.Input(id='take-profit-input', type='number', value=float(config['risk_management']['take_profit'].strip('%')), min=0.1, max=100, step=0.1),
                    html.Label("Trade Amount (USDT)"),
                    dcc.Input(id='trade-amount-input', type='number', value=config['risk_management']['max_trade_size'], min=1, max=1000, step=1),
                    html.Button("Apply", id='risk-settings-btn', className="control-btn", disabled=not current_user.is_authenticated or current_user.role != 'admin')
                ], className="risk-controls")
            ], className="risk-panel")
        ], className="bottom-container"),
        
        # Status bota
        html.Div([
            html.Div(id='bot-status', children=[
                html.Div([
                    html.H4("Bot Status"),
                    html.Div(id='bot-status-text', children="Idle", style={'color': '#ffcc00', 'font-weight': 'bold'}),
                ]),
                html.Div([
                    html.H4("Active Strategy"),
                    html.Div(id='active-strategy', children=config['strategies']['active']),
                ]),
                html.Div([
                    html.H4("Last Signal"),
                    html.Div(id='last-signal', children="No signal yet"),
                ]),
            ], style={
                'display': 'flex',
                'justify-content': 'space-between',
                'background-color': '#1e1e1e',
                'padding': '15px',
                'border-radius': '8px',
                'margin-top': '20px',
                'color': 'white'
            })
        ]),
    ])

# Layout záložky Multi-Chart
def create_multichart_layout():
    return html.Div([
        html.H3("Multi-Asset View", style={'color': 'white'}),
        
        # Ovládací prvky pro výběr párů a timeframe
        html.Div([
            dcc.Dropdown(
                id='multi-chart-market-type',
                options=[
                    {'label': 'Spot', 'value': 'spot'},
                    {'label': 'Futures', 'value': 'futures'},
                ],
                value='spot',
                className="dropdown",
                style={'width': '200px'}
            ),
            dcc.Dropdown(
                id='multi-chart-pairs',
                options=[{'label': pair, 'value': pair} for pair in available_pairs],
                value=['BNB/USDT', 'BTC/USDT', 'ETH/USDT', 'SOL/USDT'] if len(available_pairs) >= 4 else available_pairs[:min(4, len(available_pairs))],
                multi=True,
                placeholder="Select pairs to display",
                className="dropdown",
                style={'width': '350px'}
            ),
            dcc.Dropdown(
                id='multi-chart-timeframe',
                options=[
                    {'label': '5 Min', 'value': '5m'},
                    {'label': '15 Min', 'value': '15m'},
                    {'label': '1 Hour', 'value': '1h'},
                    {'label': '4 Hour', 'value': '4h'},
                ],
                value='15m',
                placeholder="Select timeframe",
                className="dropdown",
                style={'width': '200px'}
            ),
        ], className="control-row"),
        
        # Kontejner pro více grafů
        html.Div(id='multi-chart-container', className="multi-chart-container"),
        
        # Tabulka výkonnosti
        html.Div([
            html.H3("Performance Comparison", style={'color': 'white'}),
            html.Table(
                id='performance-table',
                className="trades-table",
                children=[html.Tr([
                    html.Th("Pair"), 
                    html.Th("Current Price"),
                    html.Th("24h Change"),
                    html.Th("Volume (USDT)"),
                    html.Th("Signal")
                ])]
            )
        ], className="performance-table")
    ])

# Layout záložky Performance
def create_performance_layout():
    return html.Div([
        html.H3("Trading Performance Analytics", style={'color': 'white'}),
        
        # Filtrování dat
        html.Div([
            dcc.Dropdown(
                id='performance-market-type',
                options=[
                    {'label': 'Spot', 'value': 'spot'},
                    {'label': 'Futures', 'value': 'futures'},
                    {'label': 'All Markets', 'value': 'all'},
                ],
                value='all',
                placeholder="Select market type",
                className="dropdown",
                style={'width': '200px'}
            ),
            dcc.Dropdown(
                id='performance-timerange',
                options=[
                    {'label': 'Today', 'value': 'today'},
                    {'label': 'Last 7 days', 'value': '7days'},
                    {'label': 'Last 30 days', 'value': '30days'},
                    {'label': 'All time', 'value': 'all'},
                ],
                value='all',
                placeholder="Select time range",
                className="dropdown",
                style={'width': '200px'}
            ),
            dcc.Dropdown(
                id='performance-pair',
                options=[{'label': 'All pairs', 'value': 'all'}] + [{'label': pair, 'value': pair} for pair in available_pairs],
                value='all',
                placeholder="Select pair",
                className="dropdown",
                style={'width': '200px'}
            ),
        ], className="control-row"),
        
        # Graf P&L
        html.Div([
            html.H3("Profit & Loss Curve", style={'color': 'white'}),
            dcc.Graph(id='pnl-chart', className="pnl-chart"),
        ], className="trades-panel"),
        
        # Detailní metriky
        html.Div([
            html.Div([
                html.H3("Trading Performance Metrics", style={'color': 'white'}),
                html.Div(id='detailed-metrics', className="metrics-grid", children=[
                    html.Div([
                        html.Div("Total Profit", className="metric-label"),
                        html.Div(id='total-profit', className="metric-value"),
                    ], className="metric-card"),
                    html.Div([
                        html.Div("Win Rate", className="metric-label"),
                        html.Div(id='detailed-win-rate', className="metric-value"),
                    ], className="metric-card"),
                    html.Div([
                        html.Div("Profit Factor", className="metric-label"),
                        html.Div(id='detailed-profit-factor', className="metric-value"),
                    ], className="metric-card"),
                    html.Div([
                        html.Div("Max Drawdown", className="metric-label"),
                        html.Div(id='max-drawdown', className="metric-value"),
                    ], className="metric-card"),
                ]),
            ], className="metric-box"),
        ], className="metrics-container"),
        
        # Distribuční grafy
        html.Div([
            html.Div([
                html.H3("Trade Distribution", style={'color': 'white'}),
                dcc.Graph(id='trade-distribution', className="mini-chart"),
            ], className="metric-box"),
            html.Div([
                html.H3("Profit Distribution", style={'color': 'white'}),
                dcc.Graph(id='profit-distribution', className="mini-chart"),
            ], className="metric-box"),
        ], className="metrics-container"),
    ])

# Layout záložky Settings
def create_settings_layout():
    return html.Div([
        html.H3("Bot Configuration", style={'color': 'white'}),
        
        html.Div([
            # General Settings
            html.Div([
                html.H4("General Settings", style={'color': 'white'}),
                html.Div(className="settings-form", children=[
                    # ... (ostatní prvky)
                    html.Button(
                        "Save General Settings", 
                        id='save-settings',  # Správné ID
                        className="control-btn",
                        n_clicks=0,
                        disabled=not current_user.is_authenticated or current_user.role != 'admin'
                    ),
                ]),
            ], className="metric-box"),
            
            # Strategy Settings
            html.Div([
                html.H4("Strategy Settings", style={'color': 'white'}),
                html.Div(className="settings-form", children=[
                    # ... (ostatní prvky)
                    html.Button(
                        "Save Strategy Settings", 
                        id='save-strategy-settings',  # Správné ID
                        className="control-btn",
                        n_clicks=0,
                        disabled=not current_user.is_authenticated or current_user.role != 'admin'
                    ),
                ]),
            ], className="metric-box"),
            
            # Risk Management
            html.Div([
                html.H4("Risk Management", style={'color': 'white'}),
                html.Div(className="settings-form", children=[
                    # ... (ostatní prvky)
                    html.Button(
                        "Save Risk Settings", 
                        id='save-risk-settings',  # Správné ID
                        className="control-btn",
                        n_clicks=0,
                        disabled=not current_user.is_authenticated or current_user.role != 'admin'
                    ),
                ]),
            ], className="metric-box"),
        ], className="metrics-container"),
    ])

def handle_settings_saves(settings_clicks, strategy_clicks, risk_clicks, *args):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise PreventUpdate
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    try:
        with open("config/config.yaml", "r") as f:
            config = yaml.safe_load(f)
            
        if trigger_id == 'save-settings':
            # Logika pro obecná nastavení
            return "General settings updated"
            
        elif trigger_id == 'save-strategy-settings':
            # Logika pro strategii
            return "Strategy settings updated"
            
        elif trigger_id == 'save-risk-settings':
            # Logika pro rizika
            return "Risk settings updated"
            
    except Exception as e:
        logger.error(f"Chyba při ukládání nastavení: {str(e)}")
        return f"Error: {str(e)}"
# Layout záložky Logs
def create_logs_layout():
    return html.Div([
        html.H3("Bot Activity & Logs", style={'color': 'white'}),
        
        # Filtrování logů
        html.Div([
            dcc.Dropdown(
                id='log-level-filter',
                options=[
                    {'label': 'All Levels', 'value': 'all'},
                    {'label': 'Info', 'value': 'info'},
                    {'label': 'Warning', 'value': 'warning'},
                    {'label': 'Error', 'value': 'error'},
                ],
                value='all',
                placeholder="Filter by log level",
                className="dropdown",
                style={'width': '200px'}
            ),
            dcc.Dropdown(
                id='log-market-type',
                options=[
                    {'label': 'All Markets', 'value': 'all'},
                    {'label': 'Spot', 'value': 'spot'},
                    {'label': 'Futures', 'value': 'futures'},
                ],
                value='all',
                placeholder="Market type",
                className="dropdown",
                style={'width': '200px'}
            ),
            dcc.Input(
                id='log-search',
                type='text',
                placeholder="Search in logs...",
                style={
                    'width': '300px',
                    'background-color': '#2a2a2a',
                    'border': '1px solid #444',
                    'color': 'white',
                    'padding': '8px',
                    'border-radius': '4px'
                }
            ),
        ], className="control-row"),
        
        # Zobrazení logů
        html.Div([
            html.H4("Bot Logs", style={'color': 'white'}),
            html.Div(id='bot-logs', className="log-container"),
        ], className="metric-box"),
        
        # Aktivní pozice
        html.Div([
            html.H4("Active Positions", style={'color': 'white'}),
            html.Table(
                id='active-positions',
                className="trades-table",
                children=[html.Tr([
                    html.Th("Open Time"), 
                    html.Th("Pair"),
                    html.Th("Type"),
                    html.Th("Market"),
                    html.Th("Amount"),
                    html.Th("Entry Price"),
                    html.Th("Current P/L"),
                    html.Th("SL/TP"),
                    html.Th("Actions")
                ])]
            )
        ], className="metric-box"),
        
        # Posledních N rozhodnutí bota
        html.Div([
            html.H4("Recent Bot Decisions", style={'color': 'white'}),
            html.Table(
                id='bot-decisions',
                className="trades-table",
                children=[html.Tr([
                    html.Th("Time"), 
                    html.Th("Pair"),
                    html.Th("Market"),
                    html.Th("Decision"),
                    html.Th("Confidence"),
                    html.Th("Action Taken")
                ])]
            )
        ], className="metric-box"),
    ])

# Callback pro navigaci mezi záložkami
@app.callback(
    Output('tabs-content', 'children'),
    [Input('main-tabs', 'value')]
)
def render_content(tab):
    if not current_user.is_authenticated:
        return login_layout
        
    if tab == 'dashboard':
        return create_dashboard_layout()
    elif tab == 'multi-chart':
        return create_multichart_layout()
    elif tab == 'performance':
        return create_performance_layout()
    elif tab == 'settings':
        return create_settings_layout()
    elif tab == 'logs':
        return create_logs_layout()

# Funkce pro získání obchodní historie z databáze
def get_trade_history(limit=10):
    """Získá historii obchodů z databáze"""
    try:
        conn = sqlite3.connect('data/trading_history.db', timeout=30)
        query = """
        SELECT timestamp, side, symbol, amount, entry_price, profit, market_type
        FROM trades
        ORDER BY timestamp DESC LIMIT ?"""
        
        df = pd.read_sql(query, conn, params=(limit,))
        conn.close()
        
        # Kontrola prázdného DataFrame
        if df.empty:
            return []
            
        return df.to_dict('records')
    except Exception as e:
        logger.error(f"Chyba při získávání obchodní historie: {str(e)}")
        return []

# Funkce pro získání equity křivky z databáze
def get_equity_data(days=7):
    try:
        conn = sqlite3.connect('data/trading_history.db')
        query = """
        SELECT timestamp, equity_value 
        FROM equity 
        WHERE timestamp >= datetime('now', '-{} days')
        ORDER BY timestamp
        """.format(days)
        df = pd.read_sql(query, conn)
        conn.close()
        
        # Pokud nemáme data, vytvoříme ukázková data
        if df.empty:
            start_date = datetime.now() - timedelta(days=days)
            dates = [start_date + timedelta(days=i) for i in range(days+1)]
            
            # Vygenerování hodnot pro ukázku
            initial_value = 1000.0
            values = [initial_value]
            for i in range(1, days+1):
                change = np.random.normal(0.002, 0.01)  # Průměrný denní růst 0.2%
                values.append(values[-1] * (1 + change))
            
            df = pd.DataFrame({
                'timestamp': dates,
                'equity_value': values
            })
            
            # Uložíme vygenerovaná data do databáze
            conn = sqlite3.connect('data/trading_history.db')
            for i in range(len(df)):
                try:
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO equity (timestamp, equity_value) VALUES (?, ?)",
                        (df['timestamp'][i], df['equity_value'][i])
                    )
                except:
                    pass  # Ignorujeme případné duplicity
            conn.commit()
            conn.close()
        
        return df
    except Exception as e:
        logger.error(f"Chyba při získávání equity dat: {str(e)}")
        return pd.DataFrame({'timestamp': [datetime.now()], 'equity_value': [1000.0]})
    
def create_equity_curve(market_type=None):
    """Vytvoří graf equity křivky na základě historických dat"""
    try:
        conn = sqlite3.connect('data/trading_history.db')
        # Odstraněn filtr podle market_type, který způsobuje chybu
        query = "SELECT timestamp, equity_value FROM equity ORDER BY timestamp ASC"
        df = pd.read_sql(query, conn, parse_dates=['timestamp'])
        conn.close()
        
        if df.empty:
            fig = go.Figure()
            fig.update_layout(title="Equity Curve - Žádná data", template='plotly_dark')
            return fig
            
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df['timestamp'], y=df['equity_value'], mode='lines', name='Equity'))
        fig.update_layout(title="Equity Curve", template='plotly_dark')
        return fig
        
    except Exception as e:
        logger.error(f"Chyba při vytváření equity křivky: {str(e)}")
        fig = go.Figure()
        fig.update_layout(title="Chyba při načítání dat", template='plotly_dark')
        return fig
 
def update_database_schema(conn=None):
    """Aktualizuje schéma databáze pro kompatibilitu s novějšími verzemi"""
    should_close = False
    if conn is None:
        conn = sqlite3.connect('data/trading_history.db')
        should_close = True
    
    cursor = conn.cursor()
    
    # Kontrola a přidání sloupce market_type do tabulky equity
    cursor.execute("PRAGMA table_info(equity)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'market_type' not in columns:
        logger.info("Přidávám chybějící sloupec market_type do tabulky equity")
        cursor.execute("ALTER TABLE equity ADD COLUMN market_type TEXT DEFAULT 'spot'")
        conn.commit()
    
    if should_close:
        conn.close()

def create_performance_gauge(metrics=None):
    """Vytvoří gauge graf pro vizualizaci výkonnosti"""
    try:
        # Získání denní změny, pokud není v metrics
        if not metrics:
            conn = sqlite3.connect('data/trading_history.db')
            query = """
            SELECT SUM(profit) as daily_profit
            FROM trades
            WHERE timestamp >= datetime('now', '-1 day')
            """
            df = pd.read_sql(query, conn)
            conn.close()
            daily_profit = df['daily_profit'].values[0] if not pd.isna(df['daily_profit'].values[0]) else 0
        else:
            daily_profit = metrics.get('daily_profit', 0)
        
        # Vytvoření gauge grafu
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=daily_profit,
            title={'text': "24h P&L"},
            gauge={
                'axis': {'range': [-100, 100]},
                'bar': {'color': "green" if daily_profit >= 0 else "red"},
                'steps': [
                    {'range': [-100, 0], 'color': "lightgray"},
                    {'range': [0, 100], 'color': "gray"}
                ],
                'threshold': {
                    'line': {'color': "white", 'width': 4},
                    'thickness': 0.75,
                    'value': 0
                }
            }
        ))
        
        fig.update_layout(
            template='plotly_dark',
            height=300,
            margin=dict(l=10, r=10, t=40, b=20)
        )
        
        return fig
        
    except Exception as e:
        logger.error(f"Chyba při vytváření performance gauge: {str(e)}")
        fig = go.Figure()
        fig.update_layout(title="Chyba při načítání dat", template='plotly_dark', height=300)
        return fig

def generate_trade_history_table(trades):
    """Vygeneruje tabulku obchodů pro zobrazení v dashboardu"""
    if not trades:
        return [html.Tr([html.Td("Zatím žádné obchody", colSpan=6)])]
        
    rows = []
    header = html.Tr([
        html.Th("Čas"), 
        html.Th("Typ"),
        html.Th("Pár"),
        html.Th("Množství"),
        html.Th("Cena"),
        html.Th("Zisk")
    ])
    rows.append(header)
    
    for trade in trades:
        timestamp = trade['timestamp']
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(trade['timestamp'])
        else:
            timestamp = datetime.strptime(trade['timestamp'], '%Y-%m-%dT%H:%M:%S.%f')
            
        rows.append(html.Tr([
            html.Td(timestamp),
            html.Td(trade['side'], style={'color': 'green' if trade['side'] == 'BUY' else 'red'}),
            html.Td(trade['symbol']),
            html.Td(f"{trade['amount']:.4f}"),
            html.Td(f"{trade['entry_price']:.2f}"),
            html.Td(f"{trade['profit']:.2f}", style={'color': 'green' if trade['profit'] > 0 else 'red'})
        ]))
    
    return rows

def calculate_performance_metrics(market_type=None):
    """Vypočítá výkonnostní metriky na základě historie obchodů"""
    try:
        conn = sqlite3.connect('data/trading_history.db')
        query = "SELECT profit FROM trades WHERE status = 'CLOSED'"
        params = []
        
        if market_type:
            query += " AND market_type = ?"
            params.append(market_type)
            
        df = pd.read_sql(query, conn, params=params)
        conn.close()
        
        total_trades = len(df)
        
        if total_trades == 0:
            return {
                'win_rate': 0,
                'profit_factor': 0,
                'total_trades': 0,
                'daily_profit': 0
            }
            
        win_trades = len(df[df['profit'] > 0])
        
        win_rate = (win_trades / total_trades) * 100 if total_trades > 0 else 0
        
        total_profit = df[df['profit'] > 0]['profit'].sum() if not df[df['profit'] > 0].empty else 0
        total_loss = abs(df[df['profit'] <= 0]['profit'].sum()) if not df[df['profit'] <= 0].empty else 1
        
        profit_factor = total_profit / total_loss if total_loss > 0 else total_profit
        
        # Pro gauge graf vypočítáme 24h profit
        conn = sqlite3.connect('data/trading_history.db')
        query = """
        SELECT SUM(profit) as daily_profit
        FROM trades
        WHERE timestamp >= datetime('now', '-1 day')
        """
        if market_type:
            query += " AND market_type = ?"
            params = [market_type]
        else:
            params = []
            
        daily_df = pd.read_sql(query, conn, params=params)
        conn.close()
        
        daily_profit = daily_df['daily_profit'].values[0] if not pd.isna(daily_df['daily_profit'].values[0]) else 0
        
        return {
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'total_trades': total_trades,
            'daily_profit': daily_profit
        }
        
    except Exception as e:
        logger.error(f"Chyba při výpočtu metrik: {str(e)}")
        return {
            'win_rate': 0,
            'profit_factor': 0,
            'total_trades': 0,
            'daily_profit': 0
        }

def update_charts(n, market_type):
    try:
        # Získání dat
        df = exchange.get_real_time_data('BTC/USDT')
        equity_df = pd.read_sql(
            "SELECT timestamp, equity_value FROM equity WHERE market_type = ?", 
            sqlite3.connect('data/trading_history.db'),
            params=[market_type]
        )
        
        # Vytvoření grafů
        price_fig = create_price_chart(df)
        equity_fig = create_equity_chart(equity_df)
        
        return price_fig, equity_fig
    except Exception as e:
        logging.error(f"Chyba v callbacku: {str(e)}")
        return go.Figure(), go.Figure()

def create_price_chart(df):
    fig = go.Figure()
    if df.empty:
        fig.add_trace(go.Candlestick(
            x=df['timestamp'],
            open=df['open'],
            high=df['high'],
            low=df['low'],
            close=df['close']
        ))
    fig.update_layout(template='plotly_dark')
    return fig

def create_equity_chart(df):
    fig = go.Figure()
    if df.empty:
        fig.add_trace(go.Scatter(
            x=df['timestamp'],
            y=df['equity_value'],
            mode='lines'
        ))
    fig.update_layout(template='plotly_dark')
    return fig

# Callback pro aktualizaci hlavního grafu a metrik
@app.callback(
    [Output('main-chart', 'figure'),
     Output('portfolio-value', 'children'),
     Output('daily-change', 'children'),
     Output('trade-history', 'children'),
     Output('equity-curve', 'figure'),
     Output('performance-gauge', 'figure'),
     Output('win-rate', 'children'),
     Output('profit-factor', 'children'),
     Output('total-trades', 'children')],
    [Input('update-interval', 'n_intervals'),
     Input('timeframe-selector', 'value'),
     Input('asset-selector', 'value'),
     Input('market-type-selector', 'value')]
)
def update_dashboard(n_intervals, timeframe, asset, market_type):
    try:
        # Kontrola povinných parametrů
        if None in (timeframe, asset, market_type):
            raise ValueError("Nebyly vybrány všechny parametry")
        
        # Získání dat
        raw_data = exchange.get_real_time_data(
            symbol=asset,
            timeframe=timeframe,
            market_type=market_type
        )
        
        # Zpracování dat
        df = pd.DataFrame(raw_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        
        # Výpočet indikátorů
        df['sma20'] = df['close'].rolling(20).mean()
        df['sma50'] = df['close'].rolling(50).mean()
        
        # Vytvoření grafu
        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=df['timestamp'],
            open=df['open'],
            high=df['high'],
            low=df['low'],
            close=df['close'],
            name='Candles'
        ))
        fig.update_layout(
            title=f'{asset} - {timeframe}',
            template='plotly_dark',
            height=400
        )
        
        # Získání dalších dat
        portfolio = exchange.get_portfolio_value(market_type)
        change = exchange.get_24h_change(asset, market_type)
        
        # Získání historie obchodů
        trades = get_trade_history()
        
        # Vytvoření kompletní odpovědi
        return (
            fig,
            f"{portfolio:.2f} USDT",
            f"{change:.2f}%",
            generate_trade_table(trades),
            create_equity_curve(),
            create_performance_gauge(),
            "75.5%",  # Demo hodnoty
            "1.25", 
            "42"
        )
        
    except Exception as e:
        logger.error(f"Chyba: {str(e)}")
        return get_fallback_values()

def get_fallback_values():
    """Vrátí výchozí hodnoty v případě chyby"""
    empty_fig = go.Figure()
    empty_fig.update_layout(
        title="Data nejsou dostupná",
        template='plotly_dark'
    )
    
    return (
        empty_fig,  # main-chart
        "N/A",      # portfolio-value
        "N/A",      # daily-change
        [],         # trade-history
        empty_fig,  # equity-curve
        empty_fig,  # performance-gauge
        "N/A",      # win-rate
        "N/A",      # profit-factor
        "N/A"       # total-trades
    )


def generate_trade_table(trades):
    if not trades:
        return [html.Tr([html.Td("Žádné obchody", colSpan=6)])]
    
    return [
        html.Tr([
            html.Td(trade['timestamp']),
            html.Td(trade['side'], style={'color': 'green' if trade['side'] == 'BUY' else 'red'}),
            html.Td(trade['symbol']),
            html.Td(f"{trade['amount']:.4f}"),
            html.Td(f"{trade['entry_price']:.2f}"),
            html.Td(f"{trade['profit']:.2f}", style={'color': 'green' if trade['profit'] > 0 else 'red'})
        ]) for trade in trades
    ]

# Callback pro Multi-Chart záložku
@app.callback(
    Output('multi-chart-container', 'children'),
    [Input('update-interval', 'n_intervals'),
     Input('multi-chart-pairs', 'value'),
     Input('multi-chart-timeframe', 'value'),
     Input('multi-chart-market-type', 'value')]
)
def update_multi_charts(_, pairs, timeframe, market_type):
    if not pairs:
        return html.Div("Please select at least one pair", style={'color': 'white'})
    
    charts = []
    
    for pair in pairs:
        try:
            # Získání dat
            raw_data = exchange.get_real_time_data(symbol=pair, timeframe=timeframe, market_type=market_type)
            
            # Zpracování dat
            df = pd.DataFrame(raw_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            
            # Výpočet EMA
            df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
            
            # Vytvoření grafu
            fig = go.Figure()
            
            fig.add_trace(go.Candlestick(
                x=df.index,
                open=df['open'],
                high=df['high'],
                low=df['low'],
                close=df['close'],
                name='Price',
                showlegend=False
            ))
            
            fig.add_trace(go.Scatter(
                x=df.index,
                y=df['ema20'],
                line=dict(color='#00ffff', width=1),
                name='EMA 20',
                showlegend=False
            ))
            
            # Layout grafu
            fig.update_layout(
                title=f"{pair} ({market_type})",
                height=300,
                plot_bgcolor='#1e1e1e',
                paper_bgcolor='#1e1e1e',
                font=dict(color='white', size=10),
                margin=dict(l=10, r=10, t=30, b=10),
                xaxis_rangeslider_visible=False
            )
            
            # Přidání grafu do seznamu
            charts.append(
                html.Div([
                    dcc.Graph(figure=fig, style={'height': '100%'})
                ], style={'height': '300px'})
            )
            
        except Exception as e:
            logger.error(f"Chyba při vytváření grafu pro {pair}: {str(e)}")
            charts.append(
                html.Div([
                    html.H4(pair, style={'color': 'white'}),
                    html.Div(f"Error loading data: {str(e)}", style={'color': '#ff5555'})
                ], style={'height': '300px', 'background-color': '#1e1e1e', 'padding': '10px'})
            )
    
    return charts

# Callback pro performance comparison tabulku
@app.callback(
    Output('performance-table', 'children'),
    [Input('slow-update-interval', 'n_intervals'),
     Input('multi-chart-pairs', 'value'),
     Input('multi-chart-market-type', 'value')]
)
def update_performance_table(_, pairs, market_type):
    if not pairs:
        return [html.Tr([html.Td("No pairs selected", colSpan=5)])]
    
    # Header tabulky
    table_rows = [html.Tr([
        html.Th("Pair"), 
        html.Th("Current Price"),
        html.Th("24h Change"),
        html.Th("Volume (USDT)"),
        html.Th("Signal")
    ])]
    
    for pair in pairs:
        try:
            current_price = exchange.get_current_price(pair, market_type=market_type)
            daily_change = exchange.get_24h_change(pair, market_type=market_type)
            
            # Získání posledního signálu z databáze
            conn = sqlite3.connect('data/trading_history.db')
            cursor = conn.cursor()
            cursor.execute("""
                SELECT signal FROM decisions 
                WHERE symbol = ? AND market_type = ?
                ORDER BY timestamp DESC 
                LIMIT 1
            """, (pair, market_type))
            result = cursor.fetchone()
            signal = result[0] if result else "HOLD"
            conn.close()
            
            # Barva pro signál
            signal_color = 'green' if signal == 'BUY' else ('red' if signal == 'SELL' else '#ffcc00')
            
            # Objem - buď z API nebo zpracovaný objem
            volume = exchange.get_24h_volume(pair, market_type=market_type)
            
            # Přidání řádku do tabulky
            table_rows.append(html.Tr([
                html.Td(pair),
                html.Td(f"{current_price:.2f}$"),
                html.Td(f"{daily_change:.2f}%", style={'color': 'green' if daily_change >= 0 else 'red'}),
                html.Td(f"{volume/1e6:.2f}M"),
                html.Td(signal, style={'color': signal_color})
            ]))
            
        except Exception as e:
            logger.error(f"Chyba při získávání dat pro {pair}: {str(e)}")
            table_rows.append(html.Tr([
                html.Td(pair),
                html.Td("Error", colSpan=4, style={'color': '#ff5555'})
            ]))
    
    return table_rows

# Callback pro záložku Performance
@app.callback(
    [Output('pnl-chart', 'figure'),
     Output('total-profit', 'children'),
     Output('detailed-win-rate', 'children'),
     Output('detailed-profit-factor', 'children'),
     Output('max-drawdown', 'children'),
     Output('trade-distribution', 'figure'),
     Output('profit-distribution', 'figure')],
    [Input('slow-update-interval', 'n_intervals'),
     Input('performance-timerange', 'value'),
     Input('performance-pair', 'value'),
     Input('performance-market-type', 'value')]
)
def update_performance_analytics(_, time_range, pair, market_type):
    try:
        # Sestavení filtru SQL dotazu
        conditions = []
        params = []
        
        # Filtr podle času
        if time_range == 'today':
            conditions.append("timestamp >= date('now')")
        elif time_range == '7days':
            conditions.append("timestamp >= date('now', '-7 days')")
        elif time_range == '30days':
            conditions.append("timestamp >= date('now', '-30 days')")
        
        # Filtr podle páru
        if pair != 'all':
            conditions.append("symbol = ?")
            params.append(pair)
        
        # Filtr podle typu trhu
        if market_type != 'all':
            conditions.append("market_type = ?")
            params.append(market_type)
        
        # Sestavení WHERE klauzule
        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)
        
        # Získání dat z databáze
        conn = sqlite3.connect('data/trading_history.db')
        
        # Získání seznamu obchodů
        query = f"""
        SELECT timestamp, symbol, side, amount, entry_price, exit_price, profit, market_type
        FROM trades
        {where_clause}
        ORDER BY timestamp
        """
        trades_df = pd.read_sql(query, conn, params=params, parse_dates=['timestamp'])
        
        # Pokud nemáme data, vytvoříme ukázková data
        if trades_df.empty:
            # Vytvoření ukázkových obchodů
            np.random.seed(42)  # Pro konzistenci
            
            start_date = datetime.now() - timedelta(days=30)
            dates = [start_date + timedelta(hours=i*8) for i in range(20)]
            
            symbols = [pair] if pair != 'all' else np.random.choice(['BNB/USDT', 'BTC/USDT', 'ETH/USDT'], 20)
            sides = np.random.choice(['BUY', 'SELL'], 20)
            amounts = np.random.uniform(0.1, 1.0, 20)
            
            entry_prices = np.random.uniform(100, 500, 20)
            exit_prices = [price * (1 + np.random.normal(0.01, 0.05)) for price in entry_prices]
            profits = [(exit_prices[i] - entry_prices[i]) * amounts[i] for i in range(20)]
            market_types = [market_type] if market_type != 'all' else np.random.choice(['spot', 'futures'], 20)
            
            trades_df = pd.DataFrame({
                'timestamp': dates,
                'symbol': symbols,
                'side': sides,
                'amount': amounts,
                'entry_price': entry_prices,
                'exit_price': exit_prices,
                'profit': profits,
                'market_type': market_types
            })
            
            # Uložení ukázkových dat do databáze
            for _, trade in trades_df.iterrows():
                try:
                    cursor = conn.cursor()
                    cursor.execute("""
                    INSERT INTO trades (timestamp, symbol, side, amount, entry_price, exit_price, profit, status, market_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        trade['timestamp'], 
                        trade['symbol'], 
                        trade['side'], 
                        trade['amount'], 
                        trade['entry_price'], 
                        trade['exit_price'], 
                        trade['profit'],
                        'CLOSED',
                        trade['market_type']
                    ))
                except:
                    pass  # Ignorujeme duplicity
            
            conn.commit()
        
        conn.close()
        
        # Výpočet kumulativního P&L
        trades_df['cumulative_pnl'] = trades_df['profit'].cumsum()
        
        # Vytvoření P&L grafu
        pnl_fig = go.Figure()
        
        pnl_fig.add_trace(go.Scatter(
            x=trades_df['timestamp'],
            y=trades_df['cumulative_pnl'],
            mode='lines',
            fill='tozeroy',
            line=dict(color='#00ff88' if trades_df['cumulative_pnl'].iloc[-1] >= 0 else '#ff5555', width=2),
            fillcolor='rgba(0, 255, 136, 0.1)' if trades_df['cumulative_pnl'].iloc[-1] >= 0 else 'rgba(255, 85, 85, 0.1)'
        ))
        
        pnl_fig.update_layout(
            title=f"Cumulative Profit & Loss ({market_type})",
            xaxis_title="Date",
            yaxis_title="Profit/Loss (USDT)",
            plot_bgcolor='#1e1e1e',
            paper_bgcolor='#1e1e1e',
            font=dict(color='white'),
            margin=dict(l=20, r=20, t=40, b=20)
        )
        
        # Výpočet metrik
        total_profit = trades_df['profit'].sum()
        win_trades = trades_df[trades_df['profit'] > 0]
        lose_trades = trades_df[trades_df['profit'] <= 0]
        
        win_rate = len(win_trades) / len(trades_df) * 100 if len(trades_df) > 0 else 0
        
        profit_factor = abs(win_trades['profit'].sum() / lose_trades['profit'].sum()) if len(lose_trades) > 0 and lose_trades['profit'].sum() != 0 else float('inf')
        
        # Výpočet maximálního drawdownu
        cumulative = trades_df['cumulative_pnl'].values
        max_drawdown = 0
        peak = cumulative[0]
        
        for value in cumulative[1:]:
            if value > peak:
                peak = value
            drawdown = peak - value
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        # Rozdělení obchodů podle symbolu
        trade_distribution = trades_df['symbol'].value_counts()
        
        trade_dist_fig = go.Figure()
        trade_dist_fig.add_trace(go.Bar(
            x=trade_distribution.index,
            y=trade_distribution.values,
            marker_color='#00ffff'
        ))
        
        trade_dist_fig.update_layout(
            title="Trades by Symbol",
            xaxis_title="Symbol",
            yaxis_title="Number of Trades",
            plot_bgcolor='#1e1e1e',
            paper_bgcolor='#1e1e1e',
            font=dict(color='white'),
            margin=dict(l=20, r=20, t=40, b=20)
        )
        
        # Rozdělení profitů
        profit_bins = [-float('inf'), -50, -20, -5, 0, 5, 20, 50, float('inf')]
        profit_labels = ['< -50', '-50 to -20', '-20 to -5', '-5 to 0', '0 to 5', '5 to 20', '20 to 50', '> 50']
        
        trades_df['profit_category'] = pd.cut(
            trades_df['profit'], 
            bins=profit_bins, 
            labels=profit_labels, 
            right=False
        )
        
        profit_counts = trades_df['profit_category'].value_counts().reindex(profit_labels)
        
        profit_dist_fig = go.Figure()
        
        # Barvy podle kategorií zisku/ztráty
        bar_colors = ['#ff0000', '#ff5555', '#ff9999', '#ffcccc', 
                      '#ccffcc', '#99ff99', '#55ff55', '#00ff00']
        
        profit_dist_fig.add_trace(go.Bar(
            x=profit_counts.index,
            y=profit_counts.values,
            marker_color=bar_colors
        ))
        
        profit_dist_fig.update_layout(
            title="Profit Distribution",
            xaxis_title="Profit/Loss (USDT)",
            yaxis_title="Number of Trades",
            plot_bgcolor='#1e1e1e',
            paper_bgcolor='#1e1e1e',
            font=dict(color='white'),
            margin=dict(l=20, r=20, t=40, b=20)
        )
        
        return (
            pnl_fig, 
            f"{total_profit:.2f} USDT", 
            f"{win_rate:.1f}%", 
            f"{profit_factor:.2f}", 
            f"{max_drawdown:.2f} USDT",
            trade_dist_fig,
            profit_dist_fig
        )
        
    except Exception as e:
        logger.error(f"Chyba při aktualizaci analýzy výkonu: {str(e)}")
        logger.error(traceback.format_exc())
        
        # Vytvoření prázdných grafů v případě chyby
        empty_fig = go.Figure()
        empty_fig.update_layout(
            title="No data available",
            plot_bgcolor='#1e1e1e',
            paper_bgcolor='#1e1e1e',
            font=dict(color='white')
        )
        
        return (
            empty_fig, "0.00 USDT", "0.0%", "0.0", "0.00 USDT", empty_fig, empty_fig
        )

# Callback pro aktualizaci logů
@app.callback(
    Output('bot-logs', 'children'),
    [Input('update-interval', 'n_intervals'),
     Input('log-level-filter', 'value'),
     Input('log-search', 'value'),
     Input('log-market-type', 'value')]
)
def update_logs(_, log_level, search_text, market_type):
    try:
        # Načtení logů ze souboru
        log_file = 'logs/trading_bot.log'
        if not os.path.exists(log_file):
            return html.Div("No logs available", style={'color': '#888888'})
        
        with open(log_file, 'r', encoding='utf-8') as f:
            log_lines = f.readlines()
        
        # Filtrování podle úrovně
        if log_level != 'all':
            filtered_lines = [line for line in log_lines if f" - {log_level.upper()} - " in line]
        else:
            filtered_lines = log_lines
        
        # Filtrování podle textu
        if search_text:
            filtered_lines = [line for line in filtered_lines if search_text.lower() in line.lower()]
            
        # Filtrování podle typu trhu
        if market_type != 'all':
            filtered_lines = [line for line in filtered_lines if f"{market_type.upper()}" in line]
        
        # Omezení na posledních 100 řádků
        filtered_lines = filtered_lines[-100:]
        
        # Vytvoření log entries
        log_entries = []
        
        for line in filtered_lines:
            style = {'margin-bottom': '5px'}
            
            if " - ERROR - " in line:
                style['color'] = '#ff5555'
                log_class = "log-error"
            elif " - WARNING - " in line:
                style['color'] = '#ffcc00'
                log_class = "log-warning"
            else:
                style['color'] = '#00ff88'
                log_class = "log-info"
            
            log_entries.append(html.Div(
                line,
                className=f"log-entry {log_class}",
                style=style
            ))
        
        if not log_entries:
            log_entries = [html.Div("No logs matching your criteria", style={'color': '#888888'})]
        
        return log_entries
        
    except Exception as e:
        logger.error(f"Chyba při aktualizaci logů: {str(e)}")
        return html.Div(f"Error loading logs: {str(e)}", style={'color': '#ff5555'})

# Callback pro zobrazení aktivních pozic
@app.callback(
    Output('active-positions', 'children'),
    [Input('update-interval', 'n_intervals'),
     Input('log-market-type', 'value')]
)
def update_active_positions(_, market_type):
    try:
        # Vytvoření SQL dotazu s filtrem podle typu trhu
        query = "SELECT * FROM active_positions"
        params = []
        
        if market_type != 'all':
            query += " WHERE market_type = ?"
            params.append(market_type)
            
        # Získání dat z databáze
        conn = sqlite3.connect('data/trading_history.db')
        active_positions = pd.read_sql(query, conn, params=params)
        conn.close()
        
        # Header tabulky
        table_rows = [html.Tr([
            html.Th("Open Time"), 
            html.Th("Pair"),
            html.Th("Type"),
            html.Th("Market"),
            html.Th("Amount"),
            html.Th("Entry Price"),
            html.Th("Current P/L"),
            html.Th("SL/TP"),
            html.Th("Actions")
        ])]
        
        if active_positions.empty:
            table_rows.append(html.Tr([html.Td("No active positions", colSpan=9)]))
            return table_rows
        
        # Přidání řádků do tabulky
        for _, position in active_positions.iterrows():
            # Získání aktuální ceny
            current_price = exchange.get_current_price(position['symbol'], market_type=position['market_type'])
            
            # Výpočet P/L
            if position['direction'] == 'LONG':
                pnl = (current_price - position['entry_price']) * position['amount']
            else:  # SHORT
                pnl = (position['entry_price'] - current_price) * position['amount']
            
            # Formátování P/L
            pnl_color = 'green' if pnl >= 0 else 'red'
            
            # Přidání tlačítka pro uzavření pozice pro adminy
            close_button = html.Button(
                "Close", 
                id={'type': 'close-position-btn', 'index': position['id']},
                className="control-btn",
                style={'background-color': '#ff5555', 'display': 'block' if current_user.role == 'admin' else 'none'}
            )
            
            # Přidání řádku do tabulky
            table_rows.append(html.Tr([
                html.Td(str(position['timestamp'])),
                html.Td(position['symbol']),
                html.Td(position['direction'], style={'color': 'green' if position['direction'] == 'LONG' else 'red'}),
                html.Td(position['market_type'].upper()),
                html.Td(f"{position['amount']}"),
                html.Td(f"{position['entry_price']:.2f}"),
                html.Td(f"{pnl:.2f} USDT", style={'color': pnl_color}),
                html.Td(f"SL: {position['stop_loss']:.2f} / TP: {position['take_profit']:.2f}"),
                html.Td(close_button)
            ]))
        
        return table_rows
        
    except Exception as e:
        logger.error(f"Chyba při aktualizaci aktivních pozic: {str(e)}")
        return [html.Tr([html.Td(f"Error loading positions: {str(e)}", colSpan=9)])]

# Callback pro zobrazení rozhodnutí bota
@app.callback(
    Output('bot-decisions', 'children'),
    [Input('update-interval', 'n_intervals'),
     Input('log-market-type', 'value')]
)
def update_bot_decisions(_, market_type):
    try:
        # Sestavení SQL dotazu s filtrem podle typu trhu
        query = """
        SELECT timestamp, symbol, signal, confidence, action_taken, market_type 
        FROM decisions 
        """
        
        params = []
        if market_type != 'all':
            query += "WHERE market_type = ? "
            params.append(market_type)
            
        query += "ORDER BY timestamp DESC LIMIT 10"
        
        # Získání dat z databáze
        conn = sqlite3.connect('data/trading_history.db')
        decisions = pd.read_sql(query, conn, params=params)
        conn.close()
        
        # Header tabulky
        table_rows = [html.Tr([
            html.Th("Time"), 
            html.Th("Pair"),
            html.Th("Market"),
            html.Th("Decision"),
            html.Th("Confidence"),
            html.Th("Action Taken")
        ])]
        
        if decisions.empty:
            table_rows.append(html.Tr([html.Td("No decisions recorded", colSpan=6)]))
            return table_rows
        
        # Přidání řádků do tabulky
        for _, decision in decisions.iterrows():
            # Barvy pro rozhodnutí
            if decision['signal'] == 'BUY':
                decision_color = 'green'
            elif decision['signal'] == 'SELL':
                decision_color = 'red'
            else:
                decision_color = '#ffcc00'
            
            # Přidání řádku do tabulky
            table_rows.append(html.Tr([
                html.Td(str(decision['timestamp'])),
                html.Td(decision['symbol']),
                html.Td(decision['market_type'].upper()),
                html.Td(decision['signal'], style={'color': decision_color}),
                html.Td(f"{decision['confidence']:.2f}"),
                html.Td(decision['action_taken'])
            ]))
        
        return table_rows
        
    except Exception as e:
        logger.error(f"Chyba při aktualizaci rozhodnutí bota: {str(e)}")
        return [html.Tr([html.Td(f"Error loading decisions: {str(e)}", colSpan=6)])]


# Callback pro přidání nového uživatele
@app.callback(
    Output('user-management-message', 'children'),
    [Input('add-user-btn', 'n_clicks')],
    [State('new-username', 'value'),
     State('new-password', 'value'),
     State('new-user-role', 'value')]
)
def add_user(n_clicks, username, password, role):
    if not n_clicks or not current_user.is_authenticated or current_user.role != 'admin':
        return ""
    
    if not username or not password:
        return "Uživatelské jméno a heslo jsou povinné"
    
    if username in users_db:
        return "Uživatel s tímto jménem již existuje"
    
    # Přidání nového uživatele
    users_db[username] = {
        'password': generate_password_hash(password),
        'role': role
    }
    
    return f"Uživatel {username} byl úspěšně přidán s rolí {role}"

# ui/web_app.py (část s AI informacemi)
def create_ai_metrics():
    return html.Div([
        html.H3("AI Engine Metrics", className="ai-header"),
        dcc.Graph(id='ai-performance-chart'),
        html.Div([
            html.Div([
                html.Span("Current Strategy: "),
                html.Span(id='current-strategy', className='ai-value')
            ], className='ai-metric'),
            html.Div([
                html.Span("Model Accuracy: "),
                html.Span(id='model-accuracy', className='ai-value')
            ], className='ai-metric'),
            html.Div([
                html.Span("Prediction Confidence: "),
                html.Span(id='prediction-confidence', className='ai-value')
            ], className='ai-metric'),
            dcc.Markdown('''
                **Matematický model:**
                ```
                P(y=1|x) = \frac{1}{1 + e^{-(w^T x + b)}}
                ```
                **Feature Engineering:**
                - Normalizovaný OHLC
                - Technické indikátory (RSI, MACD)
                - Fourierova transformace
            ''', className='ai-formulas')
        ], className='ai-metrics-container')
    ], className="ai-panel")



def ensure_api_connection():
    """Ověří a obnoví připojení k API"""
    global exchange
    
    try:
        # Test připojení
        exchange.client.fetch_status()
        return True
    except Exception as e:
        logger.error(f"Ztraceno spojení s API: {str(e)}")
        
        # Pokus o obnovení připojení
        try:
            exchange = BinanceConnector(load_config())
            logger.info("Připojení k API obnoveno")
            return True
        except Exception as reconnect_error:
            logger.critical(f"Nelze obnovit připojení: {str(reconnect_error)}")
            return False
        
def backup_database():
    if os.path.exists('data/trading_history.db'):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f'data/backup/trading_history_{timestamp}.db'
        os.makedirs('data/backup', exist_ok=True)
        import shutil
        shutil.copy2('data/trading_history.db', backup_path)
        logger.info(f"Vytvořena záloha databáze: {backup_path}")


# Spuštění serveru
if __name__ == "__main__":
    init_database()
    update_database_schema()  # Volat před import_exchange_data()
    import_exchange_data()
    logger.info("Inicializace dokončena. Databáze je připravena k použití.")
    app.run(debug=True)
