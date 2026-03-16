import nbformat as nbf
import os

def update_ev_diagnosis(path):
    with open(path, 'r', encoding='utf-8') as f:
        nb = nbf.read(f, as_version=4)

    # 1. Update Imports
    import_cell = nb.cells[1]
    if 'from qtrader.ml.evaluation import ModelEvaluator' not in import_cell['source']:
        import_cell['source'] += "\nfrom qtrader.ml.evaluation import ModelEvaluator\nfrom qtrader.ml.regime import RegimeDetector"

    # 2. Add ML Section
    ml_cells = [
        nbf.v4.new_markdown_cell("## 5. ML-Powered Deep Diagnosis\\nQuantitative evaluation of signal quality and market regimes."),
        nbf.v4.new_code_cell("""# 1. Compute Signal information Coefficient (IC)
evaluator = ModelEvaluator()
df_eval = candles.to_pandas()
df_eval['returns'] = df_eval['close'].pct_change().shift(-1)
# Signal: 1 if fast > slow else -1
df_eval['signal'] = (df_eval['close'].ewm(span=50).mean() > df_eval['close'].ewm(span=200).mean()).astype(int).replace(0, -1)
df_eval = df_eval.dropna()

ic = evaluator.compute_ic(df_eval['signal'], df_eval['returns'])
print(f"Signal Information Coefficient (IC): {ic:.4f}")

# Rolling IC
rolling_ic = evaluator.rolling_ic(df_eval.rename(columns={'signal': 'predicted', 'returns': 'realized'}), window=100)
fig = px.line(x=df_eval['timestamp'], y=rolling_ic, title="Signal Quality (Rolling 100-bar IC)")
fig.show()"""),
        nbf.v4.new_code_cell("""# 2. Market Regime Analysis
detector = RegimeDetector(n_regimes=3, method='gmm')
# Use returns and volatility as features
df_eval['vol'] = df_eval['close'].pct_change().rolling(20).std()
df_eval = df_eval.dropna()

feature_cols = ['returns', 'vol']
detector.fit(pl.from_pandas(df_eval), feature_cols)
regimes = detector.predict_regime(pl.from_pandas(df_eval), feature_cols)

stats = detector.get_regime_stats(pl.from_pandas(df_eval), regimes)
print("Market Regime Statistics:")
print(stats)

# Visualize Regimes
fig = px.scatter(df_eval, x='timestamp', y='close', color=regimes.to_numpy().astype(str), 
                 title="ETH-USD Price Colored by Market Regime")
fig.show()""")
    ]
    
    nb.cells.extend(ml_cells)
    
    with open(path, 'w', encoding='utf-8') as f:
        nbf.write(nb, f)
    print(f"Updated {path}")

def update_strategy_lab(path):
    with open(path, 'r', encoding='utf-8') as f:
        nb = nbf.read(f, as_version=4)

    # 1. Update Imports
    import_cell = nb.cells[1]
    if 'from qtrader.ml.regime import RegimeDetector' not in import_cell['source']:
        import_cell['source'] += "\nfrom qtrader.ml.regime import RegimeDetector"

    # 2. Add regime-filtered strategy function
    new_strategy_cell = nbf.v4.new_code_cell("""
def run_ml_filtered_strategy(df: pd.DataFrame) -> tuple:
    df_ml = df.copy()
    
    # 1. Detect Regime
    detector = RegimeDetector(n_regimes=3, method='gmm')
    # Use returns and vol to detect bull/bear/sideways
    df_ml['ret'] = df_ml['close'].pct_change()
    df_ml['vol'] = df_ml['close'].pct_change().rolling(50).std()
    df_ml_clean = df_ml.dropna()
    
    feature_cols = ['ret', 'vol']
    detector.fit(pl.from_pandas(df_ml_clean), feature_cols)
    regimes = detector.predict_regime(pl.from_pandas(df_ml_clean), feature_cols)
    
    # Join regimes back to df_ml
    df_ml_clean = df_ml_clean.with_columns(regimes.alias('regime'))
    df_ml = df_ml.join(pl.from_pandas(df_ml_clean[['timestamp', 'regime']]), on='timestamp', how='left').to_pandas()
    
    # Identify Bull Regime (highest mean return)
    stats = detector.get_regime_stats(pl.from_pandas(df_ml_clean), regimes)
    bull_regime = stats.sort('avg_return').tail(1)['regime'].item()
    
    # 2. Run Baseline strategy but ONLY in Bull Regime
    df_ml['ema_fast'] = df_ml['close'].ewm(span=50, adjust=False).mean()
    df_ml['ema_slow'] = df_ml['close'].ewm(span=200, adjust=False).mean()
    
    engine = PaperTradingEngine(starting_capital=CAPITAL, fee_rate=FEE_RATE)
    holding = False
    
    for i in range(200, len(df_ml)-1):
        row = df_ml.iloc[i]
        prev_row = df_ml.iloc[i-1]
        next_open = float(df_ml.iloc[i+1]["open"])
        
        # ML FILTER: Only trade if in Bull Regime
        regime_ok = (row['regime'] == bull_regime)
        
        market_state = {"bid": next_open, "ask": next_open, "top_depth": 50.0, "venue": "Coinbase_ADV"}

        signal_buy = (prev_row['ema_fast'] <= prev_row['ema_slow']) and (row['ema_fast'] > row['ema_slow'])
        signal_sell = (prev_row['ema_fast'] >= prev_row['ema_slow']) and (row['ema_fast'] < row['ema_slow'])

        if not holding and signal_buy and regime_ok:
            qty = round((CAPITAL * 0.10) / next_open, 4)
            entry_event = OrderEvent(symbol=SYMBOL, order_type="MARKET", side="BUY", quantity=qty, price=next_open)
            engine.simulate_fill(entry_event, market_state)
            holding = True
        elif holding and (signal_sell or not regime_ok): # Exit if signal flips or regime changes
            exit_event = OrderEvent(symbol=SYMBOL, order_type="MARKET", side="SELL", quantity=qty, price=next_open)
            engine.simulate_fill(exit_event, market_state)
            holding = False

    calc = EVCalculator(engine.closed_trades, fee_rate=FEE_RATE)
    return calc.diagnose(SYMBOL, min_trades=50), engine.closed_trades

ml_report, ml_trades = run_ml_filtered_strategy(df)
print(f"ML-Filtered EV per trade: {ml_report.ev_per_trade:.6f}")
""")

    # Find position to insert (after confluence strategy)
    nb.cells.insert(13, nbf.v4.new_markdown_cell("## 3.5 ML-Filtered Strategy\\nAdding a Regime Detector to the baseline to filter out non-trending environments."))
    nb.cells.insert(14, new_strategy_cell)
    
    # Update Comparison table cell
    found_comp = False
    for cell in nb.cells:
        if cell['cell_type'] == 'code' and 'comparison = pd.DataFrame({' in cell['source']:
            cell['source'] = cell['source'].replace(
                '"Confluence": [',
                '"ML-Filtered": [\\n'
                '        ml_report.total_trades,\\n'
                '        f"{ml_report.win_rate:.2%}",\\n'
                '        f"{ml_report.ev_per_trade:.4f}",\\n'
                '        f"± {ml_report.ev_confidence_interval:.4f}",\\n'
                '        f"{ml_report.profit_factor:.2f}",\\n'
                '        f"{ml_report.sharpe_ratio:.2f}",\\n'
                '        f"{ml_report.sortino_ratio:.2f}",\\n'
                '        f"{ml_report.calmar_ratio:.2f}" if ml_report.calmar_ratio != float("inf") else "INF",\\n'
                '        f"{ml_report.payoff_ratio:.2f}",\\n'
                '        f"{ml_report.break_even_win_rate:.2%}",\\n'
                '        f"{ml_report.cost_to_profit_ratio:.2%}",\\n'
                '        ml_report.status\\n'
                '    ],\\n    "Confluence": ['
            )
            found_comp = True
            break
    
    if not found_comp:
        print("Warning: Comparison cell not found in 06_Strategy_Lab.ipynb")

    with open(path, 'w', encoding='utf-8') as f:
        nbf.write(nb, f)
    print(f"Updated {path}")

if __name__ == "__main__":
    update_ev_diagnosis('/Users/hoangnam/qtrader/notebooks/trader/05_EV_Diagnosis.ipynb')
    update_strategy_lab('/Users/hoangnam/qtrader/notebooks/trader/06_Strategy_Lab.ipynb')
