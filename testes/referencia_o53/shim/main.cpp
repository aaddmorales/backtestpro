#include "ea.cpp"
int SIM_TF_MIN = 15; int _Period = PERIOD_M15; std::vector<MqlRates> SIM_BARS, SIM_H1; MqlTick SIM_TICK; SimPos SIM_POS; std::vector<string> SIM_LOG; long SIM_MAGIC = 0;
long long SIM_ULT_TICKET = 0; int SIM_CONTA_MODO = getenv("SIM_CONTA_REAL") ? 2 : 0; int SIM_ULT_RAZAO = 0; double SIM_ULT_PX = 0;
static std::vector<MqlRates> ler(const char* f) {
  std::ifstream in(f); string ln; std::getline(in, ln); std::vector<MqlRates> v;
  while (std::getline(in, ln)) { std::istringstream ss(ln); string d, t; MqlRates r{}; ss >> d >> t >> r.open >> r.high >> r.low >> r.close;
    std::tm tm{}; sscanf((d + " " + t).c_str(), "%d.%d.%d %d:%d:%d", &tm.tm_year, &tm.tm_mon, &tm.tm_mday, &tm.tm_hour, &tm.tm_min, &tm.tm_sec);
    tm.tm_year -= 1900; tm.tm_mon -= 1; r.time = timegm(&tm); v.push_back(r); } return v; }
int main(int argc, char** argv) {   // argv: tf_min arquivo_tf arquivo_m1 inicio_epoch spread_pontos [arquivo_h1]
  SIM_TF_MIN = atoi(argv[1]); _Period = SIM_TF_MIN == 60 ? PERIOD_H1 : SIM_TF_MIN == 30 ? PERIOD_M30 : PERIOD_M15;
  SIM_BARS = ler(argv[2]); auto m1 = ler(argv[3]); long long ini = atoll(argv[4]); double sp = atof(argv[5]) * 0.01; if (argc > 6) SIM_H1 = ler(argv[6]);
  OnInit();
  for (auto& b : m1) { bool up = b.close >= b.open; double p1 = up ? b.low : b.high, p2 = up ? b.high : b.low;
    double B[4] = {b.open, p1, p2, b.close}; long long T[4] = {b.time * 1000, b.time * 1000 + 15000, b.time * 1000 + 30000, b.time * 1000 + 59000};
    for (int k = 0; k < 4; k++) { if (T[k] / 1000 < ini) continue;
      SIM_TICK = {T[k] / 1000, std::round(B[k] * 100) / 100, std::round((B[k] + sp) * 100) / 100, 0, 0, T[k]};
      if (SIM_POS.aberta && ((SIM_POS.lado < 0 && SIM_TICK.ask >= SIM_POS.sl) || (SIM_POS.lado > 0 && SIM_TICK.bid <= SIM_POS.sl))) {
        double px = SIM_POS.lado < 0 ? SIM_TICK.ask : SIM_TICK.bid;
        SIM_LOG.push_back("FECHA|stop|" + std::to_string(SIM_TICK.time) + "|" + DoubleToString(px, 2)); SIM_POS.aberta = false; SIM_ULT_RAZAO = DEAL_REASON_SL; SIM_ULT_PX = px; }
      OnTick(); } }
  for (auto& l : SIM_LOG) std::cout << l << "\n"; }
