#include "ea.cpp"
int SIM_TF_MIN = 15; std::vector<MqlRates> SIM_BARS; MqlTick SIM_TICK; SimPos SIM_POS; std::vector<string> SIM_LOG; long SIM_MAGIC = 0;
static std::vector<MqlRates> ler(const char* f) {
  std::ifstream in(f); string ln; std::getline(in, ln); std::vector<MqlRates> v;
  while (std::getline(in, ln)) { std::istringstream ss(ln); string d, t; MqlRates r{}; ss >> d >> t >> r.open >> r.high >> r.low >> r.close;
    std::tm tm{}; sscanf((d + " " + t).c_str(), "%d.%d.%d %d:%d:%d", &tm.tm_year, &tm.tm_mon, &tm.tm_mday, &tm.tm_hour, &tm.tm_min, &tm.tm_sec);
    tm.tm_year -= 1900; tm.tm_mon -= 1; r.time = timegm(&tm); v.push_back(r); } return v; }
int main(int argc, char** argv) {   // argv: tf_min arquivo_tf arquivo_m1 inicio_epoch spread
  SIM_TF_MIN = atoi(argv[1]); SIM_BARS = ler(argv[2]); auto m1 = ler(argv[3]); long long ini = atoll(argv[4]); double sp = atof(argv[5]) * 0.01;
  OnInit();
  for (auto& b : m1) { bool up = b.close >= b.open; double p1 = up ? b.low : b.high, p2 = up ? b.high : b.low;
    double B[4] = {b.open, p1, p2, b.close}; long long T[4] = {b.time * 1000, b.time * 1000 + 15000, b.time * 1000 + 30000, b.time * 1000 + 59000};
    for (int k = 0; k < 4; k++) { if (T[k] / 1000 < ini) continue;
      SIM_TICK = {T[k] / 1000, std::round(B[k] * 100) / 100, std::round((B[k] + sp) * 100) / 100, 0, 0, T[k]};
      if (SIM_POS.aberta && ((SIM_POS.lado < 0 && SIM_TICK.ask >= SIM_POS.sl) || (SIM_POS.lado > 0 && SIM_TICK.bid <= SIM_POS.sl))) {
        SIM_LOG.push_back("FECHA|stop|" + std::to_string(SIM_TICK.time) + "|" + DoubleToString(SIM_POS.lado < 0 ? SIM_TICK.ask : SIM_TICK.bid, 2)); SIM_POS.aberta = false; }
      OnTick(); } }
  for (auto& l : SIM_LOG) std::cout << l << "\n"; }
