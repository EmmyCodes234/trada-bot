TRADA AI TRADING AGENT -- MT5 SETUP GUIDE
=========================================
Powered by OpenModel.ai

1. GET AN OPENMODEL API KEY
   - Sign up at https://console.openmodel.ai
   - Create an API key
   - Recommended: gpt-4o (or deepseek-chat for affordable alternative)

2. INSTALL THE EA
   - Copy TradaEA.mq5 and json.mqh to:
     C:\Users\<YOUR_USER>\AppData\Roaming\MetaQuotes\Terminal\<INSTANCE_ID>\MQL5\Experts\Trada\
   - Open MetaEditor (F4), compile TradaEA.mq5

3. CONFIGURE MT5 FOR WEBREQUEST
   - MT5 > Tools > Options > Expert Advisors tab
   - Check "Allow WebRequest for listed URLs"
   - Add: https://api.openmodel.ai
   - OK

4. ATTACH TO A CHART
   - Drag TradaEA onto any chart
   - Common tab: check "Allow Algo Trading", "Allow Live Trading"
   - Inputs tab:
     * InpAPIKey = your OpenModel key
     * Start with InpEnableTrading = false (dry-run mode)
     * InpAnalysisHour = server hour for daily analysis
     * Adjust InpMinConfidence, InpMaxDailyTrades, InpRiskPct

5. TEST ON DEMO FIRST
   - Open a demo account
   - Watch the Experts tab (Ctrl+T > Experts) for [SIGNAL] output
   - Set InpEnableTrading = true when ready

6. AVAILABLE MODELS
   - gpt-4o (best)  |  deepseek-chat (cheapest)
   - claude-sonnet-4-20250514  |  gemini-2.0-flash
   - qwen3-max  |  (see openmodel.ai for full list)

HOW IT WORKS
============
- Every new bar at configured hour, collects 30 bars of data
- Sends market summary (price, SMA7/21, volume, spread) to OpenModel
- AI returns {signal, confidence, risk, stop_loss, take_profit}
- If signal is BUY/SELL with confidence >= InpMinConfidence:
  - Opens position with risk-based lot sizing
  - Sets SL and TP per AI recommendation
  - Respects daily trade limits
