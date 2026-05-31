import yfinance as yf
import pandas as pd
from datetime import datetime
import time
import threading
import pytz
import requests
import os

# ============================================
# CONFIGURAÇÕES (VARIÁVEIS DE AMBIENTE)
# ============================================
TELEGRAM_TOKEN = "8207229215:AAGNJfXhQm2Xmqzv6XQ8pZ_8Ml-iaZl387Y"
TELEGRAM_CHAT_ID = "5869218072"
HORARIO_ENVIO = 10
TOP_OPORTUNIDADES = 10
LIQUIDEZ_MINIMA = 1000000  # R$ 1 milhão

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
    """Busca todos os tickers da B3"""
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
    
    # Fallback
    return ["PETR4", "VALE3", "ITUB4", "BBDC4", "ABEV3", "BBAS3", "WEGE3", "ITSA4"]

def calcular_indicadores_tecnicos(dados_historicos):
    """Calcula médias móveis e suportes"""
    if dados_historicos.empty or len(dados_historicos) < 30:
        return None
    
    try:
        close = dados_historicos['Close']
        low = dados_historicos['Low']
        
        preco = close.iloc[-1]
        
        # Médias móveis
        mm50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else preco
        mm100 = close.rolling(100).mean().iloc[-1] if len(close) >= 100 else preco
        mm200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else preco
        
        # Fundo dos últimos 30 dias
        fundo_30d = low.tail(30).min()
        
        # ============================================
        # CORREÇÃO DO SUPORTE (apenas níveis abaixo do preço)
        # ============================================
        niveis = [mm50, mm100, mm200, fundo_30d]
        suportes_validos = [n for n in niveis if n <= preco]
        
        if suportes_validos:
            suporte = max(suportes_validos)  # Maior suporte abaixo do preço
        else:
            suporte = fundo_30d  # Fallback: fundo de 30 dias
        
        resistencia = close.max()
        
        dist_suporte = ((preco - suporte) / suporte) * 100
        
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
    except Exception as e:
        return None

def buscar_acao_completa(ticker, dados_historicos):
    """Busca dados completos da ação"""
    try:
        ticker_yf = f"{ticker}.SA"
        
        # Verificação segura do MultiIndex
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
        
        # ============================================
        # LIQUIDEZ MÉDIA (20 dias)
        # ============================================
        volume_financeiro = (
            df_acao["Close"].tail(20) * df_acao["Volume"].tail(20)
        ).mean()
        
        if volume_financeiro < LIQUIDEZ_MINIMA:
            return None
        
        info = stock.info
        
        # Dados fundamentalistas
        pl = info.get('trailingPE', 0)
        pvp = info.get('priceToBook', 0)
        roe = info.get('returnOnEquity', 0) * 100 if info.get('returnOnEquity') else 0
        margem = info.get('profitMargins', 0) * 100 if info.get('profitMargins') else 0
        
# ============================================
# DY CORRIGIDO (busca trailingAnnualDividendYield)
# ============================================
dy_raw = info.get('trailingAnnualDividendYield', 0)  # Usa trailing (já realizado)

if dy_raw is None or dy_raw == 0:
    # Fallback: tenta dividendYield normal
    dy_raw = info.get('dividendYield', 0)
    if dy_raw is None or dy_raw == 0:
        dy = 0
    elif dy_raw > 1:
        dy = dy_raw
    else:
        dy = dy_raw * 100
else:
    # trailingAnnualDividendYield já vem em percentual (ex: 0.068 = 6.8%)
    dy = dy_raw * 100

# Validação realista (DY máximo histórico da B3 é ~10%)
if dy > 10 or dy < 0:
    dy = 0
        
        revenue_growth = info.get('revenueGrowth', 0) * 100 if info.get('revenueGrowth') else 0
        debt_to_equity = info.get('debtToEquity', 0)
        
        # Filtros rigorosos
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
        
        # Score melhorado
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
        
        # Suporte já está calculado corretamente (abaixo do preço)
        suporte = tecnicos['suporte']
        distancia = tecnicos['dist_suporte']
        
        # Classificação baseada na distância
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
            'volume_mm': round(volume_financeiro / 1000000, 1),
            'mm50': tecnicos['mm50'],
            'mm100': tecnicos['mm100'],
            'mm200': tecnicos['mm200']
        }
    except Exception as e:
        return None

def buscar_oportunidades():
    """Busca oportunidades - analisa TODAS as ações (sem break)"""
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
    
    # Ordena por score (mais negativo primeiro) e depois por distância
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
    app.run(host='0.0.0.0', port=8080)
