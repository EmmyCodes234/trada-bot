//+------------------------------------------------------------------+
//| Simple JSON Parser for MQL5                                      |
//+------------------------------------------------------------------+
class JSONParser
{
private:
   string _json;
   int _pos;
   int _len;

   void SkipWhitespace()
   {
      while (_pos < _len)
      {
         ushort c = StringGetCharacter(_json, _pos);
         if (c == ' ' || c == 9 || c == 10 || c == 13)
            _pos++;
         else
            break;
      }
   }

   string ReadString()
   {
      if (_pos >= _len || StringGetCharacter(_json, _pos) != '"')
         return "";
      _pos++;
      string result = "";
      while (_pos < _len)
      {
         ushort c = StringGetCharacter(_json, _pos);
         if (c == '"')
         {
            _pos++;
            return result;
         }
         if (c == '\\')
         {
            _pos++;
            if (_pos < _len)
            {
               ushort next = StringGetCharacter(_json, _pos);
               if (next == '"') result += "\"";
               else if (next == '\\') result += "\\";
               else if (next == 'n') result += "\n";
               else if (next == 't') result += "\t";
               else if (next == '/') result += "/";
               else result += ShortToString(next);
               _pos++;
            }
         }
         else
         {
            result += ShortToString(c);
            _pos++;
         }
      }
      return result;
   }

public:
   JSONParser() : _pos(0), _len(0) {}

   bool Parse(string json)
   {
      _json = json;
      _pos = 0;
      _len = StringLen(_json);
      SkipWhitespace();
      return _pos < _len;
   }

   string GetString(string key)
   {
      _pos = 0;
      _len = StringLen(_json);
      SkipWhitespace();
      if (_pos >= _len || StringGetCharacter(_json, _pos) != '{') return "";
      _pos++;
      while (_pos < _len)
      {
         SkipWhitespace();
         if (StringGetCharacter(_json, _pos) == '}') break;
         string k = ReadString();
         if (k == "")
         {
            if (_pos < _len && StringGetCharacter(_json, _pos) == ',') _pos++;
            continue;
         }
         SkipWhitespace();
         if (_pos < _len && StringGetCharacter(_json, _pos) == ':') _pos++;
         SkipWhitespace();
         if (k == key)
         {
            if (_pos < _len && StringGetCharacter(_json, _pos) == '"')
               return ReadString();
            else
            {
               int start = _pos;
               while (_pos < _len && StringGetCharacter(_json, _pos) != ',' && StringGetCharacter(_json, _pos) != '}')
                  _pos++;
               return StringSubstr(_json, start, _pos - start);
            }
         }
         else
         {
            if (_pos < _len && StringGetCharacter(_json, _pos) == '"')
               ReadString();
            else
               while (_pos < _len && StringGetCharacter(_json, _pos) != ',' && StringGetCharacter(_json, _pos) != '}')
                  _pos++;
         }
         if (_pos < _len && StringGetCharacter(_json, _pos) == ',') _pos++;
      }
      return "";
   }

   int GetInt(string key)
   {
      string s = GetString(key);
      StringTrimLeft(s);
      StringTrimRight(s);
      return (int)StringToInteger(s);
   }

   double GetDouble(string key)
   {
      string s = GetString(key);
      StringTrimLeft(s);
      StringTrimRight(s);
      return StringToDouble(s);
   }
};
