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

def calcular_suporte_real(ticker, preco_atual):
    """Calcula suporte real baseado na mínima de 52 semanas"""
    try:
        dados = yf.download(f"{ticker}.SA", period="1y", progress=False)
        if len(dados) > 0:
            minima_ano = dados["Low"].min()
            maxima_ano = dados["High"].max()
            dist_min = ((preco_atual - minima_ano) / minima_ano) * 100
            dist_max = ((maxima_ano - preco_atual) / maxima_ano) * 100
            return round(minima_ano, 2), round(maxima_ano, 2), round(dist_min, 1), round(dist_max, 1)
    except:
        pass
    return None, None, None, None

def buscar_acao_completa(ticker):
    """Busca dados completos da ação (fundamentos + suporte real)"""
    try:
        ticker_yf = f"{ticker}.SA"
        stock = yf.Ticker(ticker_yf)
        info = stock.info
        
        preco = info.get('regularMarketPrice', 0)
        if preco <= 0:
            return None
        
        # Fundamentos
        pl = info.get('trailingPE', 0)
        pvp = info.get('priceToBook', 0)
        dy = info.get('dividendYield', 0) * 100 if info.get('dividendYield') else 0
        roe = info.get('returnOnEquity', 0) * 100 if info.get('returnOnEquity') else 0
        margem = info.get('profitMargins', 0) * 100 if info.get('profitMargins') else 0
        divida_ebitda = info.get('debtToEquity', 999)
        volume = info.get('averageVolume', 0) * preco  # Volume em R$
        
        # Filtros rigorosos
        if pl < 2 or pl > 30:
            return None
        if pvp < 0.3 or pvp > 5:
            return None
        if dy > 20:
            return None
        if roe < 10:  # ROE mínimo 10%
            return None
        if margem < 0:  # Margem líquida positiva
            return None
        if divida_ebitda > 3:  # Dívida controlada
            return None
        if volume < LIQUIDEZ_MINIMA:  # Liquidez mínima R$1M
            return None
        
        # Score melhorado (prioriza empresas saudáveis)
        score = 0
        if pl < 10:
            score -= 5
        elif pl < 15:
            score -= 2
        if pvp < 1.2:
            score -= 4
        elif pvp < 1.8:
            score -= 2
        if dy > 8:
            score -= 4
        elif dy > 6:
            score -= 3
        elif dy > 4:
            score -= 1
        if roe > 20:  # Bônus para ROE alto
            score -= 2
        if margem > 15:  # Bônus para margem alta
            score -= 1
        
        # Suporte real
        suporte, topo, dist_suporte, dist_topo = calcular_suporte_real(ticker, preco)
        
        return {
            'ticker': ticker,
            'preco': preco,
            'pl': pl,
            'pvp': pvp,
            'dy': dy,
            'roe': roe,
            'margem': margem,
            'score': score,
            'suporte': suporte,
            'topo': topo,
            'dist_suporte': dist_suporte,
            'dist_topo': dist_topo,
            'volume_mm': round(volume / 1000000, 1)
        }
    except Exception as e:
        return None

def buscar_todas_acoes(tickers):
    """Busca dados de todas as ações em paralelo"""
    dados = []
    print(f"📊 Buscando {len(tickers)} ações em paralelo...")
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(buscar_acao_completa, t): t for t in tickers}
        
        for i, future in enumerate(as_completed(futures)):
            if (i+1) % 50 == 0:
                print(f"  Progresso: {i+1}/{len(tickers)}")
            
            resultado = future.result()
            if resultado:
                dados.append(resultado)
    
    df = pd.DataFrame(dados)
    if not df.empty:
        df = df.sort_values('score', ascending=True)
    
    print(f"✅ {len(df)} ações aprovadas")
    return df

def buscar_oportunidades():
    """Busca oportunidades usando a versão melhorada"""
    print(f"[{datetime.now()}] Buscando ações...")
    
    # Busca tickers da B3
    tickers = buscar_todos_tickers_b3()
    if not tickers:
        return []
    
    df = buscar_todas_acoes(tickers)
    if df is None or len(df) == 0:
        return []
    
    # Filtra por score e distância do suporte real
    df_filtrado = df[(df['score'] <= -5) & (df['dist_suporte'] <= 15)]
    
    if df_filtrado.empty:
        return []
    
    top_acoes = df_filtrado.head(TOP_OPORTUNIDADES)
    oportunidades = []
    
    for _, row in top_acoes.iterrows():
        if row['dist_suporte'] <= 3:
            classificacao = "🔴 SUPORTE FORTE - COMPRA IMEDIATA"
        elif row['dist_suporte'] <= 6:
            classificacao = "🟡 PRÓXIMO SUPORTE - COMPRA PARCIAL"
        elif row['dist_suporte'] <= 10:
            classificacao = "🟢 ACIMA SUPORTE - AGUARDAR"
        else:
            classificacao = "🔵 LONGE DO SUPORTE - MONITORAR"
        
        oportunidades.append({
            'ticker': row['ticker'],
            'preco': row['preco'],
            'suporte': row['suporte'],
            'distancia': row['dist_suporte'],
            'classificacao': classificacao,
            'pl': row['pl'],
            'pvp': row['pvp'],
            'dy': row['dy'],
            'roe': row['roe'],
            'score': row['score'],
            'volume_mm': row['volume_mm']
        })
    
    return oportunidades
