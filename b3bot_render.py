import yfinance as yf
import pandas as pd
from datetime import datetime
import time
import threading
import pytz
import requests
import os

# ============================================
# CONFIGURAÇÕES
# ============================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8207229215:AAGNJfXhQm2Xmqzv6XQ8pZ_8Ml-iaZl387Y")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "5869218072")
HORARIO_ENVIO = 10
TOP_OPORTUNIDADES = 10
LIQUIDEZ_MINIMA = 1000000

def enviar_telegram(mensagem):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram não configurado")
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": mensagem, "parse_mode": "HTML"}
        r = requests.post(url, json=payload, timeout=5)
        return r.status_code == 200
    except:
        return False

def buscar_todos_tickers_b3():
    tickers = []
    try:
        url = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?scrId=6655000&count=1000"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=30)
        data = response.json()
        quotes = data.get('finance', {}).get('result', [{}])[0].get('quotes', [])
        for quote in quotes:
            symbol = quote.get('symbol', '')
            if symbol.endswith('.SA') and len(symbol) >= 6:
                ticker = symbol.replace('.SA', '')
                if ticker and ticker[-1] in '3456':
                    tickers.append(ticker)
        if len(tickers) > 50:
            print(f"✅ {len(tickers)} tickers encontrados")
            return tickers
    except Exception as e:
        print(f"⚠️ Erro na busca: {e}")

    return ["PETR4", "VALE3", "ITUB4", "BBDC4", "ABEV3", "BBAS3", "WEGE3", "ITSA4"]

def calcular_indicadores_tecnicos(dados_historicos):
    if dados_historicos.empty or len(dados_historicos) < 30:
        return None
    try:
        close = dados_historicos['Close']
        low = dados_historicos['Low']
        preco = close.iloc[-1]
        mm50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else preco
        mm100 = close.rolling(100).mean().iloc[-1] if len(close) >= 100 else preco
        mm200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else preco
        fundo_30d = low.tail(30).min()
        niveis = [mm50, mm100, mm200, fundo_30d]
        suportes_validos = [n for n in niveis if n <= preco]
        if suportes_validos:
            suporte = max(suportes_validos)
        else:
            suporte = fundo_30d
        resistencia = close.max()
        dist_suporte = ((preco - suporte) / suporte) * 100 if suporte > 0 else 0
        return {
            'preco_atual': round(preco, 2),
            'suporte': round(suporte, 2),
            'resistencia': round(resistencia, 2),
            'dist_suporte': round(dist_suporte, 1),
            'mm50': round(mm50, 2),
            'mm100': round(mm100, 2),
            'mm200': round(mm200, 2),
            'fundo_30d': round(fundo_30d, 2)
        }
    except:
        return None

def buscar_acao_completa(ticker, dados_historicos):
    try:
        ticker_yf = f"{ticker}.SA"
        try:
            df_acao = dados_historicos[ticker_yf]
        except Exception:
            return None
        if df_acao is None or df_acao.empty:
            return None
        tecnicos = calcular_indicadores_tecnicos(df_acao)
        if not tecnicos:
            return None
        stock = yf.Ticker(ticker_yf)
        fast_info = stock.fast_info
        preco = tecnicos['preco_atual']
        if preco <= 0:
            return None
        volume_financeiro = (df_acao["Close"].tail(20) * df_acao["Volume"].tail(20)).mean()
        if volume_financeiro < LIQUIDEZ_MINIMA:
            return None
        info = stock.info
        pl = info.get('trailingPE', 0)
        pvp = info.get('priceToBook', 0)
        roe = info.get('returnOnEquity', 0) * 100 if info.get('returnOnEquity') else 0
        margem = info.get('profitMargins', 0) * 100 if info.get('profitMargins') else 0
        
        # ============================================
        # DY CORRIGIDO - Usando trailingAnnualDividendYield
        # ============================================
        dy_raw = info.get('trailingAnnualDividendYield', 0)
        
        if dy_raw is None or dy_raw == 0:
            dy_raw = info.get('dividendYield', 0)
            if dy_raw is None or dy_raw == 0:
                dy = 0
            elif dy_raw > 1:
                dy = dy_raw
            else:
                dy = dy_raw * 100
        else:
            dy = dy_raw * 100
        
        if dy > 10 or dy < 0:
            dy = 0
        
        revenue_growth = info.get('revenueGrowth', 0) * 100 if info.get('revenueGrowth') else 0
        debt_to_equity = info.get('debtToEquity', 0)
        
        if pl < 2 or pl > 15:
            return None
        if pvp < 0.3 or pvp > 2:
            return None
        if dy < 4:
            return None
        if roe < 8:
            return None
        if margem < 5:
            return None
        if debt_to_equity > 200:
            return None
        
        score = 0
        if pl < 8:
            score -= 4
        elif pl < 10:
            score -= 3
        elif pl < 12:
            score -= 1
        if pvp < 1:
            score -= 3
        elif pvp < 1.5:
            score -= 1
        if roe > 20:
            score -= 3
        elif roe > 15:
            score -= 2
        elif roe > 10:
            score -= 1
        if dy > 8:
            score -= 2
        elif dy > 6:
            score -= 1
        if revenue_growth > 10:
            score -= 1
        
        suporte = tecnicos['suporte']
        distancia = tecnicos['dist_suporte']
        if distancia <= 3:
            classificacao = "🔴 SUPORTE FORTE - COMPRA IMEDIATA"
        elif distancia <= 6:
            classificacao = "🟡 PRÓXIMO SUPORTE - COMPRA PARCIAL"
        elif distancia <= 10:
            classificacao = "🟢 ACIMA SUPORTE - AGUARDAR"
        else:
            classificacao = "🔵 LONGE DO SUPORTE - MONITORAR"
        
        return {
            'ticker': ticker,
            'preco': preco,
            'suporte': suporte,
            'distancia': distancia,
            'classificacao': classificacao,
            'pl': round(pl, 1),
            'pvp': round(pvp, 2),
            'dy': round(dy, 1),
            'roe': round(roe, 1),
            'score': score,
            'volume_mm': round(volume_financeiro / 1000000, 1)
        }
    except Exception as e:
        return None

def buscar_oportunidades():
    print(f"[{datetime.now()}] Buscando tickers...")
    tickers = buscar_todos_tickers_b3()
    if not tickers:
        return []
    print(f"📊 Analisando {len(tickers)} ações...")
    tickers_yf = [f"{t}.SA" for t in tickers]
    dados_historicos = yf.download(tickers_yf, period="1y", group_by='ticker', progress=False, timeout=60)
    if dados_historicos is None or dados_historicos.empty:
        print("❌ Erro ao baixar dados históricos")
        return []
    todas_oportunidades = []
    for i, ticker in enumerate(tickers):
        if (i+1) % 50 == 0:
            print(f"  Progresso: {i+1}/{len(tickers)}")
        acao = buscar_acao_completa(ticker, dados_historicos)
        if acao and acao['distancia'] <= 15 and acao['score'] <= -5:
            todas_oportunidades.append(acao)
    todas_oportunidades.sort(key=lambda x: (x['score'], x['distancia']))
    return todas_oportunidades[:TOP_OPORTUNIDADES]

def enviar_resumo_diario():
    oportunidades = buscar_oportunidades()
    msg = f"📊 <b>RESUMO DIÁRIO - {datetime.now().strftime('%d/%m/%Y')}</b>\n\n"
    if oportunidades:
        msg += f"🐋 <b>OPORTUNIDADES ({len(oportunidades)})</b>\n\n"
        for i, opp in enumerate(oportunidades, 1):
            msg += f"<b>{i}. {opp['ticker']}</b>\n"
            msg += f"💰 Preço: R$ {opp['preco']:.2f}\n"
            msg += f"📊 Score: {opp['score']} | P/L: {opp['pl']}x | P/VP: {opp['pvp']}x\n"
            msg += f"💰 DY: {opp['dy']}% | ROE: {opp['roe']}%\n"
            msg += f"🎯 Suporte: R$ {opp['suporte']:.2f}\n"
            msg += f"📍 Distância: {opp['distancia']:.1f}% acima\n"
            msg += f"⚡ {opp['classificacao']}\n\n"
        msg += f"📌 <i>Top {len(oportunidades)} ações mais baratas</i>"
    else:
        msg += f"✅ Nenhuma oportunidade encontrada hoje."
    enviar_telegram(msg)
    return oportunidades

def monitorar_continuo():
    fuso_sp = pytz.timezone('America/Sao_Paulo')
    print(f"\n🤖 SCANNER B3 INICIADO")
    print(f"⏰ Envio programado para às {HORARIO_ENVIO}:00\n")
    while True:
        now = datetime.now(fuso_sp)
        if now.hour == HORARIO_ENVIO and now.minute < 5:
            enviar_resumo_diario()
            time.sleep(60)
        time.sleep(30)

from flask import Flask, jsonify
app = Flask(__name__)

@app.route('/')
def health():
    return "B3 Scanner Online", 200

@app.route('/scan')
def scan_manual():
    oportunidades = enviar_resumo_diario()
    return f"Scan OK. {len(oportunidades)} oportunidades.", 200

@app.route('/oportunidades')
def ver_oportunidades():
    oportunidades = buscar_oportunidades()
    return jsonify({"total": len(oportunidades), "oportunidades": oportunidades})

if __name__ == "__main__":
    thread = threading.Thread(target=monitorar_continuo, daemon=True)
    thread.start()
    app.run(host='0.0.0.0', port=8080)    for vela in velas[-100:]:
        preco_medio = (vela['maxima'] + vela['minima'] + vela['fechamento']) / 3
        bin_idx = int((preco_medio - min_preco) / bin_size)
        if 0 <= bin_idx < n_bins:
            bin_key = f"{min_preco + bin_idx * bin_size:.2f}-{min_preco + (bin_idx+1) * bin_size:.2f}"
            volume_profile[bin_key] += vela['volume']
    
    return volume_profile

def calcular_suporte_resistencia(velas, n_niveis=3):
    if len(velas) < 50:
        return [], []
    
    highs = [v['maxima'] for v in velas[-100:]]
    lows = [v['minima'] for v in velas[-100:]]
    
    resistencias = []
    suportes = []
    
    for i in range(2, len(highs)-2):
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            resistencias.append(highs[i])
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
            suportes.append(lows[i])
    
    def agrupar_niveis(niveis, tolerancia=0.002):
        if not niveis:
            return []
        niveis.sort()
        grupos = []
        grupo_atual = [niveis[0]]
        
        for nivel in niveis[1:]:
            if (nivel - grupo_atual[-1]) / grupo_atual[-1] < tolerancia:
                grupo_atual.append(nivel)
            else:
                grupos.append(np.mean(grupo_atual))
                grupo_atual = [nivel]
        grupos.append(np.mean(grupo_atual))
        return grupos[:n_niveis]
    
    return agrupar_niveis(suportes), agrupar_niveis(resistencias)

def detectar_absorcao_volume(velas, imbalance):
    if len(velas) < 5:
        return False
    
    movimento_preco = abs(velas[-1]['fechamento'] - velas[-5]['fechamento']) / velas[-5]['fechamento']
    volume_medio = np.mean([v['volume'] for v in velas[-5:]])
    volume_atual = velas[-1]['volume']
    
    if movimento_preco < 0.003 and volume_atual > volume_medio * 1.5 and abs(imbalance) > 0.15:
        return True
    
    return False

def verificar_evento_macro():
    agora = datetime.utcnow()
    
    eventos = [
        {'nome': 'CPI', 'dia': 12, 'hora': 13, 'minuto': 30},
        {'nome': 'FOMC', 'dia': None, 'hora': 19, 'minuto': 0},
        {'nome': 'NFP', 'dia': 5, 'hora': 13, 'minuto': 30},
        {'nome': 'PCE', 'dia': 28, 'hora': 13, 'minuto': 30},
    ]
    
    for evento in eventos:
        if evento['dia']:
            if agora.day == evento['dia']:
                hora_evento = evento['hora']
                minuto_evento = evento['minuto']
                
                tempo_evento = agora.replace(hour=hora_evento, minute=minuto_evento, second=0, microsecond=0)
                tempo_inicio = tempo_evento - timedelta(minutes=30)
                tempo_fim = tempo_evento + timedelta(minutes=30)
                
                if tempo_inicio <= agora <= tempo_fim:
                    return True, evento['nome']
    
    return False, ""

def calcular_imbalance_order_book(depth):
    if not depth:
        return 0
    bids = depth.get('bids', [])
    asks = depth.get('asks', [])
    bid_volume = sum(float(b[1]) for b in bids[:50])
    ask_volume = sum(float(a[1]) for a in asks[:50])
    total = bid_volume + ask_volume
    if total == 0:
        return 0
    return (bid_volume - ask_volume) / total

def calcular_vwap_numpy(velas, periodo=20):
    """Calcula VWAP (Volume Weighted Average Price)"""
    if len(velas) < periodo:
        return 0
    
    precos_medio = (np.array([v['maxima'] for v in velas[-periodo:]]) + 
                    np.array([v['minima'] for v in velas[-periodo:]]) + 
                    np.array([v['fechamento'] for v in velas[-periodo:]])) / 3
    volumes = np.array([v['volume'] for v in velas[-periodo:]])
    
    if np.sum(volumes) == 0:
        return 0
    
    return np.sum(precos_medio * volumes) / np.sum(volumes)

# ============================================
# SQLITE DATABASE
# ============================================
class Database:
    def __init__(self):
        self.conn = None
        self.lock = Lock()
        self.inicializar()
    
    def inicializar(self):
        try:
            self.conn = sqlite3.connect('robo_institucional.db', check_same_thread=False)
            cursor = self.conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    symbol TEXT,
                    sinal TEXT,
                    preco_entrada REAL,
                    preco_saida REAL,
                    pnl REAL,
                    regime TEXT,
                    adx REAL,
                    probabilidade REAL,
                    motivo TEXT,
                    slippage REAL
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS metricas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data TEXT,
                    capital REAL,
                    drawdown REAL,
                    taxa_acerto REAL,
                    sharpe REAL,
                    profit_factor REAL
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sinais (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    symbol TEXT,
                    sinal TEXT,
                    confianca REAL,
                    preco REAL,
                    regime TEXT,
                    adx REAL,
                    vwap REAL,
                    rsi REAL,
                    foi_executado INTEGER DEFAULT 0
                )
            ''')
            
            self.conn.commit()
        except Exception as e:
            print(f"Erro ao inicializar banco: {e}")
    
    def salvar_trade(self, trade):
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                    INSERT INTO trades (timestamp, symbol, sinal, preco_entrada, preco_saida, pnl, regime, adx, probabilidade, motivo, slippage)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    trade['timestamp'], trade['symbol'], trade['sinal'],
                    trade['preco_entrada'], trade['preco_saida'], trade['pnl'],
                    trade['regime'], trade['adx'], trade['probabilidade'], 
                    trade['motivo'], trade.get('slippage', 0)
                ))
                self.conn.commit()
            except:
                pass
    
    def salvar_sinal(self, sinal):
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                    INSERT INTO sinais (timestamp, symbol, sinal, confianca, preco, regime, adx, vwap, rsi, foi_executado)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    sinal['timestamp'], sinal['symbol'], sinal['sinal'],
                    sinal['confianca'], sinal['preco'], sinal['regime'],
                    sinal['adx'], sinal.get('vwap', 0), sinal.get('rsi', 50),
                    sinal['foi_executado']
                ))
                self.conn.commit()
            except:
                pass
    
    def fechar(self):
        if self.conn:
            self.conn.close()

# ============================================
# INDICADORES COM CACHE
# ============================================
class IndicadoresComCache:
    def __init__(self):
        self.cache_atr = {}
        self.cache_adx = {}
        self.cache_rsi = {}
        self.cache_atr_medio = {}
    
    def calcular_atr_wilder(self, velas, periodo=14, symbol=None):
        if len(velas) < periodo + 1:
            return 0
        
        if symbol and len(velas) > 0:
            ultimo_timestamp = velas[-1]['timestamp']
            cache_key = f"{symbol}_{periodo}_{ultimo_timestamp}"
            
            if cache_key in self.cache_atr:
                return self.cache_atr[cache_key]
        
        highs = [v['maxima'] for v in velas]
        lows = [v['minima'] for v in velas]
        closes = [v['fechamento'] for v in velas]
        
        tr = []
        for i in range(1, len(velas)):
            tr.append(max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])))
        
        atr = np.mean(tr[:periodo])
        for i in range(periodo, len(tr)):
            atr = (atr * (periodo - 1) + tr[i]) / periodo
        
        if symbol and len(velas) > 0:
            self.cache_atr[cache_key] = atr
        
        return atr
    
    def calcular_atr_medio(self, velas, periodo=14, symbol=None):
        """Calcula ATR médio das últimas N velas"""
        if len(velas) < periodo * 2:
            return self.calcular_atr_wilder(velas, periodo, symbol)
        
        if symbol and len(velas) > 0:
            cache_key = f"{symbol}_atr_medio_{periodo}_{velas[-1]['timestamp']}"
            if cache_key in self.cache_atr_medio:
                return self.cache_atr_medio[cache_key]
        
        atrs = []
        for i in range(periodo, len(velas) - periodo, periodo):
            atrs.append(self.calcular_atr_wilder(velas[:i], periodo, symbol))
        
        atr_medio = np.mean(atrs) if atrs else self.calcular_atr_wilder(velas, periodo, symbol)
        
        if symbol:
            self.cache_atr_medio[cache_key] = atr_medio
        
        return atr_medio
    
    def calcular_adx_wilder(self, velas, periodo=14, symbol=None):
        if len(velas) < periodo + 1:
            return 0
        
        if symbol and len(velas) > 0:
            ultimo_timestamp = velas[-1]['timestamp']
            cache_key = f"{symbol}_adx_{periodo}_{ultimo_timestamp}"
            
            if cache_key in self.cache_adx:
                return self.cache_adx[cache_key]
        
        highs = np.array([v['maxima'] for v in velas])
        lows = np.array([v['minima'] for v in velas])
        closes = np.array([v['fechamento'] for v in velas])
        
        tr = []
        plus_dm = []
        minus_dm = []
        
        for i in range(1, len(velas)):
            tr.append(max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])))
            
            up = highs[i] - highs[i-1]
            down = lows[i-1] - lows[i]
            
            if up > down and up > 0:
                plus_dm.append(up)
                minus_dm.append(0)
            elif down > up and down > 0:
                plus_dm.append(0)
                minus_dm.append(down)
            else:
                plus_dm.append(0)
                minus_dm.append(0)
        
        if len(tr) < periodo:
            return 0
        
        atr = np.mean(tr[:periodo])
        plus_di = np.mean(plus_dm[:periodo])
        minus_di = np.mean(minus_dm[:periodo])
        
        dxs = []
        
        for i in range(periodo, len(tr)):
            atr = (atr * (periodo - 1) + tr[i]) / periodo
            plus_di = (plus_di * (periodo - 1) + plus_dm[i]) / periodo
            minus_di = (minus_di * (periodo - 1) + minus_dm[i]) / periodo
            
            plus_di_val = 100 * (plus_di / atr) if atr > 0 else 0
            minus_di_val = 100 * (minus_di / atr) if atr > 0 else 0
            
            soma = plus_di_val + minus_di_val
            dx = 100 * abs(plus_di_val - minus_di_val) / soma if soma > 0 else 0
            dxs.append(dx)
        
        if len(dxs) < periodo:
            adx = np.mean(dxs) if dxs else 0
        else:
            adx = np.mean(dxs[:periodo])
            for dx in dxs[periodo:]:
                adx = ((adx * (periodo - 1)) + dx) / periodo
        
        if symbol and len(velas) > 0:
            self.cache_adx[cache_key] = adx
        
        return adx
    
    def calcular_rsi(self, velas, periodo=14, symbol=None):
        if len(velas) < periodo + 1:
            return 50
        
        if symbol and len(velas) > 0:
            ultimo_timestamp = velas[-1]['timestamp']
            cache_key = f"{symbol}_rsi_{periodo}_{ultimo_timestamp}"
            
            if cache_key in self.cache_rsi:
                return self.cache_rsi[cache_key]
        
        closes = [v['fechamento'] for v in velas]
        ganhos = []
        perdas = []
        
        for i in range(1, len(closes)):
            diferenca = closes[i] - closes[i-1]
            if diferenca > 0:
                ganhos.append(diferenca)
                perdas.append(0)
            else:
                ganhos.append(0)
                perdas.append(abs(diferenca))
        
        if len(ganhos) < periodo:
            return 50
        
        media_ganhos = np.mean(ganhos[:periodo])
        media_perdas = np.mean(perdas[:periodo])
        
        for i in range(periodo, len(ganhos)):
            media_ganhos = (media_ganhos * (periodo - 1) + ganhos[i]) / periodo
            media_perdas = (media_perdas * (periodo - 1) + perdas[i]) / periodo
        
        if media_perdas == 0:
            rsi = 100
        else:
            rs = media_ganhos / media_perdas
            rsi = 100 - (100 / (1 + rs))
        
        if symbol and len(velas) > 0:
            self.cache_rsi[cache_key] = rsi
        
        return rsi

indicadores_cache = IndicadoresComCache()

def calcular_atr_wilder(velas, periodo=14, symbol=None):
    return indicadores_cache.calcular_atr_wilder(velas, periodo, symbol)

def calcular_atr_medio(velas, periodo=14, symbol=None):
    return indicadores_cache.calcular_atr_medio(velas, periodo, symbol)

def calcular_adx_wilder(velas, periodo=14, symbol=None):
    return indicadores_cache.calcular_adx_wilder(velas, periodo, symbol)

def calcular_rsi(velas, periodo=14, symbol=None):
    return indicadores_cache.calcular_rsi(velas, periodo, symbol)

# ============================================
# MARKET STRUCTURE
# ============================================
class MarketStructure:
    def __init__(self):
        self.estrutura_atual = None
        self.ultimo_high = 0
        self.ultimo_low = 0
        self.historico_estrutura = deque(maxlen=50)
    
    def detectar(self, precos):
        if len(precos) < 20:
            return None, None
        
        highs = []
        lows = []
        
        for i in range(2, len(precos)-2):
            if precos[i] > precos[i-1] and precos[i] > precos[i-2] and precos[i] > precos[i+1] and precos[i] > precos[i+2]:
                highs.append((i, precos[i]))
            if precos[i] < precos[i-1] and precos[i] < precos[i-2] and precos[i] < precos[i+1] and precos[i] < precos[i+2]:
                lows.append((i, precos[i]))
        
        if len(highs) < 2 or len(lows) < 2:
            return None, None
        
        ultimo_high = highs[-1][1]
        penultimo_high = highs[-2][1]
        ultimo_low = lows[-1][1]
        penultimo_low = lows[-2][1]
        
        self.ultimo_high = ultimo_high
        self.ultimo_low = ultimo_low
        
        if ultimo_high > penultimo_high and ultimo_low > penultimo_low:
            estrutura = "ALTA"
            detalhe = "HH+HL"
        elif ultimo_high < penultimo_high and ultimo_low < penultimo_low:
            estrutura = "BAIXA"
            detalhe = "LH+LL"
        else:
            estrutura = "LATERAL"
            detalhe = "ESTRUTURA_MISTA"
        
        if len(highs) >= 3 and len(lows) >= 3:
            high_anterior = highs[-3][1]
            low_anterior = lows[-3][1]
            
            if ultimo_high > high_anterior and ultimo_low > low_anterior:
                detalhe += "_BOS_ALTA"
            elif ultimo_high < high_anterior and ultimo_low < low_anterior:
                detalhe += "_BOS_BAIXA"
        
        self.estrutura_atual = estrutura
        self.historico_estrutura.append(estrutura)
        
        return estrutura, detalhe

# ============================================
# FAKE BREAKOUT DETECTOR
# ============================================
class FakeBreakoutDetector:
    def __init__(self, atr_mult=0.2, volume_mult=1.5, forca_minima=0.6):
        self.atr_mult = atr_mult
        self.volume_mult = volume_mult
        self.forca_minima = forca_minima
    
    def detectar(self, vela_atual, vela_anterior, atr, volume_relativo, sinal):
        if sinal == "CALL":
            if vela_atual['fechamento'] <= vela_anterior['maxima']:
                return False, "Não houve breakout"
            
            distancia = vela_atual['fechamento'] - vela_anterior['maxima']
            if distancia < atr * self.atr_mult:
                return False, f"Distância insuficiente: {distancia:.2f}"
            
            if volume_relativo < self.volume_mult:
                return False, f"Volume baixo: {volume_relativo:.1f}x (mínimo {self.volume_mult}x)"
            
            range_vela = vela_atual['maxima'] - vela_atual['minima']
            if range_vela > 0:
                forca_candle = abs(vela_atual['fechamento'] - vela_atual['abertura']) / range_vela
                if forca_candle < self.forca_minima:
                    return False, f"Candle fraco: força {forca_candle:.2f}"
            
            return True, "Breakout válido"
        
        else:
            if vela_atual['fechamento'] >= vela_anterior['minima']:
                return False, "Não houve breakout"
            
            distancia = vela_anterior['minima'] - vela_atual['fechamento']
            if distancia < atr * self.atr_mult:
                return False, f"Distância insuficiente: {distancia:.2f}"
            
            if volume_relativo < self.volume_mult:
                return False, f"Volume baixo: {volume_relativo:.1f}x (mínimo {self.volume_mult}x)"
            
            range_vela = vela_atual['maxima'] - vela_atual['minima']
            if range_vela > 0:
                forca_candle = abs(vela_atual['fechamento'] - vela_atual['abertura']) / range_vela
                if forca_candle < self.forca_minima:
                    return False, f"Candle fraco: força {forca_candle:.2f}"
            
            return True, "Breakout válido"

# ============================================
# AUTO-MACHINE LEARNING
# ============================================
class AutoMachineLearning:
    def __init__(self):
        self.historico_trades = []
        self.pesos_otimizados = {}
        self.ultima_otimizacao = 0
    
    def adicionar_trade(self, trade):
        self.historico_trades.append(trade)
        if len(self.historico_trades) > 200:
            self.historico_trades = self.historico_trades[-200:]
    
    def otimizar_pesos(self, regime_atual):
        agora = time.time()
        if agora - self.ultima_otimizacao < 3600:
            return None
        
        if len(self.historico_trades) < 30:
            return None
        
        trades_regime = [t for t in self.historico_trades if t.get('regime') == regime_atual]
        if len(trades_regime) < 15:
            return None
        
        eficiencia = {
            'tendencia_macro': {'acertos': 0, 'total': 0},
            'volume': {'acertos': 0, 'total': 0},
            'momentum': {'acertos': 0, 'total': 0},
            'breakout': {'acertos': 0, 'total': 0},
            'orderflow': {'acertos': 0, 'total': 0},
            'estrutura': {'acertos': 0, 'total': 0},
        }
        
        for trade in trades_regime:
            for componente in trade.get('componentes', []):
                if componente in eficiencia:
                    eficiencia[componente]['total'] += 1
                    if trade.get('acertou', False):
                        eficiencia[componente]['acertos'] += 1
        
        novos_pesos = {}
        for comp, dados in eficiencia.items():
            if dados['total'] > 0:
                taxa = dados['acertos'] / dados['total']
                novos_pesos[comp] = max(10, min(40, int(taxa * 50)))
            else:
                novos_pesos[comp] = 20
        
        total = sum(novos_pesos.values())
        if total > 0:
            for comp in novos_pesos:
                novos_pesos[comp] = int(novos_pesos[comp] * 100 / total)
        
        self.pesos_otimizados[regime_atual] = novos_pesos
        self.ultima_otimizacao = agora
        
        print(f"{CIANO}🤖 ML: Pesos otimizados para {regime_atual}: {novos_pesos}{RESET}")
        return novos_pesos

# ============================================
# PERFORMANCE MONITOR
# ============================================
class PerformanceMonitor:
    def __init__(self):
        self.metricas = {
            'sharpe_ratio': 0,
            'win_rate': 0,
            'profit_factor': 0,
            'avg_win': 0,
            'avg_loss': 0,
            'max_drawdown': 0,
            'total_trades': 0,
            'expectancy': 0
        }
        self.trades_history = []
        self.equity_curve = [CAPITAL_INICIAL]
    
    def atualizar_metricas(self, trades):
        if not trades:
            return
        
        lucros = [t['pnl'] for t in trades if t.get('pnl', 0) > 0]
        perdas = [t['pnl'] for t in trades if t.get('pnl', 0) < 0]
        
        total_lucros = sum(lucros) if lucros else 0
        total_perdas = abs(sum(perdas)) if perdas else 1
        
        self.metricas['win_rate'] = (len(lucros) / len(trades) * 100) if trades else 0
        self.metricas['profit_factor'] = total_lucros / total_perdas if total_perdas > 0 else 0
        self.metricas['avg_win'] = np.mean(lucros) if lucros else 0
        self.metricas['avg_loss'] = np.mean(perdas) if perdas else 0
        self.metricas['total_trades'] = len(trades)
        self.metricas['expectancy'] = (self.metricas['win_rate'] / 100 * self.metricas['avg_win']) - ((100 - self.metricas['win_rate']) / 100 * abs(self.metricas['avg_loss']))
        
        retornos = [t.get('pnl', 0) / 100 for t in trades]
        if len(retornos) > 1 and np.std(retornos) > 0:
            self.metricas['sharpe_ratio'] = np.mean(retornos) / (np.std(retornos) + 0.001) * np.sqrt(252)
    
    def mostrar_relatorio(self):
        print(f"\n{CIANO}{'='*80}{RESET}")
        print(f"{CIANO_NEGRITO}📈 RELATÓRIO DE PERFORMANCE V19{RESET}")
        print(f"{CIANO}{'='*80}{RESET}")
        print(f"   Sharpe Ratio: {self.metricas['sharpe_ratio']:.2f}")
        print(f"   Win Rate: {self.metricas['win_rate']:.1f}%")
        print(f"   Profit Factor: {self.metricas['profit_factor']:.2f}")
        print(f"   Expectancy: {self.metricas['expectancy']:.2f}%")
        print(f"   Avg Win: {self.metricas['avg_win']:.2f}%")
        print(f"   Avg Loss: {self.metricas['avg_loss']:.2f}%")
        print(f"   Max Drawdown: {self.metricas['max_drawdown']:.1f}%")
        print(f"   Total Trades: {self.metricas['total_trades']}")
        print(f"{CIANO}{'='*80}{RESET}")

# ============================================
# GERENCIAMENTO DE RISCO DINÂMICO
# ============================================
class GerenciamentoRiscoDinamico:
    def __init__(self):
        self.historico_trades = deque(maxlen=50)
        self.drawdown_atual = 0
        self.max_drawdown = 0
        self.sequencia_perdas = 0
        self.fator_risco = 1.0
        self.drawdown_diario = 0
        self.capital_inicio_dia = CAPITAL_INICIAL
        self.ultimo_reset_dia = datetime.now().date()
        self.pnl_dia = 0
        self.trades_dia = 0
    
    def atualizar_risco(self, pnl_percentual, capital_atual):
        hoje = datetime.now().date()
        if hoje != self.ultimo_reset_dia:
            self.drawdown_diario = 0
            self.pnl_dia = 0
            self.trades_dia = 0
            self.capital_inicio_dia = capital_atual
            self.ultimo_reset_dia = hoje
        
        self.historico_trades.append(pnl_percentual)
        self.pnl_dia += pnl_percentual
        self.trades_dia += 1
        
        if pnl_percentual < 0:
            self.sequencia_perdas += 1
            self.drawdown_atual += abs(pnl_percentual)
            if self.pnl_dia < 0:
                self.drawdown_diario = abs(self.pnl_dia)
        else:
            self.sequencia_perdas = 0
            self.drawdown_atual = max(0, self.drawdown_atual - pnl_percentual)
        
        self.max_drawdown = max(self.max_drawdown, self.drawdown_atual)
        
        if self.sequencia_perdas >= 3:
            self.fator_risco = max(0.3, 1.0 - (self.sequencia_perdas * 0.15))
        elif self.drawdown_diario > MAX_DRAWDOWN_DIA * 100:
            self.fator_risco = max(0.2, 1.0 - (self.drawdown_diario / 100))
        elif self.drawdown_atual > 5:
            self.fator_risco = max(0.5, 1.0 - (self.drawdown_atual / 20))
        else:
            self.fator_risco = min(1.5, self.fator_risco + 0.02)
        
        return self.fator_risco
    
    def deve_reduzir_risco(self):
        if self.sequencia_perdas >= 4:
            return True, f"Sequência de {self.sequencia_perdas} perdas"
        if self.drawdown_atual > 8:
            return True, f"Drawdown de {self.drawdown_atual:.1f}%"
        if self.drawdown_diario > MAX_DRAWDOWN_DIA * 100:
            return True, f"Drawdown diário de {self.drawdown_diario:.1f}% excedeu limite de {MAX_DRAWDOWN_DIA*100:.0f}%"
        return False, ""
    
    def get_ajuste_tamanho(self):
        if self.sequencia_perdas >= 3:
            return 0.5
        elif self.drawdown_diario > MAX_DRAWDOWN_DIA * 50:
            return 0.7
        return 1.0

# ============================================
# DRAWDOWN PROTECTOR (V18)
# ============================================
class DrawdownProtector:
    def __init__(self, capital_inicial):
        self.capital_inicial = capital_inicial
        self.capital_maximo = capital_inicial
        self.drawdown_atual = 0
        self.drawdown_maximo = 0
        self.losses_consecutivos = 0
        self.losses_hoje = 0
        self.pnl_hoje = 0
        self.pnl_semana = 0
        self.data_inicio_semana = datetime.now().date()
        self.parado = False
        self.motivo_parada = ""
    
    def atualizar(self, pnl_percentual, capital_atual):
        if self.parado:
            return True, self.motivo_parada
        
        if capital_atual > self.capital_maximo:
            self.capital_maximo = capital_atual
        
        self.drawdown_atual = (self.capital_maximo - capital_atual) / self.capital_maximo * 100
        self.drawdown_maximo = max(self.drawdown_maximo, self.drawdown_atual)
        
        if pnl_percentual < 0:
            self.losses_consecutivos += 1
            self.losses_hoje += 1
            self.pnl_hoje += pnl_percentual
            self.pnl_semana += pnl_percentual
        else:
            self.losses_consecutivos = 0
            self.pnl_hoje += pnl_percentual
            self.pnl_semana += pnl_percentual
        
        hoje = datetime.now().date()
        if hoje != self.data_inicio_semana:
            self.pnl_semana = 0
            self.losses_hoje = 0
            self.data_inicio_semana = hoje
        
        return self.verificar_limites()
    
    def verificar_limites(self):
        if self.pnl_hoje < -MAX_DRAWDOWN_DIA_PERCENT * 100:
            self.parado = True
            self.motivo_parada = f"Drawdown diário excedido: {abs(self.pnl_hoje):.1f}%"
            return True, self.motivo_parada
        
        if self.pnl_semana < -MAX_DRAWDOWN_SEMANA_PERCENT * 100:
            self.parado = True
            self.motivo_parada = f"Drawdown semanal excedido: {abs(self.pnl_semana):.1f}%"
            return True, self.motivo_parada
        
        if self.losses_consecutivos >= MAX_LOSSES_SEQUENCIAIS:
            self.parado = True
            self.motivo_parada = f"{self.losses_consecutivos} losses consecutivos"
            return True, self.motivo_parada
        
        if self.losses_hoje >= MAX_LOSSES_DIA:
            self.parado = True
            self.motivo_parada = f"{self.losses_hoje} losses no dia"
            return True, self.motivo_parada
        
        return False, ""
    
    def resetar(self):
        self.parado = False
        self.motivo_parada = ""
        self.losses_consecutivos = 0
        print(f"{VERDE}✅ Drawdown protector resetado{RESET}")

# ============================================
# OPEN INTEREST ANALYZER (V18)
# ============================================
class OpenInterestAnalyzer:
    def __init__(self, robo):
        self.robo = robo
        self.oi_historico = deque(maxlen=100)
        self.ultimo_oi = {}
        self.cache_oi = {}
        
    def obter_open_interest(self, symbol):
        try:
            symbol_futures = symbol.replace('USDT', 'USDT')
            oi_data = self.robo.binance.client.futures_open_interest(symbol=symbol_futures)
            oi_usdt = float(oi_data['openInterest']) * self.robo.dados[symbol]['preco_atual']
            return oi_usdt
        except Exception as e:
            return 0
    
    def analisar_mudanca(self, symbol, oi_atual):
        if symbol in self.ultimo_oi:
            oi_anterior = self.ultimo_oi[symbol]
            if oi_anterior > 0:
                mudanca = (oi_atual - oi_anterior) / oi_anterior
                return mudanca
        return 0
    
    def get_sinal_oi(self, symbol, tendencia_preco):
        oi_atual = self.obter_open_interest(symbol)
        if oi_atual < MINIMO_OI_USDT:
            return None, f"OI baixo: ${oi_atual/1_000_000:.1f}M"
        
        mudanca_oi = self.analisar_mudanca(symbol, oi_atual)
        self.ultimo_oi[symbol] = oi_atual
        
        if tendencia_preco == "ALTA":
            if mudanca_oi > OI_MUDANCA_SIGNIFICATIVA:
                return "CALL", f"OI +{mudanca_oi*100:.1f}% + preço alta = continuação"
            elif mudanca_oi < -OI_MUDANCA_SIGNIFICATIVA:
                return "PUT", f"OI {mudanca_oi*100:.1f}% + preço alta = possível topo"
        
        elif tendencia_preco == "BAIXA":
            if mudanca_oi < -OI_MUDANCA_SIGNIFICATIVA:
                return "PUT", f"OI {mudanca_oi*100:.1f}% + preço baixa = continuação"
            elif mudanca_oi > OI_MUDANCA_SIGNIFICATIVA:
                return "CALL", f"OI +{mudanca_oi*100:.1f}% + preço baixa = possível fundo"
        
        return None, f"OI neutro: {mudanca_oi*100:+.1f}%"

# ============================================
# CLIENTE BINANCE
# ============================================
class BinanceClient:
    def __init__(self):
        self.client = None
        self.lock = Lock()
        self.conectado = False
        self.orderbook_cache = {}
        self.orderbook_timestamp = {}
        self.ultima_sincronizacao = {}  # V19: controle de sincronização
        
    def conectar(self):
        try:
            from binance.client import Client
            self.client = Client(BINANCE_API_KEY, BINANCE_SECRET_KEY)
            self.client.ping()
            self.conectado = True
            print(f"{VERDE}✅ Binance REST conectada{RESET}")
            return True
        except Exception as e:
            print(f"{VERMELHO}❌ Binance REST: {e}{RESET}")
            return False
    
    def obter_velas(self, symbol, timeframe, limit=300):
        if not self.conectado or not self.client:
            return None
        with self.lock:
            try:
                interval_map = {
                    '5m': self.client.KLINE_INTERVAL_5MINUTE,
                    '15m': self.client.KLINE_INTERVAL_15MINUTE,
                    '1h': self.client.KLINE_INTERVAL_1HOUR,
                    '4h': self.client.KLINE_INTERVAL_4HOUR,
                }
                klines = self.client.get_klines(
                    symbol=symbol, 
                    interval=interval_map.get(timeframe, self.client.KLINE_INTERVAL_1HOUR), 
                    limit=limit
                )
                velas = []
                for k in klines:
                    velas.append({
                        'timestamp': k[0],
                        'abertura': float(k[1]),
                        'maxima': float(k[2]),
                        'minima': float(k[3]),
                        'fechamento': float(k[4]),
                        'volume': float(k[5])
                    })
                return velas
            except Exception as e:
                return None
    
    def sincronizar_velas_perdidas(self, symbol, timeframe, ultimo_timestamp):
        """V19: Sincroniza velas perdidas após reconexão WebSocket"""
        try:
            velas = self.obter_velas(symbol, timeframe, limit=100)
            if not velas:
                return []
            
            velas_novas = []
            for vela in velas:
                if vela['timestamp'] > ultimo_timestamp:
                    velas_novas.append(vela)
            
            if velas_novas:
                print(f"{CIANO}🔄 Sincronizadas {len(velas_novas)} velas perdidas para {symbol} {timeframe}{RESET}")
            
            return velas_novas
        except Exception as e:
            print(f"{VERMELHO}❌ Erro na sincronização: {e}{RESET}")
            return []
    
    def obter_order_book_com_cache(self, symbol, limit=100):
        agora = time.time()
        
        if symbol in self.orderbook_timestamp:
            if agora - self.orderbook_timestamp[symbol] < 5:
                return self.orderbook_cache.get(symbol)
        
        if not self.conectado or not self.client:
            return None
        
        with self.lock:
            try:
                ticker = self.client.get_orderbook_ticker(symbol=symbol)
                depth = self.client.get_order_book(symbol=symbol, limit=limit)
                
                depth['best_bid'] = float(ticker['bidPrice'])
                depth['best_ask'] = float(ticker['askPrice'])
                depth['bids'] = depth.get('bids', [])
                depth['asks'] = depth.get('asks', [])
                
                self.orderbook_cache[symbol] = depth
                self.orderbook_timestamp[symbol] = agora
                return depth
            except Exception as e:
                return self.orderbook_cache.get(symbol)
    
    def obter_spread_real(self, symbol):
        try:
            ticker = self.client.get_orderbook_ticker(symbol=symbol)
            bid = float(ticker['bidPrice'])
            ask = float(ticker['askPrice'])
            if bid > 0:
                spread = (ask - bid) / bid
                return spread
        except:
            pass
        return 0.001
    
    def obter_liquidez_24h(self, symbol):
        try:
            ticker = self.client.get_ticker(symbol=symbol)
            volume_24h = float(ticker['quoteVolume'])
            return volume_24h
        except:
            return 0

# ============================================
# WEBSOCKET COM SINCRONIZAÇÃO (V19)
# ============================================
class BinanceWebSocket:
    def __init__(self, robo):
        self.robo = robo
        self.ws = None
        self.thread = None
        self.rodando = True
        self.reconectando = False
        self.reconect_lock = Lock()
        self.executor = ThreadPoolExecutor(max_workers=MAX_THREADS)
        self.processando = set()
        self.symbols = [ativo['symbol'].lower() for ativo in robo.ATIVOS if ativo['ativo']]
        self.ultimo_timestamp_por_stream = {}  # V19: controle de timestamps
        
    def iniciar(self):
        streams = []
        for symbol in self.symbols:
            streams.append(f"{symbol}@kline_15m")
            streams.append(f"{symbol}@kline_1h")
            streams.append(f"{symbol}@kline_4h")
        
        stream_name = "/".join(streams)
        url = f"wss://stream.binance.com:9443/stream?streams={stream_name}"
        
        print(f"{CIANO}🔌 Conectando WebSocket...{RESET}")
        
        self.ws = websocket.WebSocketApp(
            url,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open
        )
        
        self.thread = threading.Thread(target=self.ws.run_forever, kwargs={'ping_interval': 20, 'ping_timeout': 10}, daemon=True)
        self.thread.start()
        
    def on_open(self, ws):
        print(f"{VERDE}✅ WebSocket conectado!{RESET}")
        # V19: Resetar timestamps na reconexão
        self.ultimo_timestamp_por_stream.clear()
    
    def on_message(self, ws, message):
        try:
            data = json.loads(message)
            if 'data' in data:
                stream = data['stream']
                vela = data['data']['k']
                
                if vela.get('x', False):
                    symbol = vela['s'].upper()
                    timeframe = stream.split('@')[1].replace('kline_', '')
                    timestamp_fechamento = vela['t']
                    
                    # V19: Verificar se há velas perdidas
                    stream_key = f"{symbol}_{timeframe}"
                    ultimo_ts = self.ultimo_timestamp_por_stream.get(stream_key, 0)
                    
                    if ultimo_ts > 0 and timestamp_fechamento > ultimo_ts + self.get_timeframe_ms(timeframe) * 2:
                        # Perdeu pelo menos 2 velas, sincronizar
                        print(f"{AMARELO}⚠️ Possível perda de velas para {symbol} {timeframe}. Sincronizando...{RESET}")
                        velas_perdidas = self.robo.binance.sincronizar_velas_perdidas(symbol, timeframe, ultimo_ts)
                        for vela_perdida in velas_perdidas:
                            self.processar_vela(symbol, vela_perdida, timeframe)
                    
                    self.ultimo_timestamp_por_stream[stream_key] = timestamp_fechamento
                    
                    key = f"{symbol}_{timeframe}"
                    if key in self.processando:
                        return
                    
                    self.processando.add(key)
                    self.executor.submit(self.processar_vela_atrasada, symbol, vela, timeframe, key)
        except Exception as e:
            pass
    
    def get_timeframe_ms(self, timeframe):
        if timeframe == '15m':
            return 15 * 60 * 1000
        elif timeframe == '1h':
            return 60 * 60 * 1000
        elif timeframe == '4h':
            return 4 * 60 * 60 * 1000
        return 60 * 60 * 1000
    
    def processar_vela(self, symbol, vela_data, timeframe):
        """Processa uma vela individual"""
        if timeframe == '15m':
            self.robo.adicionar_vela_websocket(symbol, vela_data, '15m')
            self.robo.atualizar_preco_websocket(symbol, vela_data['fechamento'])
            self.robo.verificar_sinal_apos_vela(symbol)
        elif timeframe == '1h':
            self.robo.adicionar_vela_websocket(symbol, vela_data, '1h')
        elif timeframe == '4h':
            self.robo.adicionar_vela_websocket(symbol, vela_data, '4h')
    
    def processar_vela_atrasada(self, symbol, vela, timeframe, key):
        try:
            timestamp_fechamento = vela['t'] / 1000
            if timeframe == '15m':
                timestamp_fechamento += 15 * 60
            elif timeframe == '1h':
                timestamp_fechamento += 60 * 60
            elif timeframe == '4h':
                timestamp_fechamento += 4 * 60 * 60
            
            while time.time() < timestamp_fechamento + 1:
                time.sleep(0.2)
            
            vela_data = {
                'timestamp': vela['t'],
                'abertura': float(vela['o']),
                'maxima': float(vela['h']),
                'minima': float(vela['l']),
                'fechamento': float(vela['c']),
                'volume': float(vela['v'])
            }
            
            self.processar_vela(symbol, vela_data, timeframe)
        finally:
            self.processando.discard(key)
    
    def on_error(self, ws, error):
        pass
    
    def on_close(self, ws, close_status_code, close_msg):
        if not self.rodando:
            return
        
        with self.reconect_lock:
            if self.reconectando:
                return
            self.reconectando = True
        
        print(f"{AMARELO}⚠️ WebSocket fechado. Reconectando em 5s...{RESET}")
        time.sleep(5)
        
        if self.ws:
            try:
                self.ws.close()
            except:
                pass
        
        self.iniciar()
        
        with self.reconect_lock:
            self.reconectando = False
    
    def parar(self):
        self.rodando = False
        self.executor.shutdown(wait=False)
        if self.ws:
            try:
                self.ws.close()
            except:
                pass

# ============================================
# DETECTOR DE REGIME DE MERCADO
# ============================================
class MarketRegimeDetector:
    def __init__(self):
        self.regime_atual = 'indefinido'
        self.volatilidade_atual = 0
        self.adx_atual = 0
        self.historico_regime = deque(maxlen=100)
    
    def detectar(self, velas):
        if len(velas) < 50:
            return 'indefinido', 0, 0
        
        precos = [v['fechamento'] for v in velas[-50:]]
        adx = calcular_adx_wilder(velas[-30:], 14)
        self.adx_atual = adx
        
        retornos = [(precos[i] - precos[i-1]) / precos[i-1] for i in range(1, len(precos))]
        volatilidade = np.std(retornos) * 100
        self.volatilidade_atual = volatilidade
        
        chop = calcular_chop_index(precos, 20)
        
        if adx >= REGIME_LIMIARES['tendencia_forte'] and chop < 0.5:
            regime_base = 'tendencia_forte'
        elif adx >= REGIME_LIMIARES['tendencia_fraca'] and chop < 0.6:
            regime_base = 'tendencia_fraca'
        elif chop > CHOP_LIMIAR:
            regime_base = 'lateral'
        else:
            regime_base = 'tendencia_media'
        
        if volatilidade >= REGIME_LIMIARES['vol_alta']:
            regime_vol = 'alta_vol'
        elif volatilidade <= REGIME_LIMIARES['vol_baixa']:
            regime_vol = 'baixa_vol'
        else:
            regime_vol = 'media_vol'
        
        self.regime_atual = f"{regime_base}_{regime_vol}"
        self.historico_regime.append(self.regime_atual)
        
        return self.regime_atual, adx, volatilidade
    
    def get_pesos_adaptativos(self, auto_ml=None):
        pesos = PESOS_REGIME['tendencia'].copy()
        
        if 'lateral' in self.regime_atual:
            pesos.update(PESOS_REGIME['lateral'])
        if 'alta_vol' in self.regime_atual:
            pesos.update(PESOS_REGIME['alta_vol'])
        if 'baixa_vol' in self.regime_atual:
            pesos.update(PESOS_REGIME['baixa_vol'])
        
        if auto_ml and self.regime_atual in auto_ml.pesos_otimizados:
            ml_pesos = auto_ml.pesos_otimizados[self.regime_atual]
            for comp in pesos:
                if comp in ml_pesos:
                    pesos[comp] = ml_pesos[comp]
        
        return pesos
    
    def deve_ignorar_trade(self):
        if self.adx_atual < REGIME_LIMIARES['lateral']:
            return True, f"Mercado lateral (ADX: {self.adx_atual:.0f})"
        
        if self.volatilidade_atual < REGIME_LIMIARES['vol_baixa']:
            return True, f"Baixa volatilidade ({self.volatilidade_atual:.2f}%)"
        
        return False, ""

# ============================================
# POSITION SIZING
# ============================================
class PositionSizing:
    def __init__(self, capital_inicial):
        self.capital = capital_inicial
        self.historico_capital = deque(maxlen=100)
        self.historico_capital.append(capital_inicial)
    
    def atualizar_capital(self, novo_capital):
        self.capital = novo_capital
        self.historico_capital.append(novo_capital)
    
    def calcular_quantidade(self, preco, stop_percentual, ajuste_risco=1.0):
        risco_em_dinheiro = self.capital * RISCO_POR_TRADE * ajuste_risco
        risco_por_contrato = preco * stop_percentual
        quantidade = risco_em_dinheiro / risco_por_contrato if risco_por_contrato > 0 else 0
        return max(0, quantidade)
    
    def get_valor_trade(self, preco, stop_percentual, ajuste_risco=1.0):
        quantidade = self.calcular_quantidade(preco, stop_percentual, ajuste_risco)
        valor_trade = quantidade * preco
        valor_maximo = self.capital * MAX_ALAVANCAGEM
        return min(valor_trade, valor_maximo)

# ============================================
# TRAILING STOP
# ============================================
class TrailingStopATR:
    def __init__(self, preco_entrada, direcao, atv, atr):
        self.preco_entrada = preco_entrada
        self.direcao = direcao
        self.atv = atv
        self.atr = atr
        self.melhor_preco = preco_entrada
        self.stop_atual = preco_entrada - (atr * 1.5) if direcao == 'CALL' else preco_entrada + (atr * 1.5)
        self.ativo_aberto = True
        self.tp = TAKE_PROFIT_BASE.get(atv, 0.015)
        self.tp_preco = preco_entrada * (1 + self.tp) if direcao == 'CALL' else preco_entrada * (1 - self.tp)
    
    def atualizar(self, preco_atual, novo_atr):
        if not self.ativo_aberto:
            return None, 0
        
        self.atr = novo_atr
        
        if self.direcao == 'CALL':
            if preco_atual > self.melhor_preco:
                self.melhor_preco = preco_atual
                novo_stop = self.melhor_preco - (self.atr * 1.5)
                if novo_stop > self.stop_atual:
                    self.stop_atual = novo_stop
            
            if preco_atual >= self.tp_preco:
                self.ativo_aberto = False
                return 'TAKE_PROFIT', (preco_atual - self.preco_entrada) / self.preco_entrada * 100
            
            if preco_atual <= self.stop_atual:
                self.ativo_aberto = False
                return 'TRAILING_STOP', (preco_atual - self.preco_entrada) / self.preco_entrada * 100
        
        else:
            if preco_atual < self.melhor_preco:
                self.melhor_preco = preco_atual
                novo_stop = self.melhor_preco + (self.atr * 1.5)
                if novo_stop < self.stop_atual:
                    self.stop_atual = novo_stop
            
            if preco_atual <= self.tp_preco:
                self.ativo_aberto = False
                return 'TAKE_PROFIT', (self.preco_entrada - preco_atual) / self.preco_entrada * 100
            
            if preco_atual >= self.stop_atual:
                self.ativo_aberto = False
                return 'TRAILING_STOP', (self.preco_entrada - preco_atual) / self.preco_entrada * 100
        
        return None, 0

# ============================================
# SISTEMA DE CONFLUÊNCIA (V19 - SCORE MAIS EXIGENTE)
# ============================================
class SistemaConfluencia:
    def __init__(self, regime_detector, auto_ml=None):
        self.regime_detector = regime_detector
        self.auto_ml = auto_ml
    
    def calcular_confluencia(self, dados):
        confirmacoes = []
        pesos = self.regime_detector.get_pesos_adaptativos(self.auto_ml)
        
        if dados.get('tendencia_4h') == dados.get('tendencia_1h') and dados.get('tendencia_4h') != "LATERAL":
            confirmacoes.append({
                'nome': 'Tendência Alinhada',
                'direcao': 'CALL' if dados['tendencia_4h'] == "ALTA" else 'PUT',
                'peso': pesos.get('tendencia_macro', 25)
            })
        
        if dados.get('volume_relativo', 0) > VOLUME_MINIMO:
            if dados.get('tendencia_15m') == "ALTA":
                confirmacoes.append({'nome': 'Volume Institucional', 'direcao': 'CALL', 'peso': pesos.get('volume', 20)})
            elif dados.get('tendencia_15m') == "BAIXA":
                confirmacoes.append({'nome': 'Volume Institucional', 'direcao': 'PUT', 'peso': pesos.get('volume', 20)})
        
        if dados.get('momentum_score', 0) > 0.3:
            confirmacoes.append({'nome': 'Momentum Acelerando', 'direcao': 'CALL', 'peso': pesos.get('momentum', 15)})
        elif dados.get('momentum_score', 0) < -0.3:
            confirmacoes.append({'nome': 'Momentum Desacelerando', 'direcao': 'PUT', 'peso': pesos.get('momentum', 15)})
        
        if dados.get('breakout_valido', False):
            confirmacoes.append({'nome': f"Breakout {dados.get('breakout_motivo', 'Válido')}", 
                                'direcao': dados.get('sinal_breakout', 'CALL'), 
                                'peso': pesos.get('breakout', 20)})
        
        if dados.get('imbalance', 0) > 0.1 and not dados.get('absorcao', False):
            confirmacoes.append({'nome': 'OrderFlow Comprador', 'direcao': 'CALL', 'peso': pesos.get('orderflow', 20)})
        elif dados.get('imbalance', 0) < -0.1 and not dados.get('absorcao', False):
            confirmacoes.append({'nome': 'OrderFlow Vendedor', 'direcao': 'PUT', 'peso': pesos.get('orderflow', 20)})
        
        if dados.get('estrutura_mercado') == 'ALTA':
            confirmacoes.append({'nome': f"Estrutura ALTA ({dados.get('detalhe_estrutura', 'HH+HL')})", 
                                'direcao': 'CALL', 'peso': 25})
        elif dados.get('estrutura_mercado') == 'BAIXA':
            confirmacoes.append({'nome': f"Estrutura BAIXA ({dados.get('detalhe_estrutura', 'LH+LL')})", 
                                'direcao': 'PUT', 'peso': 25})
        
        if dados.get('divergencia_rsi') == 'DIVERGENCIA_ALTA':
            confirmacoes.append({'nome': 'Divergência RSI Alta', 'direcao': 'CALL', 'peso': 15})
        elif dados.get('divergencia_rsi') == 'DIVERGENCIA_BAIXA':
            confirmacoes.append({'nome': 'Divergência RSI Baixa', 'direcao': 'PUT', 'peso': 15})
        
        if dados.get('suporte_proximo') and dados.get('tendencia_15m') == 'BAIXA':
            confirmacoes.append({'nome': 'Suporte Próximo', 'direcao': 'CALL', 'peso': 10})
        if dados.get('resistencia_proxima') and dados.get('tendencia_15m') == 'ALTA':
            confirmacoes.append({'nome': 'Resistência Próxima', 'direcao': 'PUT', 'peso': 10})
        
        # V19: VWAP como confirmação
        if dados.get('vwap_valido', False):
            direcao = 'CALL' if dados.get('vwap_sinal') == 'ACIMA' else 'PUT'
            confirmacoes.append({'nome': f"VWAP ({dados.get('vwap_sinal')})", 'direcao': direcao, 'peso': 20})
        
        votos_call = sum(c['peso'] for c in confirmacoes if c['direcao'] == 'CALL')
        votos_put = sum(c['peso'] for c in confirmacoes if c['direcao'] == 'PUT')
        
        total_votos = votos_call + votos_put
        if total_votos > 0:
            prob_call = (votos_call / total_votos) * 100
        else:
            prob_call = 50
        
        # V19: LIMIAR MAIS EXIGENTE (50 em vez de 40)
        limiar = LIMIAR_CONFLUENCIA
        
        if votos_call >= limiar:
            return 'CALL', votos_call, confirmacoes, prob_call
        elif votos_put >= limiar:
            return 'PUT', votos_put, confirmacoes, prob_call
        else:
            return None, max(votos_call, votos_put), confirmacoes, prob_call

# ============================================
# MONITOR CENTRAL DE TRADES
# ============================================
class TradeMonitor:
    def __init__(self, robo):
        self.robo = robo
        self.rodando = True
        self.thread = None
    
    def iniciar(self):
        self.thread = threading.Thread(target=self.monitorar, daemon=True)
        self.thread.start()
        print(f"{VERDE}✅ Trade Monitor iniciado{RESET}")
    
    def monitorar(self):
        while self.rodando:
            try:
                time.sleep(1)
                
                with self.robo.trade_lock:
                    trades_para_remover = []
                    
                    for trade_id, trade in self.robo.trades_abertos.items():
                        if time.time() - trade['timestamp'] > TIMEOUT_TRADE:
                            trades_para_remover.append(trade_id)
                            continue
                        
                        symbol = trade['symbol']
                        preco_atual = self.robo.dados.get(symbol, {}).get('preco_atual', 0)
                        
                        if preco_atual > 0:
                            velas = list(self.robo.dados[symbol]['velas_15m'])
                            if len(velas) > 0:
                                novo_atr = calcular_atr_wilder(velas, 14, symbol)
                                sinal = trade['sinal']
                                preco_entrada = trade['preco_entrada']
                                
                                if sinal == 'CALL':
                                    if preco_atual >= trade['tp_preco']:
                                        pnl = (preco_atual - preco_entrada) / preco_entrada * 100
                                        self.robo.finalizar_trade(trade_id, preco_atual, pnl, 'TAKE_PROFIT')
                                        trades_para_remover.append(trade_id)
                                    elif preco_atual <= trade['stop_atual']:
                                        pnl = (preco_atual - preco_entrada) / preco_entrada * 100
                                        self.robo.finalizar_trade(trade_id, preco_atual, pnl, 'STOP_LOSS')
                                        trades_para_remover.append(trade_id)
                                    else:
                                        if preco_atual > trade['melhor_preco']:
                                            trade['melhor_preco'] = preco_atual
                                            novo_stop = trade['melhor_preco'] - (novo_atr * 1.5)
                                            if novo_stop > trade['stop_atual']:
                                                trade['stop_atual'] = novo_stop
                                else:
                                    if preco_atual <= trade['tp_preco']:
                                        pnl = (preco_entrada - preco_atual) / preco_entrada * 100
                                        self.robo.finalizar_trade(trade_id, preco_atual, pnl, 'TAKE_PROFIT')
                                        trades_para_remover.append(trade_id)
                                    elif preco_atual >= trade['stop_atual']:
                                        pnl = (preco_entrada - preco_atual) / preco_entrada * 100
                                        self.robo.finalizar_trade(trade_id, preco_atual, pnl, 'STOP_LOSS')
                                        trades_para_remover.append(trade_id)
                                    else:
                                        if preco_atual < trade['melhor_preco']:
                                            trade['melhor_preco'] = preco_atual
                                            novo_stop = trade['melhor_preco'] + (novo_atr * 1.5)
                                            if novo_stop < trade['stop_atual']:
                                                trade['stop_atual'] = novo_stop
                    
                    for trade_id in trades_para_remover:
                        if trade_id in self.robo.trades_abertos:
                            del self.robo.trades_abertos[trade_id]
                            
            except Exception as e:
                pass
    
    def parar(self):
        self.rodando = False
        if self.thread:
            self.thread.join(timeout=2)

# ============================================
# BACKTEST ENGINE
# ============================================
class BacktestEngine:
    def __init__(self, robo):
        self.robo = robo
    
    def executar_backtest(self, symbol, dias=5):
        dados = self.robo.dados[symbol]
        
        if len(dados['velas_15m']) < 200:
            return None
        
        velas_backtest = list(dados['velas_15m'])[-dias*96:]
        
        acertos = 0
        erros = 0
        lucro_total = 0
        
        for i in range(100, len(velas_backtest)-10):
            velas_parciais = velas_backtest[:i]
            velas_original = dados['velas_15m']
            dados['velas_15m'] = deque(velas_parciais, maxlen=300)
            
            resultado = self.robo.gerar_sinal(symbol)
            
            if resultado[0] and resultado[1] >= CONFIANCA_MINIMA:
                sinal = resultado[0]
                preco_entrada = velas_parciais[-1]['fechamento']
                stop = resultado[3]
                tp = resultado[4]
                
                for j in range(i+1, min(i+24, len(velas_backtest))):
                    preco_atual = velas_backtest[j]['fechamento']
                    
                    if sinal == "CALL":
                        if preco_atual >= preco_entrada * (1 + tp):
                            pnl = tp * 100
                            if pnl > 0:
                                acertos += 1
                            else:
                                erros += 1
                            lucro_total += pnl
                            break
                        elif preco_atual <= preco_entrada * (1 - stop):
                            pnl = -stop * 100
                            erros += 1
                            lucro_total += pnl
                            break
                    else:
                        if preco_atual <= preco_entrada * (1 - tp):
                            pnl = tp * 100
                            acertos += 1
                            lucro_total += pnl
                            break
                        elif preco_atual >= preco_entrada * (1 + stop):
                            pnl = -stop * 100
                            erros += 1
                            lucro_total += pnl
                            break
            
            dados['velas_15m'] = velas_original
        
        total = acertos + erros
        taxa = (acertos / total * 100) if total > 0 else 0
        
        return {
            'trades': total,
            'acertos': acertos,
            'erros': erros,
            'taxa_acerto': taxa,
            'lucro_total': lucro_total
        }
    
    def otimizar_parametros(self, symbol):
        dados = self.robo.dados[symbol]
        if len(dados['velas_15m']) < 200:
            return None
        
        melhores_parametros = None
        melhor_lucro = -float('inf')
        
        tp_opcoes = [0.005, 0.008, 0.010, 0.012, 0.015]
        sl_opcoes = [0.003, 0.005, 0.006, 0.008, 0.010]
        
        velas_original = dados['velas_15m']
        velas_backtest = list(velas_original)[-200:]
        
        for tp in tp_opcoes:
            for sl in sl_opcoes:
                if tp/sl > 2.5:
                    continue
                
                tp_original = TAKE_PROFIT_BASE.get(symbol, 0.008)
                sl_original = STOP_LOSS_BASE.get(symbol, 0.005)
                
                TAKE_PROFIT_BASE[symbol] = tp
                STOP_LOSS_BASE[symbol] = sl
                
                acertos = 0
                erros = 0
                lucro_total = 0
                
                for i in range(100, len(velas_backtest)-10):
                    velas_parciais = velas_backtest[:i]
                    dados['velas_15m'] = deque(velas_parciais, maxlen=300)
                    
                    resultado = self.robo.gerar_sinal(symbol)
                    
                    if resultado[0] and resultado[1] >= CONFIANCA_MINIMA:
                        sinal = resultado[0]
                        preco_entrada = velas_parciais[-1]['fechamento']
                        
                        for j in range(i+1, min(i+24, len(velas_backtest))):
                            preco_atual = velas_backtest[j]['fechamento']
                            
                            if sinal == "CALL":
                                if preco_atual >= preco_entrada * (1 + tp):
                                    lucro_total += tp * 100
                                    acertos += 1
                                    break
                                elif preco_atual <= preco_entrada * (1 - sl):
                                    lucro_total += -sl * 100
                                    erros += 1
                                    break
                            else:
                                if preco_atual <= preco_entrada * (1 - tp):
                                    lucro_total += tp * 100
                                    acertos += 1
                                    break
                                elif preco_atual >= preco_entrada * (1 + sl):
                                    lucro_total += -sl * 100
                                    erros += 1
                                    break
                
                if lucro_total > melhor_lucro:
                    melhor_lucro = lucro_total
                    melhores_parametros = {'tp': tp, 'sl': sl, 'lucro': lucro_total}
                
                TAKE_PROFIT_BASE[symbol] = tp_original
                STOP_LOSS_BASE[symbol] = sl_original
        
        dados['velas_15m'] = velas_original
        
        if melhores_parametros and melhores_parametros['lucro'] > 0:
            return melhores_parametros
        
        return None

# ============================================
# ROBÔ PRINCIPAL V19 COMPLETO
# ============================================
class RoboInstitucionalV19Completo:
    def __init__(self):
        self.binance = BinanceClient()
        self.position_sizing = PositionSizing(CAPITAL_INICIAL)
        self.ws = None
        self.trade_monitor = None
        self.backtest_engine = None
        self.db = Database()
        self.auto_ml = AutoMachineLearning()
        self.performance_monitor = PerformanceMonitor()
        self.gerenciamento_risco = GerenciamentoRiscoDinamico()
        self.market_structure = MarketStructure()
        self.fake_breakout = FakeBreakoutDetector(atr_mult=FORCA_BREAKOUT_ATR_MULT, volume_mult=VOLUME_BREAKOUT_MIN, forca_minima=FORCA_BREAKOUT_MINIMA)
        
        # V18
        self.drawdown_protector = DrawdownProtector(CAPITAL_INICIAL)
        self.open_interest_analyzer = OpenInterestAnalyzer(self)
        
        # V19: Controle de correlação entre ALTs
        self.alt_coins = ['ETHUSDT', 'BNBUSDT', 'SOLUSDT']
        self.trade_lock = Lock()
        
        self.ATIVOS = [
            {'symbol': 'BTCUSDT', 'nome': 'BITCOIN', 'decimais': 0, 'ativo': True, 'tipo': 'btc'},
            {'symbol': 'ETHUSDT', 'nome': 'ETHEREUM', 'decimais': 0, 'ativo': True, 'tipo': 'alt'},
            {'symbol': 'BNBUSDT', 'nome': 'BNB', 'decimais': 1, 'ativo': True, 'tipo': 'alt'},
            {'symbol': 'SOLUSDT', 'nome': 'SOLANA', 'decimais': 2, 'ativo': True, 'tipo': 'alt'},
        ]
        
        self.dados = {}
        for ativo in self.ATIVOS:
            self.dados[ativo['symbol']] = {
                'nome': ativo['nome'],
                'decimais': ativo['decimais'],
                'tipo': ativo['tipo'],
                'velas_15m': deque(maxlen=300),
                'velas_1h': deque(maxlen=200),
                'velas_4h': deque(maxlen=100),
                'preco_atual': 0,
                'conectado': False,
                'estatisticas': {'acertos': 0, 'erros': 0, 'historico_trades': []},
                'ultimo_sinal': 0,
                'ultimo_timestamp_15m': 0,
                'ultimo_timestamp_1h': 0,
                'ultimo_timestamp_4h': 0,
                'regime_detector': MarketRegimeDetector(),
                'cooldown_loss': 0,
                'tendencia_4h': 'LATERAL',
                'liquidez_24h': 0,
            }
        
        self.ultimo_alerta_tempo = {}
        self.ultimo_alerta_tipo = {}
        self.trades_abertos = {}
        
        self.carregar_estatisticas()
        self.carregar_velas_iniciais()
        
        self.backtest_engine = BacktestEngine(self)

    def carregar_estatisticas(self):
        try:
            if os.path.exists("estatisticas_institucional.json"):
                with open("estatisticas_institucional.json", 'r') as f:
                    dados = json.load(f)
                    for symbol in self.dados:
                        if symbol in dados:
                            self.dados[symbol]['estatisticas'] = dados[symbol].get('estatisticas', {'acertos': 0, 'erros': 0})
                            if 'historico_trades' in dados[symbol]:
                                self.dados[symbol]['estatisticas']['historico_trades'] = dados[symbol]['historico_trades']
        except:
            pass

    def salvar_estatisticas(self):
        try:
            dados = {}
            for symbol in self.dados:
                dados[symbol] = {
                    'estatisticas': {
                        'acertos': self.dados[symbol]['estatisticas']['acertos'],
                        'erros': self.dados[symbol]['estatisticas']['erros'],
                        'historico_trades': list(self.dados[symbol]['estatisticas'].get('historico_trades', []))
                    },
                    'nome': self.dados[symbol]['nome']
                }
            with open("estatisticas_institucional.json", 'w') as f:
                json.dump(dados, f, indent=4)
        except:
            pass

    def carregar_velas_iniciais(self):
        print(f"{CIANO}🔄 Carregando velas históricas...{RESET}")
        
        if not self.binance.conectar():
            print(f"{VERMELHO}❌ Não foi possível conectar.{RESET}")
            return
        
        for ativo in self.ATIVOS:
            if not ativo['ativo']:
                continue
            symbol = ativo['symbol']
            
            velas_15m = self.binance.obter_velas(symbol, '15m', 300)
            if velas_15m and len(velas_15m) > 0:
                self.dados[symbol]['velas_15m'] = deque(velas_15m, maxlen=300)
                self.dados[symbol]['conectado'] = True
                self.dados[symbol]['preco_atual'] = velas_15m[-1]['fechamento']
                self.dados[symbol]['ultimo_timestamp_15m'] = velas_15m[-1]['timestamp']
            
            velas_1h = self.binance.obter_velas(symbol, '1h', 200)
            if velas_1h and len(velas_1h) > 0:
                self.dados[symbol]['velas_1h'] = deque(velas_1h, maxlen=200)
                self.dados[symbol]['ultimo_timestamp_1h'] = velas_1h[-1]['timestamp']
            
            velas_4h = self.binance.obter_velas(symbol, '4h', 100)
            if velas_4h and len(velas_4h) > 0:
                self.dados[symbol]['velas_4h'] = deque(velas_4h, maxlen=100)
                self.dados[symbol]['ultimo_timestamp_4h'] = velas_4h[-1]['timestamp']
            
            self.dados[symbol]['liquidez_24h'] = self.binance.obter_liquidez_24h(symbol)
            
            tendencia, _ = analisar_tendencias(list(self.dados[symbol]['velas_4h']))
            self.dados[symbol]['tendencia_4h'] = tendencia
            
            status = f"{VERDE}✓" if self.dados[symbol]['conectado'] else f"{VERMELHO}✗"
            liquidez_str = f"${self.dados[symbol]['liquidez_24h']/1_000_000:.1f}M"
            print(f"   {status} {ativo['nome']}: 15m={len(self.dados[symbol]['velas_15m'])} | 1h={len(self.dados[symbol]['velas_1h'])} | 4h={len(self.dados[symbol]['velas_4h'])} | Liq: {liquidez_str}")
        
        print()

    def executar_backtest_auto(self):
        print(f"\n{CIANO}{'='*80}{RESET}")
        print(f"{CIANO_NEGRITO}📊 EXECUTANDO BACKTEST INICIAL V19{RESET}")
        print(f"{CIANO}{'='*80}{RESET}")
        
        for ativo in self.ATIVOS:
            if not ativo['ativo']:
                continue
            
            symbol = ativo['symbol']
            resultado = self.backtest_engine.executar_backtest(symbol, BACKTEST_DIAS)
            
            if resultado and resultado['trades'] > 10:
                cor = VERDE if resultado['taxa_acerto'] > 55 else AMARELO if resultado['taxa_acerto'] > 45 else VERMELHO
                print(f"   {ativo['nome']}: {resultado['trades']} trades | Acertos: {resultado['acertos']} | Erros: {resultado['erros']} | {cor}Taxa: {resultado['taxa_acerto']:.1f}%{RESET} | Lucro: {resultado['lucro_total']:.1f}%")
                
                if resultado['taxa_acerto'] < 40 and resultado['trades'] > 20:
                    print(f"{AMARELO}⚠️ {ativo['nome']} taxa baixa! Otimizando parâmetros...{RESET}")
                    otimizado = self.backtest_engine.otimizar_parametros(symbol)
                    if otimizado:
                        print(f"{VERDE}   ✓ Otimizado: TP={otimizado['tp']*100:.1f}% SL={otimizado['sl']*100:.1f}%{RESET}")
            else:
                print(f"   {ativo['nome']}: {AMARELO}dados insuficientes para backtest{RESET}")

    def adicionar_vela_websocket(self, symbol, vela, timeframe):
        dados = self.dados.get(symbol)
        if not dados:
            return
        
        if timeframe == '15m' and vela['timestamp'] > dados['ultimo_timestamp_15m']:
            dados['velas_15m'].append(vela)
            dados['ultimo_timestamp_15m'] = vela['timestamp']
        elif timeframe == '1h' and vela['timestamp'] > dados['ultimo_timestamp_1h']:
            dados['velas_1h'].append(vela)
            dados['ultimo_timestamp_1h'] = vela['timestamp']
        elif timeframe == '4h' and vela['timestamp'] > dados['ultimo_timestamp_4h']:
            dados['velas_4h'].append(vela)
            dados['ultimo_timestamp_4h'] = vela['timestamp']
            tendencia, _ = analisar_tendencias(list(dados['velas_4h']))
            dados['tendencia_4h'] = tendencia

    def atualizar_preco_websocket(self, symbol, preco):
        self.dados[symbol]['preco_atual'] = preco

    def pode_gerar_novo_sinal(self, symbol):
        ultimo = self.dados[symbol].get('ultimo_sinal', 0)
        return time.time() - ultimo > COOLDOWN_ENTRE_SINAIS

    def em_cooldown(self, symbol):
        cooldown = self.dados[symbol].get('cooldown_loss', 0)
        if cooldown > 0:
            if time.time() - cooldown < COOLDOWN_APOS_LOSS:
                return True, f"Cooldown de {COOLDOWN_APOS_LOSS//60} minutos após loss"
        return False, ""

    # V19: Controle de correlação entre ALTs
    def verificar_correlacao_alts(self):
        """Verifica quantos trades correlacionados estão abertos"""
        with self.trade_lock:
            alts_abertos = 0
            for trade in self.trades_abertos.values():
                symbol = trade['symbol']
                if symbol in self.alt_coins:
                    alts_abertos += 1
            return alts_abertos

    def pode_abrir_trade(self, sinal, symbol):
        with self.trade_lock:
            if len(self.trades_abertos) >= MAX_TRADES_ABERTOS:
                return False, f"Máximo de {MAX_TRADES_ABERTOS} trades"
            
            mesma_direcao = sum(1 for t in self.trades_abertos.values() if t.get('sinal') == sinal)
            if mesma_direcao >= MAX_TRADES_MESMA_DIRECAO:
                return False, f"Máximo de {MAX_TRADES_MESMA_DIRECAO} trades na direção {sinal}"
            
            # V19: Verificar correlação entre ALTs
            if symbol in self.alt_coins:
                alts_abertos = self.verificar_correlacao_alts()
                if alts_abertos >= MAX_TRADES_CORRELACIONADOS:
                    return False, f"Máximo de {MAX_TRADES_CORRELACIONADOS} trade(s) correlacionado(s) (ETH/BNB/SOL)"
        
        return True, ""

    # V19: Verificar volatilidade explosiva
    def verificar_volatilidade_explosiva(self, velas, symbol):
        if len(velas) < 30:
            return False, ""
        
        atr_atual = calcular_atr_wilder(velas, 14, symbol)
        atr_medio = calcular_atr_medio(velas, 14, symbol)
        
        if atr_atual > atr_medio * ATR_MULT_EXPLOSIVO:
            return True, f"ATR atual {atr_atual:.2f} > {ATR_MULT_EXPLOSIVO}x ATR médio {atr_medio:.2f}"
        
        return False, ""

    # V19: Obter funding rate
    def obter_funding_rate(self, symbol):
        try:
            symbol_futures = symbol.replace('USDT', 'USDT')
            funding = self.binance.client.futures_funding_rate(symbol=symbol_futures, limit=1)
            if funding and len(funding) > 0:
                return float(funding[0]['fundingRate'])
            return 0
        except:
            return 0

    # V19: Filtrar funding rate
    def filtrar_funding_rate(self, symbol, sinal, funding_rate):
        if funding_rate > FUNDING_LIMIAR_ALTO and sinal == "CALL":
            return False, f"Funding alto {funding_rate*100:.3f}% - mercado supercomprado"
        
        if funding_rate < FUNDING_LIMIAR_BAIXO and sinal == "PUT":
            return False, f"Funding baixo {funding_rate*100:.3f}% - mercado supervendido"
        
        if abs(funding_rate) > 0.02:
            return False, f"Funding extremo {funding_rate*100:.3f}% - aguardar normalizar"
        
        return True, ""

    def finalizar_trade(self, trade_id, preco_saida, pnl, motivo):
        with self.trade_lock:
            if trade_id not in self.trades_abertos:
                return
            
            trade = self.trades_abertos[trade_id]
            symbol = trade['symbol']
            sinal = trade['sinal']
            preco_entrada = trade['preco_entrada']
            valor_trade = trade['valor_trade']
            
            acertou = pnl > 0
            
            # V19: Calcular slippage real
            slippage_real = 0
            if 'preco_teorico' in trade:
                slippage_real = abs(preco_saida - trade['preco_teorico']) / trade['preco_teorico']
            
            lucro_perda = valor_trade * (pnl / 100)
            novo_capital = self.position_sizing.capital + lucro_perda
            self.position_sizing.atualizar_capital(novo_capital)
            
            if not acertou:
                self.dados[symbol]['cooldown_loss'] = time.time()
            
            self.gerenciamento_risco.atualizar_risco(pnl, novo_capital)
            
            parado, motivo_parada = self.drawdown_protector.atualizar(pnl, novo_capital)
            if parado:
                print(f"{VERMELHO_NEGRITO}🔴 ROBÔ PARADO: {motivo_parada}{RESET}")
                enviar_telegram(f"🔴 ROBÔ PARADO\n{motivo_parada}\nCapital: ${novo_capital:,.2f}")
            
            trade_record = {
                'timestamp': datetime.now().isoformat(),
                'symbol': symbol,
                'sinal': sinal,
                'preco_entrada': preco_entrada,
                'preco_saida': preco_saida,
                'pnl': pnl,
                'regime': trade.get('regime', 'indefinido'),
                'adx': trade.get('adx', 0),
                'probabilidade': trade.get('prob_call', 50),
                'motivo': motivo,
                'slippage': slippage_real
            }
            self.db.salvar_trade(trade_record)
            
            ml_trade = {
                'regime': trade.get('regime', 'indefinido'),
                'acertou': acertou,
                'pnl': pnl,
                'componentes': trade.get('componentes', [])
            }
            self.auto_ml.adicionar_trade(ml_trade)
            
            # V19: Salvar log com slippage
            salvar_log_trade(symbol, sinal, preco_entrada, preco_saida, pnl, trade.get('regime', 'indefinido'), trade.get('adx', 0), trade.get('prob_call', 50), motivo, slippage_real)
            
            if acertou:
                self.dados[symbol]['estatisticas']['acertos'] += 1
                print(f"\n{VERDE_NEGRITO}{'='*65}{RESET}")
                print(f"{VERDE_NEGRITO}✅ ACERTOU! {self.dados[symbol]['nome']}{RESET}")
                print(f"{VERDE}   Entrada: ${preco_entrada:,.2f} | Saída: ${preco_saida:,.2f}")
                print(f"{VERDE}   P&L: {pnl:+.2f}% | Lucro: ${lucro_perda:+.2f}{RESET}")
                print(f"{VERDE}   Slippage: {slippage_real:.4f}% | Capital: ${self.position_sizing.capital:,.2f}{RESET}")
                enviar_telegram(f"✅ <b>ACERTOU</b> {self.dados[symbol]['nome']}!\n💰 Entrada: ${preco_entrada:,.2f}\n📈 P&L: {pnl:+.2f}%")
            else:
                self.dados[symbol]['estatisticas']['erros'] += 1
                print(f"\n{VERMELHO_NEGRITO}{'='*65}{RESET}")
                print(f"{VERMELHO_NEGRITO}❌ ERROU! {self.dados[symbol]['nome']}{RESET}")
                print(f"{VERMELHO}   Entrada: ${preco_entrada:,.2f} | Saída: ${preco_saida:,.2f}")
                print(f"{VERMELHO}   P&L: {pnl:+.2f}% | Prejuízo: ${lucro_perda:+.2f}{RESET}")
                print(f"{VERMELHO}   Slippage: {slippage_real:.4f}% | Capital: ${self.position_sizing.capital:,.2f}{RESET}")
                enviar_telegram(f"❌ <b>ERROU</b> {self.dados[symbol]['nome']}!\n💰 Entrada: ${preco_entrada:,.2f}\n📉 P&L: {pnl:+.2f}%")
            
            todos_trades = []
            for sym in self.dados:
                todos_trades.extend(self.dados[sym]['estatisticas'].get('historico_trades', []))
            self.performance_monitor.atualizar_metricas(todos_trades)
            
            self.salvar_estatisticas()

    def abrir_trade(self, symbol, sinal, preco, stop_final, tp_final, confianca, prob_call, valor_trade, regime, adx, detalhes, componentes, vwap, rsi):
        with self.trade_lock:
            trade_id = f"{symbol}_{datetime.now().timestamp()}"
            
            if sinal == 'CALL':
                tp_preco = preco * (1 + tp_final)
                stop_atual = preco - (calcular_atr_wilder(list(self.dados[symbol]['velas_15m']), 14, symbol) * 1.5)
            else:
                tp_preco = preco * (1 - tp_final)
                stop_atual = preco + (calcular_atr_wilder(list(self.dados[symbol]['velas_15m']), 14, symbol) * 1.5)
            
            self.trades_abertos[trade_id] = {
                'symbol': symbol,
                'sinal': sinal,
                'preco_entrada': preco,
                'preco_teorico': preco,  # V19: para calcular slippage
                'tp_preco': tp_preco,
                'stop_atual': stop_atual,
                'melhor_preco': preco,
                'valor_trade': valor_trade,
                'timestamp': time.time(),
                'regime': regime,
                'adx': adx,
                'prob_call': prob_call,
                'confianca': confianca,
                'tp': tp_final,
                'sl': stop_final,
                'componentes': componentes
            }
            
            self.dados[symbol]['ultimo_sinal'] = time.time()
            
            sinal_record = {
                'timestamp': datetime.now().isoformat(),
                'symbol': symbol,
                'sinal': sinal,
                'confianca': confianca,
                'preco': preco,
                'regime': regime,
                'adx': adx,
                'vwap': vwap,
                'rsi': rsi,
                'foi_executado': 1
            }
            self.db.salvar_sinal(sinal_record)
            
            print(f"\n{MAGENTA}{'='*110}{RESET}")
            print(f"{MAGENTA_NEGRITO}🏦 SINAL V19 COMPLETO - {self.dados[symbol]['nome']}{RESET}")
            print(f"{VERDE_NEGRITO if sinal == 'CALL' else VERMELHO_NEGRITO}📊 {sinal} (conf: {confianca:.1f}/10){RESET}")
            print(f"{CIANO}💰 Preço: ${preco:,.2f}{RESET}")
            print(f"{CIANO}💰 Valor: ${valor_trade:,.0f} (Risk {RISCO_POR_TRADE*100:.1f}%){RESET}")
            print(f"{CIANO}🎯 TP: {tp_final*100:.1f}% | SL: {stop_final*100:.1f}%{RESET}")
            print(f"{CIANO}📊 VWAP: ${vwap:,.2f} | RSI: {rsi:.0f}{RESET}")
            for ev in detalhes[:5]:
                print(f"   {ev}")
            print(f"{MAGENTA}{'='*110}{RESET}")
            
            if TELEGRAM_TOKEN:
                msg = f"🏦 <b>SINAL V19 - {self.dados[symbol]['nome']}</b>\n📊 {sinal}\n💰 ${preco:,.2f}\n💰 Valor: ${valor_trade:,.0f}\n⭐ Conf: {confianca:.1f}/10\n📊 VWAP: ${vwap:,.0f} | RSI: {rsi:.0f}"
                enviar_telegram(msg)
            
            if TEM_SOM and winsound:
                winsound.Beep(1000, 300)

    def gerar_sinal(self, symbol):
        dados = self.dados[symbol]
        
        if len(dados['velas_15m']) < 50 or len(dados['velas_1h']) < 30:
            return None, 0, [], 0, 0, 0, 0, {'motivo': 'Dados insuficientes'}
        
        if not self.pode_gerar_novo_sinal(symbol):
            return None, 0, [], 0, 0, 0, 0, {'motivo': 'Cooldown entre sinais'}
        
        horario_ok, motivo = horario_permitido()
        if not horario_ok:
            return None, 0, [], 0, 0, 0, 0, {'motivo': motivo}
        
        evento_macro, nome_evento = verificar_evento_macro()
        if evento_macro:
            return None, 0, [], 0, 0, 0, 0, {'motivo': f'Evento macro: {nome_evento}'}
        
        em_cooldown, motivo = self.em_cooldown(symbol)
        if em_cooldown:
            return None, 0, [], 0, 0, 0, 0, {'motivo': motivo}
        
        if self.drawdown_protector.parado:
            return None, 0, [], 0, 0, 0, 0, {'motivo': self.drawdown_protector.motivo_parada}
        
        reduzir, motivo_risco = self.gerenciamento_risco.deve_reduzir_risco()
        if reduzir:
            return None, 0, [], 0, 0, 0, 0, {'motivo': motivo_risco}
        
        liquidity = dados.get('liquidez_24h', 0)
        if liquidity < LIQUIDEZ_MINIMA_USDT:
            return None, 0, [], 0, 0, 0, 0, {'motivo': f'Baixa liquidez: ${liquidity/1_000_000:.1f}M'}
        
        spread = self.binance.obter_spread_real(symbol)
        if spread > SPREAD_MAXIMO:
            return None, 0, [], 0, 0, 0, 0, {'motivo': f'Spread alto: {spread*100:.2f}%'}
        
        velas_15m = list(dados['velas_15m'])
        velas_1h = list(dados['velas_1h'])
        velas_4h = list(dados['velas_4h'])
        
        # V19: Verificar volatilidade explosiva
        vol_explosiva, motivo_vol = self.verificar_volatilidade_explosiva(velas_15m, symbol)
        if vol_explosiva:
            return None, 0, [], 0, 0, 0, 0, {'motivo': motivo_vol}
        
        detector = dados['regime_detector']
        regime, adx, volatilidade = detector.detectar(velas_15m)
        
        if detector.deve_ignorar_trade()[0]:
            return None, 0, [], 0, 0, 0, 0, {'regime': regime}
        
        precos = [v['fechamento'] for v in velas_15m]
        chop = calcular_chop_index(precos, 20)
        if chop > CHOP_LIMIAR:
            return None, 0, [], 0, 0, 0, 0, {'motivo': f'Mercado serrilhado (chop: {chop:.2f})'}
        
        tendencia_15m, _ = analisar_tendencias(velas_15m)
        tendencia_1h, _ = analisar_tendencias(velas_1h)
        tendencia_4h, _ = analisar_tendencias(velas_4h)
        
        estrutura, detalhe_estrutura = self.market_structure.detectar(precos)
        
        volumes = [v['volume'] for v in velas_15m[-20:]]
        volume_medio = np.mean(volumes) if volumes else 1
        volume_relativo = velas_15m[-1]['volume'] / volume_medio if volume_medio > 0 else 1
        
        if volume_relativo < VOLUME_MINIMO:
            return None, 0, [], 0, 0, 0, 0, {'motivo': f'Volume baixo ({volume_relativo:.1f}x)'}
        
        momentum_score = calcular_momentum_numpy(precos)
        
        # V19: RSI para filtrar extremos
        rsi = calcular_rsi(velas_15m, 14, symbol)
        
        # V19: VWAP como filtro obrigatório
        vwap = calcular_vwap_numpy(velas_15m, VWAP_Periodo)
        preco_atual = precos[-1]
        
        vwap_valido = False
        vwap_sinal = None
        
        if VWAP_OBRIGATORIO and vwap > 0:
            if preco_atual > vwap:
                vwap_valido = True
                vwap_sinal = "ACIMA"
            else:
                vwap_valido = True
                vwap_sinal = "ABAIXO"
        
        rsi_values = []
        for i in range(20, 0, -1):
            if len(velas_15m) >= i:
                rsi_values.append(calcular_rsi(velas_15m[-i:], 14))
        
        divergencia = None
        if len(precos) >= 20 and len(rsi_values) >= 20:
            if precos[-1] < precos[-5] and rsi_values[-1] > rsi_values[-5]:
                divergencia = "DIVERGENCIA_ALTA"
            elif precos[-1] > precos[-5] and rsi_values[-1] < rsi_values[-5]:
                divergencia = "DIVERGENCIA_BAIXA"
        
        depth = self.binance.obter_order_book_com_cache(symbol, 100)
        imbalance = calcular_imbalance_order_book(depth) if depth else 0
        
        absorcao = detectar_absorcao_volume(velas_15m, imbalance)
        
        suportes, resistencias = calcular_suporte_resistencia(velas_15m)
        suporte_proximo = min([s for s in suportes if s < precos[-1]], default=None) if suportes else None
        resistencia_proxima = min([r for r in resistencias if r > precos[-1]], default=None) if resistencias else None
        
        atr = calcular_atr_wilder(velas_15m, 14, symbol)
        
        tp_mult, sl_mult = (2.5, 1.5) if volatilidade > 4 else (2.0, 1.2)
        tp_dinamico = min(atr * tp_mult / precos[-1], 0.03)
        sl_dinamico = min(atr * sl_mult / precos[-1], 0.02)
        
        tp_final = max(tp_dinamico, TAKE_PROFIT_BASE.get(symbol, 0.008))
        stop_final = sl_dinamico
        if sl_dinamico < STOP_LOSS_BASE.get(symbol, 0.005):
            stop_final = STOP_LOSS_BASE.get(symbol, 0.005)
        
        ajuste_risco = self.gerenciamento_risco.get_ajuste_tamanho()
        valor_trade = self.position_sizing.get_valor_trade(precos[-1], stop_final, ajuste_risco)
        
        breakout_valido = False
        sinal_breakout = None
        breakout_motivo = ""
        
        if len(velas_15m) >= 2:
            vela_atual = velas_15m[-1]
            vela_anterior = velas_15m[-2]
            
            if vela_atual['fechamento'] > vela_anterior['maxima']:
                valido, motivo = self.fake_breakout.detectar(vela_atual, vela_anterior, atr, volume_relativo, "CALL")
                if valido:
                    breakout_valido = True
                    sinal_breakout = "CALL"
                    breakout_motivo = motivo
            
            elif vela_atual['fechamento'] < vela_anterior['minima']:
                valido, motivo = self.fake_breakout.detectar(vela_atual, vela_anterior, atr, volume_relativo, "PUT")
                if valido:
                    breakout_valido = True
                    sinal_breakout = "PUT"
                    breakout_motivo = motivo
        
        # V18: Open Interest
        sinal_oi, motivo_oi = self.open_interest_analyzer.get_sinal_oi(symbol, tendencia_4h)
        
        # V18: Funding Rate
        funding_rate = self.obter_funding_rate(symbol)
        funding_ok, motivo_funding = self.filtrar_funding_rate(symbol, None, funding_rate)
        
        confluencia = SistemaConfluencia(detector, self.auto_ml)
        dados_confluencia = {
            'tendencia_15m': tendencia_15m,
            'tendencia_1h': tendencia_1h,
            'tendencia_4h': tendencia_4h,
            'volume_relativo': volume_relativo,
            'momentum_score': momentum_score,
            'breakout_valido': breakout_valido,
            'sinal_breakout': sinal_breakout,
            'breakout_motivo': breakout_motivo,
            'imbalance': imbalance,
            'absorcao': absorcao,
            'estrutura_mercado': estrutura,
            'detalhe_estrutura': detalhe_estrutura,
            'divergencia_rsi': divergencia,
            'suporte_proximo': suporte_proximo is not None,
            'resistencia_proxima': resistencia_proxima is not None,
            'vwap_valido': vwap_valido,
            'vwap_sinal': vwap_sinal,
        }
        
        sinal, score, confirmacoes, prob_call = confluencia.calcular_confluencia(dados_confluencia)
        # V19: Confiança mínima mais exigente
        confianca = min(10, score / 10)
        
        # V19: Aplicar todos os filtros
        if sinal:
            # V19: Filtro VWAP
            if VWAP_OBRIGATORIO and vwap > 0:
                if sinal == "CALL" and preco_atual <= vwap:
                    return None, 0, [], 0, 0, 0, 0, {'motivo': f'Preço ${preco_atual:.0f} abaixo do VWAP ${vwap:.0f} para CALL'}
                if sinal == "PUT" and preco_atual >= vwap:
                    return None, 0, [], 0, 0, 0, 0, {'motivo': f'Preço ${preco_atual:.0f} acima do VWAP ${vwap:.0f} para PUT'}
            
            # V19: Filtro RSI extremo
            if sinal == "CALL" and rsi > RSI_LIMIAR_ALTO:
                return None, 0, [], 0, 0, 0, 0, {'motivo': f'RSI muito alto ({rsi:.0f} > {RSI_LIMIAR_ALTO}) - não comprar'}
            if sinal == "PUT" and rsi < RSI_LIMIAR_BAIXO:
                return None, 0, [], 0, 0, 0, 0, {'motivo': f'RSI muito baixo ({rsi:.0f} < {RSI_LIMIAR_BAIXO}) - não vender'}
            
            # V18: Verificar conflito com Open Interest
            if sinal_oi and sinal_oi != sinal:
                return None, 0, [], 0, 0, 0, 0, {'motivo': f'OI conflitante: {motivo_oi}'}
            
            # V18: Verificar Funding Rate
            if not funding_ok:
                return None, 0, [], 0, 0, 0, 0, {'motivo': motivo_funding}
            
            if tendencia_4h == "ALTA" and sinal == "PUT":
                return None, 0, [], 0, 0, 0, 0, {'motivo': 'Contra tendência macro'}
            if tendencia_4h == "BAIXA" and sinal == "CALL":
                return None, 0, [], 0, 0, 0, 0, {'motivo': 'Contra tendência macro'}
        
        if symbol != 'BTCUSDT':
            btc_tendencia = self.dados['BTCUSDT'].get('tendencia_4h', 'LATERAL')
            if sinal == 'CALL' and btc_tendencia != 'ALTA':
                return None, 0, [], 0, 0, 0, 0, {'motivo': 'BTC não em alta'}
            if sinal == 'PUT' and btc_tendencia != 'BAIXA':
                return None, 0, [], 0, 0, 0, 0, {'motivo': 'BTC não em baixa'}
        
        evidencias = [f"🔍 {c['nome']} (peso {c['peso']})" for c in confirmacoes[:4]]
        evidencias.append(f"📊 ADX: {adx:.0f} | Chop: {chop:.2f} | RSI: {rsi:.0f}")
        evidencias.append(f"💰 Posição: ${valor_trade:.0f} | TP: {tp_final*100:.1f}% | SL: {stop_final*100:.1f}%")
        evidencias.append(f"📊 Order Flow: {imbalance:.2f} | Spread: {spread*100:.2f}%")
        evidencias.append(f"📈 VWAP: ${vwap:,.0f} | Preço: ${preco_atual:,.0f}")
        if estrutura:
            evidencias.append(f"📈 Estrutura: {detalhe_estrutura}")
        if divergencia:
            evidencias.append(f"🔄 Divergência: {divergencia}")
        if sinal_oi:
            evidencias.append(f"📊 OI: {motivo_oi}")
        if funding_rate != 0:
            evidencias.append(f"💰 Funding: {funding_rate*100:.3f}%")
        
        # V19: Confiança mínima mais exigente (6 em vez de 5)
        if sinal and confianca >= CONFIANCA_MINIMA:
            componentes = [c['nome'] for c in confirmacoes]
            return sinal, confianca, evidencias, stop_final, tp_final, adx, prob_call, {
                'regime': regime, 
                'valor_trade': valor_trade, 
                'imbalance': imbalance,
                'momentum_score': momentum_score,
                'estrutura': estrutura,
                'detalhe_estrutura': detalhe_estrutura,
                'componentes': componentes,
                'chop': chop,
                'rsi': rsi,
                'vwap': vwap,
                'funding_rate': funding_rate,
                'oi_motivo': motivo_oi if sinal_oi else None
            }
        else:
            return None, 0, [], 0, 0, 0, 0, {'regime': regime}

    def verificar_sinal_apos_vela(self, symbol):
        dados = self.dados[symbol]
        
        resultado = self.gerar_sinal(symbol)
        if resultado[0] is None:
            return
        
        sinal, confianca, evidencias, stop_final, tp_final, adx, prob_call, info = resultado
        
        # V19: Verificar correlação entre ALTs
        pode, motivo = self.pode_abrir_trade(sinal, symbol)
        if not pode:
            return
        
        if sinal and confianca >= CONFIANCA_MINIMA:
            preco = dados['preco_atual']
            
            if not self.pode_enviar_alerta(symbol, sinal):
                return
            
            valor_trade = info.get('valor_trade', 0)
            componentes = info.get('componentes', [])
            vwap = info.get('vwap', 0)
            rsi = info.get('rsi', 50)
            
            self.abrir_trade(symbol, sinal, preco, stop_final, tp_final, confianca, prob_call, valor_trade, info.get('regime', 'indefinido'), adx, evidencias, componentes, vwap, rsi)

    def pode_enviar_alerta(self, symbol, sinal):
        agora = time.time()
        if symbol not in self.ultimo_alerta_tempo:
            self.ultimo_alerta_tempo[symbol] = 0
            self.ultimo_alerta_tipo[symbol] = None
        
        if self.ultimo_alerta_tipo[symbol] != sinal:
            self.ultimo_alerta_tempo[symbol] = agora
            self.ultimo_alerta_tipo[symbol] = sinal
            return True
        
        if agora - self.ultimo_alerta_tempo[symbol] < ALERTA_COOLDOWN:
            return False
        
        self.ultimo_alerta_tempo[symbol] = agora
        return True

    def mostrar_status(self):
        os.system('cls' if os.name == 'nt' else 'clear')
        
        total_acertos = sum(self.dados[s]['estatisticas']['acertos'] for s in self.dados)
        total_erros = sum(self.dados[s]['estatisticas']['erros'] for s in self.dados)
        total = total_acertos + total_erros
        taxa_global = (total_acertos / total * 100) if total > 0 else 0
        
        print(f"{CIANO}{'='*120}{RESET}")
        print(f"{CIANO_NEGRITO}     🏦 ROBÔ INSTITUCIONAL V19 COMPLETO - VWAP + RSI + CORRELAÇÃO{RESET}")
        print(f"{CIANO}{'='*120}{RESET}")
        print(f"{CIANO}📊 Taxa Global: {taxa_global:.1f}% ({total_acertos}/{total})     🏦 Capital: ${self.position_sizing.capital:,.2f}{RESET}")
        print(f"{CIANO}🎲 Fator Risco: {self.gerenciamento_risco.fator_risco:.2f}x     Drawdown Diário: {self.gerenciamento_risco.drawdown_diario:.1f}%{RESET}")
        print(f"{CIANO}📈 Sharpe: {self.performance_monitor.metricas['sharpe_ratio']:.2f} | Profit Factor: {self.performance_monitor.metricas['profit_factor']:.2f}{RESET}")
        
        if self.drawdown_protector.parado:
            print(f"{VERMELHO_NEGRITO}🔴 ROBÔ PARADO: {self.drawdown_protector.motivo_parada}{RESET}")
        else:
            alts_abertos = self.verificar_correlacao_alts()
            print(f"{VERDE}🟢 Drawdown Protector: Ativo | Losses cons: {self.drawdown_protector.losses_consecutivos} | Hoje: {self.drawdown_protector.losses_hoje}{RESET}")
            print(f"{CIANO}🔗 Trades correlacionados (ALT): {alts_abertos}/{MAX_TRADES_CORRELACIONADOS}{RESET}")
        
        with self.trade_lock:
            print(f"{CIANO}📊 Trades abertos: {len(self.trades_abertos)}/{MAX_TRADES_ABERTOS}     Sequência Perdas: {self.gerenciamento_risco.sequencia_perdas}{RESET}")
        
        print(f"{CINZA}{'-'*120}{RESET}")
        
        for ativo in self.ATIVOS:
            if not ativo['ativo']:
                continue
            symbol = ativo['symbol']
            dados = self.dados.get(symbol, {})
            
            if dados.get('conectado'):
                preco = dados['preco_atual']
                decimais = ativo['decimais']
                preco_str = f"${preco:,.2f}" if decimais == 2 else f"${preco:,.0f}"
                
                velas_15m = list(dados.get('velas_15m', []))
                detector = dados.get('regime_detector')
                if detector and len(velas_15m) > 50:
                    regime_local, adx_local, vol_local = detector.detectar(velas_15m)
                else:
                    regime_local, adx_local, vol_local = 'indefinido', 0, 0
                
                precos_atuais = [v['fechamento'] for v in velas_15m[-50:]] if len(velas_15m) >= 50 else []
                if len(precos_atuais) >= 20:
                    estrutura_atual, _ = self.market_structure.detectar(precos_atuais)
                else:
                    estrutura_atual = "N/A"
                
                chop = calcular_chop_index(precos_atuais, 20) if len(precos_atuais) >= 20 else 0
                chop_cor = VERMELHO if chop > CHOP_LIMIAR else VERDE
                
                # V19: Calcular VWAP e RSI
                vwap = calcular_vwap_numpy(velas_15m, VWAP_Periodo) if len(velas_15m) >= VWAP_Periodo else 0
                rsi = calcular_rsi(velas_15m, 14, symbol) if len(velas_15m) >= 14 else 50
                
                stats = dados.get('estatisticas', {'acertos': 0, 'erros': 0})
                taxa = (stats['acertos'] / (stats['acertos'] + stats['erros']) * 100) if (stats['acertos'] + stats['erros']) > 0 else 0
                
                status = f"{VERDE}✓ ATIVO{RESET}" if dados.get('conectado') else f"{VERMELHO}✗ OFFLINE{RESET}"
                regime_cor = VERDE if 'tendencia' in regime_local else AMARELO if 'vol' in regime_local else CINZA
                estrutura_cor = VERDE if estrutura_atual == "ALTA" else VERMELHO if estrutura_atual == "BAIXA" else CINZA
                
                # V19: Funding rate
                funding = self.obter_funding_rate(symbol)
                funding_cor = VERDE if abs(funding) < 0.005 else AMARELO if abs(funding) < 0.01 else VERMELHO
                
                # V19: Posição em relação ao VWAP
                vwap_cor = VERDE if preco > vwap else VERMELHO if preco < vwap else CINZA
                
                print(f"{ativo['nome']:<12} {preco_str:>14} {adx_local:>7.0f} {regime_cor}{regime_local[:20]:>20}{RESET} {estrutura_cor}{estrutura_atual:>10}{RESET} {chop_cor}{chop:>6.2f}{RESET} {vwap_cor}{vwap:>12,.0f}{RESET} {rsi:>6.0f} {funding_cor}{funding*100:>8.3f}%{RESET} {status:>12} {stats['acertos']:>3}/{stats['erros']:<2} ({taxa:.0f}%)")
        
        print(f"{CINZA}{'-'*120}{RESET}")
        print(f"{CIANO}✅ V19: VWAP obrigatório | RSI extremo | Correlação ALTs | Sincronização WebSocket{RESET}")
        print(f"{CIANO}✅ Score mínimo: {LIMIAR_CONFLUENCIA} | Confiança mínima: {CONFIANCA_MINIMA}/10 | Slippage real{RESET}")
        print(f"{CIANO}✅ Open Interest | Funding Rate | Drawdown Protection | Fake Breakout (vol+força){RESET}")
        print(f"{CIANO}{'='*120}{RESET}")

    def executar(self):
        print(f"{MAGENTA}{'='*120}{RESET}")
        print(f"{MAGENTA_NEGRITO}     🏦 ROBÔ INSTITUCIONAL V19 COMPLETO - VWAP + RSI + CORRELAÇÃO{RESET}")
        print(f"{MAGENTA}{'='*120}{RESET}")
        
        self.ws = BinanceWebSocket(self)
        self.ws.iniciar()
        
        self.trade_monitor = TradeMonitor(self)
        self.trade_monitor.iniciar()
        
        self.executar_backtest_auto()
        
        enviar_telegram(f"🏦 ROBÔ V19 COMPLETO INICIADO\n✅ VWAP obrigatório | RSI extremo\n✅ Correlação ALTs | Sincronização WebSocket\n✅ Score mínimo {LIMIAR_CONFLUENCIA} | Confiança {CONFIANCA_MINIMA}/10\n✅ Slippage real | Volatilidade explosiva")
        
        print(f"\n{VERDE_NEGRITO}🚀 Robô V19 Completo operacional!{RESET}")
        print(f"{CIANO}📋 NOVIDADES V19:{RESET}")
        print(f"   ✅ VWAP como filtro OBRIGATÓRIO (CALL: preço > VWAP | PUT: preço < VWAP)")
        print(f"   ✅ RSI extremo (não comprar com RSI > {RSI_LIMIAR_ALTO} / não vender com RSI < {RSI_LIMIAR_BAIXO})")
        print(f"   ✅ Sincronização REST após reconexão WebSocket (sem perda de dados)")
        print(f"   ✅ Controle de correlação entre ALTs (máx {MAX_TRADES_CORRELACIONADOS} trade entre ETH/BNB/SOL)")
        print(f"   ✅ Score mínimo mais exigente: {LIMIAR_CONFLUENCIA} (antes 40)")
        print(f"   ✅ Confiança mínima: {CONFIANCA_MINIMA}/10 (antes 5)")
        print(f"   ✅ Monitoramento de slippage real (registrado no CSV)")
        print(f"   ✅ Filtro de volatilidade explosiva (ATR > {ATR_MULT_EXPLOSIVO}x média)")
        print(f"\n{CIANO}📋 FUNCIONALIDADES MANTIDAS:{RESET}")
        print(f"   ✅ Open Interest | Funding Rate | Drawdown Protection")
        print(f"   ✅ Choppiness Index | Volume Absorption | Auto-ML")
        print(f"   ✅ Performance Monitor | Suporte/Resistência | Divergência RSI")
        print(f"   ✅ Market Structure | Fake Breakout (volume + força do candle)")
        print(f"   ✅ Backtest e Otimização | SQLite Database\n")
        
        try:
            while True:
                self.mostrar_status()
                time.sleep(5)
                
        except KeyboardInterrupt:
            self.salvar_estatisticas()
            
            todos_trades = []
            for sym in self.dados:
                todos_trades.extend(self.dados[sym]['estatisticas'].get('historico_trades', []))
            self.performance_monitor.atualizar_metricas(todos_trades)
            self.performance_monitor.mostrar_relatorio()
            
            metrica_final = {
                'data': datetime.now().isoformat(),
                'capital': self.position_sizing.capital,
                'drawdown': self.gerenciamento_risco.max_drawdown,
                'taxa_acerto': self.performance_monitor.metricas['win_rate'],
                'sharpe': self.performance_monitor.metricas['sharpe_ratio'],
                'profit_factor': self.performance_monitor.metricas['profit_factor']
            }
            self.db.salvar_metrica(metrica_final)
            
            if self.trade_monitor:
                self.trade_monitor.parar()
            if self.ws:
                self.ws.parar()
            
            self.db.fechar()
            
            enviar_telegram(f"🏦 ROBÔ V19 COMPLETO ENCERRADO\n💰 Capital Final: ${self.position_sizing.capital:,.2f}\n📊 Sharpe: {self.performance_monitor.metricas['sharpe_ratio']:.2f}")
        except Exception as e:
            print(f"{VERMELHO}❌ Erro: {e}{RESET}")
            time.sleep(5)

# ============================================
# PONTO DE ENTRADA PRINCIPAL
# ============================================

if __name__ == "__main__":
    try:
        robo = RoboInstitucionalV19Completo()
        robo.executar()
    except ImportError as e:
        print(f"{VERMELHO}❌ Erro de importação: {e}{RESET}")
        print(f"{AMARELO}⚠️ pip install python-binance websocket-client numpy pandas requests{RESET}")
    except Exception as e:
        print(f"{VERMELHO}❌ Erro fatal: {e}{RESET}")
