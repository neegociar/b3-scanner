import yfinance as yf
import pandas as pd
from datetime import datetime
import time
import threading
import pytz
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============================================
# CONFIGURAÇÕES
# ============================================
TELEGRAM_TOKEN = "8207229215:AAGNJfXhQm2Xmqzv6XQ8pZ_8Ml-iaZl387Y"
TELEGRAM_CHAT_ID = "5869218072"
HORARIO_ENVIO = 10
TOP_OPORTUNIDADES = 10
LIQUIDEZ_MINIMA = 1000000  # R$ 1 milhão

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
            return tickers
    except:
        pass
    
    # Fallback
    return ["PETR4", "VALE3", "ITUB4", "BBDC4", "ABEV3", "BBAS3", "WEGE3", "ITSA4"]

def calcular_indicadores_tecnicos(dados_historicos):
    """Calcula médias móveis e suportes"""
    if dados_historicos.empty:
        return None
    
    try:
        close = dados_historicos['Close']
        low = dados_historicos['Low']
        
        mm50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else close.iloc[-1]
        mm100 = close.rolling(100).mean().iloc[-1] if len(close) >= 100 else close.iloc[-1]
        mm200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else close.iloc[-1]
        
        fundo_30d = low.tail(30).min()
        fundo_52s = low.min()
        
        suporte = max(mm50, mm100, mm200, fundo_30d)
        resistencia = close.max()
        
        dist_suporte = ((close.iloc[-1] - suporte) / suporte) * 100
        dist_resistencia = ((resistencia - close.iloc[-1]) / close.iloc[-1]) * 100
        
        return {
            'preco_atual': round(close.iloc[-1], 2),
            'suporte': round(suporte, 2),
            'resistencia': round(resistencia, 2),
            'dist_suporte': round(dist_suporte, 1),
            'dist_resistencia': round(dist_resistencia, 1),
            'mm50': round(mm50, 2),
            'mm100': round(mm100, 2),
            'mm200': round(mm200, 2),
            'fundo_52s': round(fundo_52s, 2)
        }
    except:
        return None

def buscar_acao_completa(ticker, dados_historicos):
    """Busca dados completos da ação (fundamentos + análise técnica)"""
    try:
        ticker_yf = f"{ticker}.SA"
        stock = yf.Ticker(ticker_yf)
        
        # Dados técnicos
        if ticker_yf in dados_historicos:
            df_acao = dados_historicos[ticker_yf]
            tecnicos = calcular_indicadores_tecnicos(df_acao)
            if not tecnicos:
                return None
        else:
            return None
        
        # Fundamentos usando fast_info (mais confiável)
        fast_info = stock.fast_info
        preco = fast_info.get('lastPrice', 0)
        if preco <= 0:
            return None
        
        volume_diario = fast_info.get('lastVolume', 0) * preco
        if volume_diario < LIQUIDEZ_MINIMA:
            return None
        
        # Dados fundamentalistas
        info = stock.info
        pl = info.get('trailingPE', 0)
        pvp = info.get('priceToBook', 0)
        dy = info.get('dividendYield', 0) * 100 if info.get('dividendYield') else 0
        roe = info.get('returnOnEquity', 0) * 100 if info.get('returnOnEquity') else 0
        margem = info.get('profitMargins', 0) * 100 if info.get('profitMargins') else 0
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
        if debt_to_equity > 200:  # Dívida > 2x patrimônio
            return None
        
        # Score melhorado (40% fundamentos, 30% rentabilidade, 20% dividendos, 10% crescimento)
        score = 0
        
        # Fundamentos (40%)
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
        
        # Rentabilidade (30%)
        if roe > 20:
            score -= 3
        elif roe > 15:
            score -= 2
        elif roe > 10:
            score -= 1
        
        # Dividendos (20%)
        if dy > 8:
            score -= 2
        elif dy > 6:
            score -= 1
        
        # Crescimento (10%)
        if revenue_growth > 10:
            score -= 1
        
        return {
            'ticker': ticker,
            'preco': tecnicos['preco_atual'],
            'suporte': tecnicos['suporte'],
            'distancia': tecnicos['dist_suporte'],
            'pl': pl,
            'pvp': pvp,
            'dy': dy,
            'roe': roe,
            'margem': margem,
            'score': score,
            'volume_mm': round(volume_diario / 1000000, 1),
            'mm50': tecnicos['mm50'],
            'mm100': tecnicos['mm100'],
            'mm200': tecnicos['mm200']
        }
    except Exception as e:
        return None

def buscar_oportunidades():
    """Busca oportunidades usando a versão melhorada"""
    print(f"[{datetime.now()}] Buscando tickers...")
    tickers = buscar_todos_tickers_b3()
    if not tickers:
        return []
    
    print(f"📊 Analisando {len(tickers)} ações...")
    
    # Download único de dados históricos
    tickers_yf = [f"{t}.SA" for t in tickers]
    dados_historicos = yf.download(tickers_yf, period="1y", group_by='ticker', progress=False, timeout=30)
    
    oportunidades = []
    
    for ticker in tickers:
        acao = buscar_acao_completa(ticker, dados_historicos)
        if acao:
            if acao['distancia'] <= 15 and acao['score'] <= -5:
                if acao['distancia'] <= 3:
                    classificacao = "🔴 SUPORTE FORTE - COMPRA IMEDIATA"
                elif acao['distancia'] <= 6:
                    classificacao = "🟡 PRÓXIMO SUPORTE - COMPRA PARCIAL"
                elif acao['distancia'] <= 10:
                    classificacao = "🟢 ACIMA SUPORTE - AGUARDAR"
                else:
                    classificacao = "🔵 LONGE DO SUPORTE - MONITORAR"
                
                oportunidades.append({
                    'ticker': ticker,
                    'preco': acao['preco'],
                    'suporte': acao['suporte'],
                    'distancia': acao['distancia'],
                    'classificacao': classificacao,
                    'pl': acao['pl'],
                    'pvp': acao['pvp'],
                    'dy': acao['dy'],
                    'roe': acao['roe'],
                    'score': acao['score']
                })
        
        if len(oportunidades) >= TOP_OPORTUNIDADES:
            break
    
    return sorted(oportunidades, key=lambda x: x['distancia'])[:TOP_OPORTUNIDADES]

# ... (resto do código: enviar_telegram, enviar_resumo_diario, monitorar_continuo, Flask)
