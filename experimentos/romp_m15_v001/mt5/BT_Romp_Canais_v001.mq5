//+------------------------------------------------------------------+
//| BT_Romp_Canais_v001 — BotTested · experiência ROMP-M15-0.1        |
//| SÓ EXIBE: canais de entrada (20 barras ANTERIORES) e de saída     |
//| (10 barras ANTERIORES) — a barra atual NÃO entra — e as marcas    |
//| gravadas pelo executor Python (sinal, entrada, stop, saída).      |
//| Não envia ordens.                                                 |
//+------------------------------------------------------------------+
#property indicator_chart_window
#property indicator_buffers 4
#property indicator_plots   4
#property indicator_label1  "LS20 (máx 20 anteriores)"
#property indicator_type1   DRAW_LINE
#property indicator_color1  clrDodgerBlue
#property indicator_label2  "LI20 (mín 20 anteriores)"
#property indicator_type2   DRAW_LINE
#property indicator_color2  clrDodgerBlue
#property indicator_label3  "LS10 (máx 10 anteriores)"
#property indicator_type3   DRAW_LINE
#property indicator_style3  STYLE_DOT
#property indicator_color3  clrOrange
#property indicator_label4  "LI10 (mín 10 anteriores)"
#property indicator_type4   DRAW_LINE
#property indicator_style4  STYLE_DOT
#property indicator_color4  clrOrange
input int  N_entrada = 20;
input int  N_saida   = 10;
double LS20[], LI20[], LS10[], LI10[];
string ARQ;

int OnInit()
{
   SetIndexBuffer(0, LS20); SetIndexBuffer(1, LI20); SetIndexBuffer(2, LS10); SetIndexBuffer(3, LI10);
   for(int k = 0; k < 4; k++) PlotIndexSetDouble(k, PLOT_EMPTY_VALUE, EMPTY_VALUE);
   ARQ = "BT_ROMP\\marcas_" + _Symbol + ".csv";
   EventSetTimer(5);
   return(INIT_SUCCEEDED);
}
void OnDeinit(const int r) { EventKillTimer(); ObjectsDeleteAll(0, "ROMP_"); }

int OnCalculate(const int total, const int prev, const datetime &time[], const double &open[], const double &high[],
                const double &low[], const double &close[], const long &tv[], const long &vol[], const int &spread[])
{
   ArraySetAsSeries(high, false); ArraySetAsSeries(low, false);
   int ini = (prev > 0 ? prev - 1 : 0);
   for(int i = ini; i < total; i++)
   {
      LS20[i] = LI20[i] = LS10[i] = LI10[i] = EMPTY_VALUE;
      if(i >= N_entrada) { double mx = high[i-1], mn = low[i-1]; for(int j = i - N_entrada; j < i; j++) { mx = MathMax(mx, high[j]); mn = MathMin(mn, low[j]); } LS20[i] = mx; LI20[i] = mn; }
      if(i >= N_saida)   { double mx = high[i-1], mn = low[i-1]; for(int j = i - N_saida;   j < i; j++) { mx = MathMax(mx, high[j]); mn = MathMin(mn, low[j]); } LS10[i] = mx; LI10[i] = mn; }
   }
   return(total);
}

void OnTimer()
{
   int h = FileOpen(ARQ, FILE_READ | FILE_TXT | FILE_COMMON | FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_ANSI);
   if(h == INVALID_HANDLE) return;
   int n = 0;
   while(!FileIsEnding(h))
   {
      string ln = FileReadString(h); string c[]; if(StringSplit(ln, ';', c) < 5) continue;
      datetime t = (datetime)StringToInteger(c[0]); string tipo = c[1]; double px = StringToDouble(c[2]);
      string nome = "ROMP_" + IntegerToString(n++) + "_" + tipo;
      if(ObjectFind(0, nome) >= 0) continue;
      int cod = 159; color cor = clrWhite;
      if(tipo == "SINAL")   { cod = 108; cor = clrYellow; }
      if(tipo == "ENTRADA") { cod = 233; cor = clrLime; }
      if(tipo == "STOP")    { cod = 251; cor = clrRed; }
      if(tipo == "SAIDA")   { cod = 251; cor = clrMagenta; }
      ObjectCreate(0, nome, OBJ_ARROW, 0, t, px); ObjectSetInteger(0, nome, OBJPROP_ARROWCODE, cod); ObjectSetInteger(0, nome, OBJPROP_COLOR, cor);
      ObjectSetString(0, nome, OBJPROP_TOOLTIP, tipo + " · " + c[3] + " · " + c[4]);
   }
   FileClose(h); ChartRedraw();
}
