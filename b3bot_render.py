import yfinance as yf
import pandas as pd
from datetime import datetime
import time
import threading
import pytz
import requests
import os
import json

# ============================================
# CONFIGURAÇÕES
# ============================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8207229215:AAGNJfXhQm2Xmqzv6XQ8pZ_8Ml-iaZl387Y")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "5869218072")
HORARIO_ENVIO = 10
TOP_OPORTUNIDADES = 10
LIQUIDEZ_MINIMA = 1000000  # R$ 1 milhão

# ============================================
# CACHE LOCAL
# ============================================
CACHE_FILE = "acoes_cache.json"
CACHE_DURATION = 3600  # 1 hora

def carregar_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r') as f:
                cache = json.load(f)
                if time.time() - cache.get('timestamp', 0) < CACHE_DURATION:
                    print("  📦 Cache carregado")
                    return cache.get('dados', {})
        except:
            pass
    return {}

def salvar_cache(dados):
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump({'timestamp': time.time(), 'dados': dados}, f)
        print("  💾 Cache salvo")
    except:
        pass

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

def calcular_proximo_suporte(dados_historicos, preco_atual, suporte_atual):
    try:
        low = dados_historicos['Low']
        close = dados_historicos['Close']
        
        niveis_suporte = []
        for i in range(20, len(low) - 5):
            if low.iloc[i] < low.iloc[i-1] and low.iloc[i] < low.iloc[i+1] and low.iloc[i] < low.iloc[i-2]:
                niveis_suporte.append(low.iloc[i])
        
        mm200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else None
        mm100 = close.rolling(100).mean().iloc[-1] if len(close) >= 100 else None
        
        if mm200:
            niveis_suporte.append(mm200)
        if mm100:
            niveis_suporte.append(mm100)
        
        niveis_validos = []
        for nivel in niveis_suporte:
            if nivel < preco_atual and nivel > 0:
                if not any(abs(nivel - n) < 0.5 for n in niveis_validos):
                    niveis_validos.append(nivel)
        
        if niveis_validos:
            return round(max(niveis_validos), 2)
        return None
    except:
        return None

def buscar_acao_completa(ticker, dados_historicos, cache_dados):
    try:
        ticker_yf = f"{ticker}.SA"
        
        if ticker in cache_dados:
            print(f"  📦 Cache: {ticker}")
            return cache_dados[ticker]
        
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
        
        # ============================================
        # INDICADORES BÁSICOS
        # ============================================
        pl = info.get('trailingPE', 0)
        pvp = info.get('priceToBook', 0)
        roe = info.get('returnOnEquity', 0) * 100 if info.get('returnOnEquity') else 0
        margem = info.get('profitMargins', 0) * 100 if info.get('profitMargins') else 0
        
        # DY
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
        if dy > 15 or dy < 0:
            dy = 0
        
        revenue_growth = info.get('revenueGrowth', 0) * 100 if info.get('revenueGrowth') else 0
        debt_to_equity = info.get('debtToEquity', 0)
        
        # Fluxo de caixa vs lucro
        net_income = info.get('netIncomeToCommon', 0)
        free_cashflow = info.get('freeCashflow', 0)
        fco_vs_lucro = None
        if net_income > 0 and free_cashflow > 0:
            fco_vs_lucro = (free_cashflow / net_income) * 100
        
        # ============================================
        # MELHORIAS
        # ============================================
        earnings_growth = info.get('earningsQuarterlyGrowth', 0) * 100 if info.get('earningsQuarterlyGrowth') else 0
        
        ebit = info.get('ebit', 0)
        interest_expense = info.get('interestExpense', 1)
        cobertura_juros = None
        if interest_expense and interest_expense > 0:
            cobertura_juros = ebit / interest_expense
        
        # ALTMAN Z-SCORE
        ativo_total = info.get('totalAssets', 0)
        passivo_total = info.get('totalLiabilities', 0)
        working_capital = info.get('currentAssets', 0) - info.get('currentLiabilities', 0)
        
        altman_z = None
        if ativo_total > 0:
            A = working_capital / ativo_total if working_capital else 0
            B = info.get('retainedEarnings', 0) / ativo_total if info.get('retainedEarnings') else 0
            C = ebit / ativo_total if ebit else 0
            D = (info.get('marketCap', 0) / passivo_total) if passivo_total > 0 else 0
            E = info.get('totalRevenue', 0) / ativo_total if info.get('totalRevenue') else 0
            altman_z = 1.2*A + 1.4*B + 3.3*C + 0.6*D + 1.0*E
        
        # ============================================
        # PRAZO DE ESTOCAGEM (NOVO)
        # ============================================
        inventory = info.get('inventory', 0)
        cost_of_revenue = info.get('costOfRevenue', 0)
        dias_estoque = None
        if cost_of_revenue > 0 and inventory > 0:
            dias_estoque = (inventory / cost_of_revenue) * 365
        
        # ============================================
        # FILTROS EXISTENTES (mantidos)
        # ============================================
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
        if revenue_growth <= 0:
            return None
        if fco_vs_lucro is not None and fco_vs_lucro < 50:
            return None
        
        # ============================================
        # NOVOS FILTROS (APENAS ADICIONADOS)
        # ============================================
        
        # 1. ALTMAN Z-SCORE como FILTRO (eliminatório)
        if altman_z is not None and altman_z < 1.81:
            return None  # Reprova empresas com risco de falência
        
        # 2. PRAZO DE ESTOCAGEM (elimina estoque parado)
        if dias_estoque is not None and dias_estoque > 180:
            return None  # Mais de 6 meses de estoque parado
        
        # ============================================
        # RANKING PONDERADO (NOVO)
        # ============================================
        
        # Valuation (35%)
        score_valuation = 0
        if pl < 8:
            score_valuation -= 4
        elif pl < 10:
            score_valuation -= 3
        elif pl < 12:
            score_valuation -= 1
        if pvp < 1:
            score_valuation -= 3
        elif pvp < 1.5:
            score_valuation -= 1
        
        # Rentabilidade (25%)
        score_rentabilidade = 0
        if roe > 20:
            score_rentabilidade -= 3
        elif roe > 15:
            score_rentabilidade -= 2
        elif roe > 10:
            score_rentabilidade -= 1
        
        # Crescimento (20%)
        score_crescimento = 0
        if revenue_growth > 10:
            score_crescimento -= 2
        if earnings_growth > 10:
            score_crescimento -= 1
        elif earnings_growth < 0:
            score_crescimento += 1
        
        # Caixa (10%)
        score_caixa = 0
        if fco_vs_lucro is not None:
            if fco_vs_lucro > 80:
                score_caixa -= 2
            elif fco_vs_lucro > 50:
                score_caixa -= 1
        
        # Risco (10%)
        score_risco = 0
        if altman_z is not None:
            if altman_z < 2.99:
                score_risco += 2
        if cobertura_juros is not None and cobertura_juros < 3:
            score_risco += 1
        if dias_estoque is not None and dias_estoque > 120:
            score_risco += 1
        
        # Score total (ponderado)
        score = int((
            score_valuation * 0.35 +
            score_rentabilidade * 0.25 +
            score_crescimento * 0.20 +
            score_caixa * 0.10 +
            score_risco * 0.10
        ) * 10)
        
        # ============================================
        # CLASSIFICAÇÃO
        # ============================================
        suporte = tecnicos['suporte']
        distancia = tecnicos['dist_suporte']
        
        alertas = []
        
        if altman_z is not None:
            if altman_z < 2.99:
                alertas.append(f"🟡 Z-Score: {altman_z:.2f}")
        
        if cobertura_juros is not None and cobertura_juros < 3:
            alertas.append(f"⚠️ Juros: {cobertura_juros:.1f}x")
        
        if dias_estoque is not None:
            if dias_estoque > 120:
                alertas.append(f"⚠️ Estoque: {dias_estoque:.0f}d")
        
        if preco < suporte:
            proximo_suporte = calcular_proximo_suporte(df_acao, preco, suporte)
            if proximo_suporte:
                suporte = proximo_suporte
                distancia = ((suporte - preco) / preco) * 100
                classificacao = f"⚠️ SUPORTE ROMPIDO - PRÓXIMO SUPORTE EM R$ {proximo_suporte:.2f}"
            else:
                classificacao = "🔴 SUPORTE ROMPIDO - TENDÊNCIA DE BAIXA"
        else:
            if distancia <= 3:
                classificacao = "🔴 SUPORTE FORTE - COMPRA IMEDIATA"
            elif distancia <= 6:
                classificacao = "🟡 PRÓXIMO SUPORTE - COMPRA PARCIAL"
            elif distancia <= 10:
                classificacao = "🟢 ACIMA SUPORTE - AGUARDAR"
            else:
                classificacao = "🔵 LONGE DO SUPORTE - MONITORAR"
        
        if alertas:
            classificacao += " | " + " | ".join(alertas)
        
        resultado = {
            'ticker': ticker,
            'preco': preco,
            'suporte': suporte,
            'distancia': round(distancia, 1),
            'classificacao': classificacao,
            'pl': round(pl, 1),
            'pvp': round(pvp, 2),
            'dy': round(dy, 1),
            'roe': round(roe, 1),
            'score': score,
            'volume_mm': round(volume_financeiro / 1000000, 1),
            'altman_z': round(altman_z, 2) if altman_z else None
        }
        
        cache_dados[ticker] = resultado
        return resultado
        
    except Exception as e:
        return None

def buscar_oportunidades():
    print(f"[{datetime.now()}] Buscando tickers...")
    tickers = buscar_todos_tickers_b3()
    if not tickers:
        return []
    
    cache_dados = carregar_cache()
    
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
        
        acao = buscar_acao_completa(ticker, dados_historicos, cache_dados)
        if acao and acao['distancia'] <= 15 and acao['score'] <= -5:
            todas_oportunidades.append(acao)
    
    salvar_cache(cache_dados)
    
    todas_oportunidades.sort(key=lambda x: (x['score'], x['distancia']))
    return todas_oportunidades[:TOP_OPORTUNIDADES]

def enviar_resumo_diario():
    # ============================================
    # AQUECIMENTO: Garante que o servidor está pronto
    # ============================================
    print("🚀 Servidor acordado. Aguardando 10 segundos para estabilizar...")
    time.sleep(10)  # Aguarda o servidor estabilizar completamente
    print("🟢 Continuando com o scan...")
    
    # ============================================
    # SCAN NORMAL (seu código original)
    # ============================================
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
            msg += f"📍 Distância: {opp['distancia']:.1f}% {'acima' if opp['preco'] > opp['suporte'] else 'abaixo'}\n"
            if opp.get('altman_z'):
                msg += f"📊 Altman Z-Score: {opp['altman_z']:.2f}\n"
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
    # Comentado para evitar duplicação com o cron-job.org
    # thread = threading.Thread(target=monitorar_continuo, daemon=True)
    # thread.start()
    
    app.run(host='0.0.0.0', port=8080)
