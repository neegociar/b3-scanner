import requests
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime
import time
import threading

# ============================================
# CONFIGURAÇÕES
# ============================================
TELEGRAM_TOKEN = "8207229215:AAGNJfXhQm2Xmqzv6XQ8pZ_8Ml-iaZl387Y"
TELEGRAM_CHAT_ID = "5869218072"

HORARIO_ENVIO = 9  # 9:00 da manhã
TOP_OPORTUNIDADES = 10  # Máximo de oportunidades no resumo
DIAS_PARA_SUPORTE = 90  # Dias para calcular suporte (via dados históricos)

# ============================================
# FUNÇÕES
# ============================================
def enviar_telegram(mensagem):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": mensagem, "parse_mode": "HTML"}
        r = requests.post(url, json=payload, timeout=5)
        return r.status_code == 200
    except:
        return False

def buscar_acoes_fundamentus():
    """Busca TODAS as ações da B3 no Fundamentus (600+)"""
    try:
        url = "https://fundamentus.com.br/resultado.php"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        
        response = requests.get(url, headers=headers, timeout=30)
        response.encoding = 'utf-8'
        
        soup = BeautifulSoup(response.text, 'html.parser')
        tabela = soup.find('table', {'id': 'tabelaResultado'})
        if not tabela:
            tabela = soup.find('table', {'class': 'resultado'})
        
        dados = []
        linhas = tabela.find_all('tr')[1:]
        
        def converte_valor(texto):
            if not texto or texto == '-':
                return 0
            texto = texto.replace('R$', '').replace('.', '').replace(',', '.').strip()
            try:
                return float(texto)
            except:
                return 0
        
        def converte_percent(texto):
            if not texto or texto == '-':
                return 0
            texto = texto.replace('%', '').replace('.', '').replace(',', '.').strip()
            try:
                return float(texto)
            except:
                return 0
        
        for linha in linhas:
            colunas = linha.find_all('td')
            if len(colunas) >= 10:
                try:
                    ticker = colunas[0].text.strip()
                    
                    if not ticker[0].isalpha():
                        continue
                    if len(ticker) < 4 or len(ticker) > 6:
                        continue
                    if not ticker[-1].isdigit():
                        continue
                    
                    cotacao = converte_valor(colunas[1].text)
                    pl = converte_valor(colunas[3].text)
                    pvp = converte_valor(colunas[4].text)
                    dy = converte_percent(colunas[5].text)
                    
                    if cotacao <= 0 or pl <= 0 or pvp <= 0:
                        continue
                    
                    # Filtros de ação saudável
                    if pl < 2 or pl > 30:
                        continue
                    if pvp < 0.3 or pvp > 5:
                        continue
                    if dy > 20:
                        continue
                    
                    # Score de valor (quanto menor, mais barata)
                    score = 0
                    if pl < 10: score -= 5
                    elif pl < 15: score -= 2
                    if pvp < 1.2: score -= 4
                    elif pvp < 1.8: score -= 2
                    if dy > 6: score -= 3
                    elif dy > 4: score -= 1
                    
                    dados.append({
                        'ticker': ticker,
                        'preco': cotacao,
                        'pl': pl,
                        'pvp': pvp,
                        'dy': dy,
                        'score': score,
                        'setor': colunas[2].text[:30] if len(colunas) > 2 else "N/A"
                    })
                except:
                    continue
        
        df = pd.DataFrame(dados)
        if len(df) > 0:
            df = df.sort_values('score', ascending=True)
        
        return df
        
    except Exception as e:
        print(f"Erro na busca: {e}")
        return None

def calcular_suporte_dinamico(preco_atual):
    """Calcula suporte com percentual variável baseado no preço"""
    if preco_atual < 10:
        percentual = 0.15  # 15% abaixo (ações muito baratas)
    elif preco_atual < 30:
        percentual = 0.12  # 12% abaixo (ações baratas)
    elif preco_atual < 70:
        percentual = 0.10  # 10% abaixo (ações médias)
    else:
        percentual = 0.08  # 8% abaixo (ações caras)
    
    suporte = preco_atual * (1 - percentual)
    return round(suporte, 2)

def buscar_oportunidades():
    """Busca oportunidades em TODAS as ações (>600), sem prefixação"""
    oportunidades = []
    
    print(f"[{datetime.now()}] Buscando TODAS as ações do Fundamentus...")
    df = buscar_acoes_fundamentus()
    
    if df is None or len(df) == 0:
        print("Nenhuma ação encontrada")
        return oportunidades
    
    print(f"✅ Total de ações saudáveis: {len(df)}")
    
    # Filtra as ações mais baratas (score mais baixo)
    # Quanto menor o score, mais barata a ação
    df_filtrado = df[df['score'] <= -5]  # Ações realmente baratas
    
    if len(df_filtrado) == 0:
        print("Nenhuma ação com score baixo encontrado")
        return oportunidades
    
    print(f"📊 Ações baratas (score <= -5): {len(df_filtrado)}")
    
    # Pega as top 50 ações mais baratas
    top_acoes = df_filtrado.head(50)
    
    print(f"🔍 Analisando suporte das top {len(top_acoes)} ações...\n")
    
    for _, row in top_acoes.iterrows():
        ticker = row['ticker']
        preco = row['preco']
        
        # Calcula suporte dinâmico baseado no preço
        suporte, topo = calcular_suporte_dinamico(ticker, preco)
        dist_suporte = ((preco - suporte) / preco) * 100
        
        # Só considera se estiver próximo do suporte (distância <= 8%)
        if dist_suporte <= 8:
            if dist_suporte <= 3:
                classificacao = "🔴 SUPORTE FORTE - COMPRA IMEDIATA"
            elif dist_suporte <= 5:
                classificacao = "🟡 PRÓXIMO SUPORTE - COMPRA PARCIAL"
            else:
                classificacao = "🟢 ACIMA SUPORTE - AGUARDAR"
            
            oportunidades.append({
                'ticker': ticker,
                'preco': preco,
                'suporte': suporte,
                'topo': topo,
                'distancia': round(dist_suporte, 1),
                'classificacao': classificacao,
                'pl': row['pl'],
                'pvp': row['pvp'],
                'dy': row['dy'],
                'score': row['score'],
                'setor': row['setor']
            })
            
            print(f"   📍 {ticker}: R$ {preco:.2f} | Suporte: R$ {suporte:.2f} | Dist: {dist_suporte:.1f}% | {classificacao.split('-')[0]}")
    
    # Ordena por distância do suporte (mais próximos primeiro)
    oportunidades = sorted(oportunidades, key=lambda x: x['distancia'])
    
    return oportunidades[:TOP_OPORTUNIDADES]

def enviar_resumo_diario():
    """Envia resumo com formatação OTIMIZADA para Telegram"""
    
    hoje = datetime.now().strftime('%Y-%m-%d')
    
    print(f"\n{'='*60}")
    print(f"[{datetime.now()}] GERANDO RESUMO DIÁRIO")
    print(f"{'='*60}")
    
    oportunidades = buscar_oportunidades()
    
    # Título
    msg = f"📊 <b>RESUMO DIÁRIO - {datetime.now().strftime('%d/%m/%Y')}</b>\n\n"
    
    if oportunidades:
        msg += f"🐋 <b>OPORTUNIDADES ENCONTRADAS ({len(oportunidades)})</b>\n\n"
        
        for i, opp in enumerate(oportunidades, 1):
            # Define o nível de barateza baseado no score
            if opp['score'] <= -15:
                nivel_barateza = "🔴🔴🔴 EXTREMAMENTE BARATA"
            elif opp['score'] <= -10:
                nivel_barateza = "🔴🔴 MUITO BARATA"
            elif opp['score'] <= -5:
                nivel_barateza = "🟡 BARATA"
            else:
                nivel_barateza = ""
            
            # Define o texto da distância
            if opp['distancia'] <= 3:
                distancia_texto = "🔴 NO SUPORTE - COMPRA IMEDIATA"
            elif opp['distancia'] <= 6:
                distancia_texto = "🟡 PRÓXIMO SUPORTE - COMPRA PARCIAL"
            else:
                distancia_texto = "🟢 ACIMA SUPORTE - AGUARDAR"
            
            # Monta a mensagem com formatação limpa
            msg += f"<b>{i}. {opp['ticker']}</b>\n"
            msg += f"💰 Preço: R$ {opp['preco']:.2f}\n"
            msg += f"📊 Score: {opp['score']:.1f} {nivel_barateza}\n"
            msg += f"📊 P/L: {opp['pl']:.1f}x | P/VP: {opp['pvp']:.2f}x | DY: {opp['dy']:.1f}%\n"
            msg += f"🎯 Suporte: R$ {opp['suporte']:.2f}\n"
            msg += f"📍 Distância: {opp['distancia']:.1f}% - {distancia_texto}\n"
            
            # Dica para ações muito baratas
            if opp['score'] <= -10:
                msg += f"💡 Ação muito barata! Acompanhe de perto.\n"
            
            msg += f"⚡ Setor: {opp['setor']}\n\n"
        
        msg += f"📌 <i>Top {len(oportunidades)} ações mais baratas</i>"
    else:
        msg += f"✅ Nenhuma oportunidade encontrada hoje.\n\n"
        msg += f"📌 <i>Continue monitorando diariamente!</i>"
    
    if enviar_telegram(msg):
        print(f"✅ Resumo enviado! {len(oportunidades)} oportunidades.")
    else:
        print(f"❌ Falha ao enviar resumo.")
    
    return oportunidades

def monitorar_continuo():
    """Loop que envia resumo apenas às 09:00"""
    print(f"\n🤖 Scanner B3 DINÂMICO INICIADO!")
    print(f"📊 Analisando TODAS as ações da B3 (>600)")
    print(f"🎯 Score mínimo: {SCORE_MINIMO}")
    print(f"📈 Top {TOP_OPORTUNIDADES} oportunidades")
    print(f"⏰ Envio programado para às {HORARIO_ENVIO}:00 da manhã\n")
    
    while True:
        now = datetime.now()
        
        # Verifica se é 09:00 (entre 09:00 e 09:05)
        if now.hour == HORARIO_ENVIO and now.minute < 5:
            enviar_resumo_diario()
            time.sleep(60)  # Espera 1 min para não repetir
        
        time.sleep(30)

# ============================================
# SERVIDOR WEB (Flask)
# ============================================
from flask import Flask, jsonify
app = Flask(__name__)

@app.route('/')
def health():
    return "B3 Scanner DINÂMICO - Analisando TODAS as ações", 200

@app.route('/scan')
def scan_manual():
    """Força um scan manual imediato"""
    oportunidades = enviar_resumo_diario()
    return f"Scan concluído. {len(oportunidades)} oportunidades encontradas.", 200

@app.route('/oportunidades')
def ver_oportunidades():
    """Retorna as oportunidades em JSON"""
    oportunidades = buscar_oportunidades()
    return jsonify({"total": len(oportunidades), "oportunidades": oportunidades})

# ============================================
# INICIAR
# ============================================
if __name__ == "__main__":
    thread = threading.Thread(target=monitorar_continuo, daemon=True)
    thread.start()
    app.run(host='0.0.0.0', port=8080)
