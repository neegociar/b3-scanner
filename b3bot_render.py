def buscar_acao_completa(ticker, dados_historicos):
    """Busca dados completos da ação"""
    try:
        ticker_yf = f"{ticker}.SA"
        
        if ticker_yf not in dados_historicos:
            return None
        
        df_acao = dados_historicos[ticker_yf]
        tecnicos = calcular_indicadores_tecnicos(df_acao)
        if not tecnicos:
            return None
        
        stock = yf.Ticker(ticker_yf)
        fast_info = stock.fast_info
        
        preco = tecnicos['preco_atual']
        if preco <= 0:
            return None
        
        volume_acoes = fast_info.get('lastVolume', 0)
        volume_financeiro = volume_acoes * preco
        if volume_financeiro < LIQUIDEZ_MINIMA:
            return None
        
        info = stock.info
        
        # ============================================
        # DADOS CONFIÁVEIS
        # ============================================
        pl = info.get('trailingPE', 0)
        pvp = info.get('priceToBook', 0)
        roe = info.get('returnOnEquity', 0) * 100 if info.get('returnOnEquity') else 0
        margem = info.get('profitMargins', 0) * 100 if info.get('profitMargins') else 0
        
        # ============================================
        # DY CORRIGIDO
        # ============================================
        dy_raw = info.get('dividendYield', 0)
        if dy_raw is None or dy_raw == 0:
            dy = 0
        elif dy_raw > 1:
            dy = dy_raw  # Yahoo já retornou em percentual
        elif dy_raw <= 1:
            dy = dy_raw * 100  # Converte decimal para percentual
        else:
            dy = 0
        
        # Validação realista
        if dy > 25 or dy < 0:
            dy = 0
        
        # Outros dados (com validação)
        revenue_growth = info.get('revenueGrowth', 0) * 100 if info.get('revenueGrowth') else 0
        debt_to_equity = info.get('debtToEquity', 0)
        
        # ============================================
        # FILTROS RIGOROSOS
        # ============================================
        if pl < 2 or pl > 15:
            return None
        if pvp < 0.3 or pvp > 2:
            return None
        if dy < 4:  # DY mínimo 4%
            return None
        if roe < 8:  # ROE mínimo 8%
            return None
        if margem < 5:  # Margem mínima 5%
            return None
        if debt_to_equity > 200:  # Dívida controlada
            return None
        
        # ============================================
        # SCORE MELHORADO
        # ============================================
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
        
        # ============================================
        # SUPORTE CORRIGIDO (apenas acima)
        # ============================================
        suporte = tecnicos['suporte']
        preco_atual = tecnicos['preco_atual']
        
        if preco_atual > suporte:
            distancia = ((preco_atual - suporte) / suporte) * 100
            situacao = "acima"
            if distancia <= 5:
                classificacao = "🔴 SUPORTE FORTE - COMPRA IMEDIATA"
            elif distancia <= 10:
                classificacao = "🟡 PRÓXIMO SUPORTE - COMPRA PARCIAL"
            elif distancia <= 15:
                classificacao = "🟢 ACIMA SUPORTE - AGUARDAR"
            else:
                classificacao = "🔵 LONGE DO SUPORTE - MONITORAR"
        else:
            distancia = abs(((suporte - preco_atual) / preco_atual) * 100)
            situacao = "abaixo"
            classificacao = "⚠️ ROMPEU SUPORTE - NÃO COMPRAR"
        
        return {
            'ticker': ticker,
            'preco': preco_atual,
            'suporte': suporte,
            'distancia': round(distancia, 1),
            'situacao': situacao,
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
