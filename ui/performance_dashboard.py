# ui/performance_dashboard.py
import dash
from dash import dcc, html, Input, Output
import plotly.express as px
import pandas as pd

def create_dashboard(app):
    app.layout = html.Div([
        dcc.Interval(id='update-interval', interval=60*1000),
        html.H1("Obchodní Performance"),
        dcc.Graph(id='equity-curve'),
        html.Div([
            html.Div([
                html.H3("Sharpe Ratio"),
                html.Div(id='sharpe-ratio')
            ], className='metric-box'),
            html.Div([
                html.H3("Win Rate"),
                html.Div(id='win-rate')
            ], className='metric-box')
        ], className='metrics-container')
    ])

    @app.callback(
        [Output('equity-curve', 'figure'),
         Output('sharpe-ratio', 'children'),
         Output('win-rate', 'children')],
        [Input('update-interval', 'n_intervals')]
    )
    def update_metrics(n):
        df = pd.read_csv('logs/trade_history.log', parse_dates=['timestamp'])
        # Výpočet metrik
        return (
            px.line(df, x='timestamp', y='cumulative_profit'),
            f"{calculate_sharpe(df):.2f}",
            f"{calculate_win_rate(df):.1%}"
        )
