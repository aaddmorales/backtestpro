// camada mínima que imita a API do MT5 para rodar a LÓGICA do EA em C++ (teste; não é o MT5)
#include <bits/stdc++.h>
typedef long long datetime; using std::string;
struct MqlRates { datetime time; double open, high, low, close; long tick_volume; int spread; long real_volume; };
struct MqlTick { datetime time; double bid, ask, last; ulong volume; long time_msc; };
enum { INIT_SUCCEEDED = 0, POSITION_TYPE_BUY = 0, POSITION_TYPE_SELL = 1, POSITION_SYMBOL = 1, POSITION_MAGIC = 2, POSITION_TYPE = 3, TIME_DATE = 1, TIME_MINUTES = 2 };
extern int SIM_TF_MIN; extern std::vector<MqlRates> SIM_BARS; extern MqlTick SIM_TICK;
struct SimPos { bool aberta = false; int lado = 0; double entrada = 0, sl = 0; long long t_ent = 0; };
extern SimPos SIM_POS; extern std::vector<string> SIM_LOG;
static const string _Symbol = "BTCUSD"; static const int _Digits = 2;
#define PERIOD_M15 1
#define PERIOD_M30 2
#define PERIOD_H1  3
static const int _Period = PERIOD_M15;
inline int PeriodSeconds(int) { return SIM_TF_MIN * 60; }
inline string IntegerToString(long long v) { return std::to_string(v); }
inline string DoubleToString(double v, int d) { char b[64]; snprintf(b, 64, "%.*f", d, v); return b; }
inline string TimeToString(datetime t, int) { return std::to_string(t); }
inline long StringFind(const string& s, const string& x) { auto p = s.find(x); return p == string::npos ? -1 : (long)p; }
inline double MathRound(double x) { return std::round(x); } inline double MathMax(double a, double b) { return std::max(a, b); } inline double MathAbs(double a) { return std::fabs(a); }
inline double NormalizeDouble(double x, int d) { double m = std::pow(10.0, d); return std::round(x * m) / m; }
template <class T> inline void ArrayResize(std::vector<T>& v, int n) { v.resize(n); }
template <class T> inline int ArraySize(const std::vector<T>& v) { return (int)v.size(); }
template <class T> inline void ArraySetAsSeries(std::vector<T>&, bool) {}
inline void _p(std::ostringstream&) {} template <class A, class... R> inline void _p(std::ostringstream& o, const A& a, const R&... r) { o << a; _p(o, r...); }
template <class... R> inline void Print(const R&... r) { std::ostringstream o; _p(o, r...); SIM_LOG.push_back(o.str()); }
inline datetime iTime(const string&, int, int shift) { long long dur = SIM_TF_MIN * 60; return (SIM_TICK.time / dur) * dur; }
inline int CopyRates(const string&, int, int start, int count, std::vector<MqlRates>& r) {   // start=1: só barras fechadas
  long long dur = SIM_TF_MIN * 60; std::vector<MqlRates> f; for (auto& b : SIM_BARS) if (b.time + dur <= SIM_TICK.time) f.push_back(b);
  int ini = std::max(0, (int)f.size() - count); r.assign(f.begin() + ini, f.end()); return (int)r.size(); }
inline bool SymbolInfoTick(const string&, MqlTick& q) { q = SIM_TICK; return true; }
inline int PositionsTotal() { return SIM_POS.aberta ? 1 : 0; } inline ulong PositionGetTicket(int) { return 1; }
inline string PositionGetString(int) { return _Symbol; } extern long SIM_MAGIC;
inline long PositionGetInteger(int k) { return k == POSITION_MAGIC ? SIM_MAGIC : (SIM_POS.lado > 0 ? POSITION_TYPE_BUY : POSITION_TYPE_SELL); }
struct CTrade { void SetExpertMagicNumber(long m) { SIM_MAGIC = m; }
  bool Buy(double, const string&, double, double sl, double, const char*) { SIM_POS = {true, 1, SIM_TICK.ask, sl, SIM_TICK.time}; SIM_LOG.push_back("ORDEM|buy|" + std::to_string(SIM_TICK.time) + "|" + DoubleToString(SIM_TICK.ask, 2) + "|" + DoubleToString(sl, 2)); return true; }
  bool Sell(double, const string&, double, double sl, double, const char*) { SIM_POS = {true, -1, SIM_TICK.bid, sl, SIM_TICK.time}; SIM_LOG.push_back("ORDEM|sell|" + std::to_string(SIM_TICK.time) + "|" + DoubleToString(SIM_TICK.bid, 2) + "|" + DoubleToString(sl, 2)); return true; }
  bool PositionClose(ulong) { double px = SIM_POS.lado < 0 ? SIM_TICK.ask : SIM_TICK.bid; SIM_LOG.push_back("FECHA|canal|" + std::to_string(SIM_TICK.time) + "|" + DoubleToString(px, 2)); SIM_POS.aberta = false; return true; } };
