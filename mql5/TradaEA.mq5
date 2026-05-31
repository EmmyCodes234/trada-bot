//+------------------------------------------------------------------+
//|                                              Trada Trading Agent |
//|                                      Powered by OpenModel.ai AI |
//+------------------------------------------------------------------+
#property copyright "Trada"
#property version   "1.00"

#include <Trade/Trade.mqh>
#include "json.mqh"

//+------------------------------------------------------------------+
//| Input parameters                                                 |
//+------------------------------------------------------------------+
input string InpAPIKey         = "your-api-key-here";
input string InpModel          = "gpt-4o";
input string InpBaseURL        = "https://api.openmodel.ai";
input bool   InpEnableTrading  = false;
input double InpMaxDailyTrades = 3;
input double InpMinConfidence  = 65;
input int    InpAnalysisBars   = 30;
input ENUM_TIMEFRAMES InpTF    = PERIOD_D1;
input int    InpAnalysisHour   = 1;
input bool   InpUseSL          = true;
input bool   InpUseTP          = true;
input double InpFixedLots      = 0.0;
input double InpRiskPct        = 1.0;
input int    InpMagic          = 20240501;

//+------------------------------------------------------------------+
//| Global variables                                                 |
//+------------------------------------------------------------------+
//+------------------------------------------------------------------+
//| Signal enum                                                      |
//+------------------------------------------------------------------+
enum ENUM_SIGNAL
{
   SIGNAL_HOLD = 0,
   SIGNAL_BUY  = 1,
   SIGNAL_SELL = -1
};

string SignalToString(ENUM_SIGNAL s)
{
   switch (s)
   {
      case SIGNAL_BUY:  return "BUY";
      case SIGNAL_SELL: return "SELL";
   }
   return "HOLD";
}

int GetDayOfYear()
{
   MqlDateTime dt;
   TimeCurrent(dt);
   return dt.day_of_year;
}

CTrade      m_trade;
JSONParser  m_parser;
string      m_prev_symbol;
ENUM_TIMEFRAMES m_prev_tf;
datetime    m_last_bar_time;
int         m_daily_trade_count = 0;
int         m_last_trade_day    = 0;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   if (InpAPIKey == "" || InpAPIKey == "your-api-key-here")
   {
      Print("[ERROR] API Key not set! Set it in EA inputs.");
      return INIT_PARAMETERS_INCORRECT;
   }

   m_trade.SetExpertMagicNumber(InpMagic);
   m_prev_symbol = _Symbol;
   m_prev_tf = InpTF;
   m_last_bar_time = GetLastBarTime();
   m_last_trade_day = GetDayOfYear();

   Print("[INFO] Trada EA initialized. Model: ", InpModel);
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   Print("[INFO] Trada EA stopped.");
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
   if (!IsNewBar())
      return;

   if (!IsAnalysisHour())
      return;

   ResetDailyCount();
   CollectAndAnalyze();
}

//+------------------------------------------------------------------+
//| Check for new bar on configured timeframe                        |
//+------------------------------------------------------------------+
bool IsNewBar()
{
   datetime bars[], current;
   if (CopyTime(_Symbol, InpTF, 0, 1, bars) < 1)
      return false;

   current = bars[0];
   if (current != m_last_bar_time)
   {
      m_last_bar_time = current;
      return true;
   }
   return false;
}

//+------------------------------------------------------------------+
//| Check if current server hour matches configured hour             |
//+------------------------------------------------------------------+
bool IsAnalysisHour()
{
   MqlDateTime dt;
   TimeCurrent(dt);
   return (dt.hour == InpAnalysisHour);
}

//+------------------------------------------------------------------+
//| Get timestamp of the last completed bar                          |
//+------------------------------------------------------------------+
datetime GetLastBarTime()
{
   datetime bars[];
   if (CopyTime(_Symbol, InpTF, 0, 1, bars) < 1)
      return 0;
   return bars[0];
}

//+------------------------------------------------------------------+
//| Reset daily trade count at day boundary                          |
//+------------------------------------------------------------------+
void ResetDailyCount()
{
   int today = GetDayOfYear();
   if (today != m_last_trade_day)
   {
      m_daily_trade_count = 0;
      m_last_trade_day = today;
   }
}

//+------------------------------------------------------------------+
//| Collect data, query AI, parse signal, execute                   |
//+------------------------------------------------------------------+
void CollectAndAnalyze()
{
   string summary = CollectMarketData();
   if (summary == "")
   {
      Print("[ERROR] Failed to collect market data");
      return;
   }

   string ai_response = QueryAI(summary);
   if (ai_response == "")
   {
      Print("[ERROR] AI analysis failed or timed out");
      return;
   }

   ENUM_SIGNAL signal = SIGNAL_HOLD;
   double confidence = 0;
   string risk = "";
   double stop_loss = 0;
   double take_profit = 0;

   if (!ParseAIResponse(ai_response, signal, confidence, risk, stop_loss, take_profit))
   {
      Print("[ERROR] Failed to parse AI response");
      return;
   }

   Print("[SIGNAL] ", SignalToString(signal),
         " | Confidence: ", DoubleToString(confidence, 0), "%",
         " | Risk: ", risk);

   if (signal == SIGNAL_HOLD)
   {
      Print("[INFO] HOLD signal. No action.");
      return;
   }

   if (confidence < InpMinConfidence)
   {
      Print("[INFO] Confidence (", DoubleToString(confidence, 0),
            "%) below threshold (", DoubleToString(InpMinConfidence, 0), "%)");
      return;
   }

   if (!InpEnableTrading)
   {
      Print("[INFO] Signal generated but trading DISABLED. Set InpEnableTrading=true to execute.");
      return;
   }

   if (m_daily_trade_count >= (int)InpMaxDailyTrades)
   {
      Print("[INFO] Daily trade limit (", (int)InpMaxDailyTrades, ") reached");
      return;
   }

   ExecuteTrade(signal, stop_loss, take_profit);
}

//+------------------------------------------------------------------+
//| Collect and summarize market data                                |
//+------------------------------------------------------------------+
string CollectMarketData()
{
   int bars_needed = MathMax(InpAnalysisBars, 22);
   int total = Bars(_Symbol, InpTF);
   if (total < bars_needed)
   {
      Print("[WARN] Not enough bars: ", total, " (need ", bars_needed, ")");
      return "";
   }

   double close[];
   double high[];
   double low[];
   long   volume[];
   if (CopyClose(_Symbol, InpTF, 0, bars_needed, close) < bars_needed ||
       CopyHigh(_Symbol, InpTF, 0, bars_needed, high) < bars_needed ||
       CopyLow(_Symbol, InpTF, 0, bars_needed, low) < bars_needed ||
       CopyTickVolume(_Symbol, InpTF, 0, bars_needed, volume) < bars_needed)
   {
      return "";
   }

   double current_close = close[0];
   double prev_close    = close[1];
   double change_pct = (prev_close > 0) ? ((current_close - prev_close) / prev_close) * 100.0 : 0;

   double period_high = high[0];
   double period_low  = low[0];
   double vol_sum     = 0;
   double sma7_sum    = 0;
   double sma21_sum   = 0;

   for (int i = 0; i < bars_needed; i++)
   {
      if (high[i] > period_high) period_high = high[i];
      if (low[i]  < period_low)  period_low  = low[i];
      vol_sum += (double)volume[i];
      if (i < 7)  sma7_sum  += close[i];
      if (i < 21) sma21_sum += close[i];
   }

   double avg_vol  = vol_sum / bars_needed;
   double sma_7    = sma7_sum  / 7.0;
   double sma_21   = sma21_sum / 21.0;
   double ask      = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid      = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double point    = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   double spread   = (ask - bid) / point;

   string summary = StringFormat(
      "Symbol: %s\n"
      "Timeframe: current\n"
      "Current Price: %.5f\n"
      "Bid: %.5f | Ask: %.5f\n"
      "Change: %.2f%%\n"
      "Period High: %.5f\n"
      "Period Low: %.5f\n"
      "Avg Volume: %.0f\n"
      "SMA(7): %.5f\n"
      "SMA(21): %.5f\n"
      "Spread: %.1f pips\n"
      "Data Points: %d",
      _Symbol,
      current_close,
      bid, ask,
      change_pct,
      period_high, period_low,
      avg_vol,
      sma_7, sma_21,
      spread,
      bars_needed
   );

   return summary;
}

//+------------------------------------------------------------------+
//| Query OpenModel API via WebRequest                                |
//+------------------------------------------------------------------+
string QueryAI(string market_summary)
{
   string system_prompt = "You are a professional trading analyst. Analyze the market data and "
      "give a clear recommendation. Return ONLY a valid JSON object with exactly these fields: "
      "{\"signal\": \"BUY\"|\"SELL\"|\"HOLD\", "
      "\"confidence\": 0-100, "
      "\"reasoning\": \"brief explanation\", "
      "\"risk\": \"LOW\"|\"MEDIUM\"|\"HIGH\", "
      "\"suggested_entry\": number or null, "
      "\"stop_loss\": number or null, "
      "\"take_profit\": number or null}. "
      "Be conservative. Only BUY/SELL with strong conviction.";

   string body = "{";
   body += "\"model\":\"" + InpModel + "\",";
   body += "\"messages\":[";
   body += "{\"role\":\"system\",\"content\":\"" + EscapeJSON(system_prompt) + "\"},";
   body += "{\"role\":\"user\",\"content\":\"" + EscapeJSON(market_summary) + "\"}";
   body += "],";
   body += "\"temperature\":0.3,";
   body += "\"max_tokens\":1024";
   body += "}";

   string url = InpBaseURL + "/v1/chat/completions";
   string headers = "Authorization: Bearer " + InpAPIKey + "\r\n"
                  + "Content-Type: application/json\r\n";

   uchar post_data[];
   int data_len = StringLen(body);
   ArrayResize(post_data, data_len);
   for (int i = 0; i < data_len; i++)
      post_data[i] = (uchar)StringGetCharacter(body, i);

   uchar result_data[];
   string result_headers;
   int timeout = 15000;

   ResetLastError();
   int res = WebRequest("POST", url, headers, timeout, post_data, result_data, result_headers);

   if (res == -1)
   {
      int err = GetLastError();
      Print("[ERROR] WebRequest failed. Error: ", err);
      if (err == 4060)
         Print("  -> Add '", url, "' to Tools > Options > Expert Advisors > Allow WebRequest");
      return "";
   }

   string response = "";
   for (int i = 0; i < ArraySize(result_data); i++)
      response += ShortToString(result_data[i]);

   if (res != 200)
   {
      Print("[ERROR] API returned HTTP ", res, ": ", StringSubstr(response, 0, 200));
      return "";
   }

   return ExtractContent(response);
}

//+------------------------------------------------------------------+
//| Extract assistant content from OpenAI response                   |
//+------------------------------------------------------------------+
string ExtractContent(string raw)
{
   int idx = StringFind(raw, "\"role\":\"assistant\"");
   if (idx < 0)
   {
      idx = StringFind(raw, "\"content\":\"");
      if (idx < 0) return "";
      idx += 11;
   }
   else
   {
      idx = StringFind(raw, "\"content\":\"", idx);
      if (idx < 0) return "";
      idx += 11;
   }

   string result = "";
   int len = StringLen(raw);
   while (idx < len)
   {
      ushort c = StringGetCharacter(raw, idx);
      if (c == '"')
      {
         if (idx + 1 >= len) break;
         ushort next = StringGetCharacter(raw, idx + 1);
         if (next == ',' || next == '}' || next == '\n' || next == '\r')
            break;
      }
      if (c == '\\' && idx + 1 < len)
      {
         ushort next = StringGetCharacter(raw, idx + 1);
         if (next == '"') result += "\"";
         else if (next == 'n') result += "\n";
         else if (next == 't') result += "\t";
         else if (next == '\\') result += "\\";
         else result += ShortToString(c) + ShortToString(next);
         idx += 2;
         continue;
      }
      result += ShortToString(c);
      idx++;
   }

   return result;
}

//+------------------------------------------------------------------+
//| Parse AI JSON response into structured signals                   |
//+------------------------------------------------------------------+
bool ParseAIResponse(string resp, ENUM_SIGNAL &signal, double &confidence,
                     string &risk, double &stop_loss, double &take_profit)
{
   StringReplace(resp, "```json", "");
   StringReplace(resp, "```", "");
   StringTrimLeft(resp);
   StringTrimRight(resp);

   m_parser.Parse(resp);

   string raw = m_parser.GetString("signal");
   StringToUpper(raw);
   StringTrimLeft(raw);
   StringTrimRight(raw);

   if (raw == "BUY")       signal = SIGNAL_BUY;
   else if (raw == "SELL") signal = SIGNAL_SELL;
   else                    signal = SIGNAL_HOLD;

   confidence = m_parser.GetDouble("confidence");
   risk       = m_parser.GetString("risk");
   stop_loss  = m_parser.GetDouble("stop_loss");
   take_profit = m_parser.GetDouble("take_profit");

   return true;
}

//+------------------------------------------------------------------+
//| Execute trade based on signal                                    |
//+------------------------------------------------------------------+
void ExecuteTrade(ENUM_SIGNAL signal, double stop_loss, double take_profit)
{
   double lots = CalculateLots();
   if (lots <= 0)
   {
      Print("[ERROR] Invalid lot size: ", DoubleToString(lots, 2));
      return;
   }

   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);

   double sl = 0, tp = 0;
   if (InpUseSL && stop_loss > 0)
      sl = NormalizeDouble(stop_loss, digits);
   if (InpUseTP && take_profit > 0)
      tp = NormalizeDouble(take_profit, digits);

   bool result = false;
   if (signal == SIGNAL_BUY)
   {
      result = m_trade.Buy(lots, _Symbol, ask, sl, tp);
   }
   else if (signal == SIGNAL_SELL)
   {
      result = m_trade.Sell(lots, _Symbol, bid, sl, tp);
   }

   if (result)
   {
      m_daily_trade_count++;
      Print("[TRADE] ", (signal == SIGNAL_BUY ? "BUY" : "SELL"),
            " | Lots: ", DoubleToString(lots, 2),
            " | SL: ", DoubleToString(sl, digits),
            " | TP: ", DoubleToString(tp, digits));
   }
   else
   {
      Print("[ERROR] Trade failed. Code: ", GetLastError());
   }
}

//+------------------------------------------------------------------+
//| Calculate lot size from risk or fixed value                      |
//+------------------------------------------------------------------+
double CalculateLots()
{
   if (InpFixedLots > 0)
      return NormalizeLot(InpFixedLots);

   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double risk_amount = balance * (InpRiskPct / 100.0);

   double tick_value = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   if (tick_value <= 0) tick_value = 0.01;

   double stop_dist = 100 * SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   double risk_per_lot = stop_dist / SymbolInfoDouble(_Symbol, SYMBOL_POINT) * tick_value;

   if (risk_per_lot <= 0)
      return NormalizeLot(0.01);

   double lots = risk_amount / risk_per_lot;
   return NormalizeLot(lots);
}

//+------------------------------------------------------------------+
//| Normalize lot size to broker requirements                        |
//+------------------------------------------------------------------+
double NormalizeLot(double lots)
{
   double min_lot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double max_lot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double step    = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);

   if (min_lot <= 0) min_lot = 0.01;
   if (step <= 0)    step    = 0.01;

   lots = MathFloor(lots / step) * step;
   lots = MathMax(lots, min_lot);
   lots = MathMin(lots, max_lot);

   return lots;
}

//+------------------------------------------------------------------+
//| Escape string for JSON body                                      |
//+------------------------------------------------------------------+
string EscapeJSON(string str)
{
   string result = "";
   int len = StringLen(str);
   for (int i = 0; i < len; i++)
   {
      ushort c = StringGetCharacter(str, i);
      if (c == '"')
         result += "\\\"";
      else if (c == '\\')
         result += "\\\\";
      else if (c == 10)
         result += "\\n";
      else if (c == 13)
         result += "\\r";
      else if (c == 9)
         result += "\\t";
      else
         result += ShortToString(c);
   }
   return result;
}

//+------------------------------------------------------------------+