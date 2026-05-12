import requests
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime
import time
import threading
import pytz

# ============================================
# CONFIGURAÇÕES
# ============================================
TELEGRAM_TOKEN = "8207229215:AAGNJfXhQm2Xmqzv6XQ8pZ_8Ml-iaZl387Y"
TELEGRAM_CHAT_ID = "5869218072"

HORARIO_ENVIO = 10  # 10:00 da manhã (horário de Brasília)
TOP_OPORTUNIDADES = 10

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
            if not texto or texto == '-' or texto == '':
                return 0
            texto = texto.replace('R$', '').replace('.', '').replace(',', '.').strip()
            try:
                return float(texto)
            except:
                return 0

        def converte_percent(texto):
            if not texto or texto == '-' or texto == '':
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
                    
                    if not ticker or len(ticker) < 4:
                        continue
                    if not ticker[0].isalpha():
                        continue
                    if not ticker[-1].isdigit():
                        continue

                    cotacao = converte_valor(colunas[1].text)

                    # Filtro de preço mínimo
                    if cotacao <= 0.50:
                        continue

                    pl = converte_valor(colunas[3].text)
                    pvp = converte_valor(colunas[4].text)
                    dy = converte_percent(colunas[5].text)

                    if pl <= 0 or pvp <= 0:
                        continue

                    # Filtro de liquidez por volume (colunas[6])
                    if len(colunas) > 6:
                        volume_texto = colunas[6].text.strip()
                        if volume_texto and volume_texto != '-':
                            try:
                                volume = converte_valor(volume_texto)
                                if volume < 50000:
                                    continue
                            except:
                                pass

                    # Filtros fundamentalistas
                    if pl < 2 or pl > 30:
                        continue
                    if pvp < 0.3 or pvp > 5:
                        continue
                    if dy > 20:
                        continue

                    # Cálculo do Score
                    score = 0
                    if pl < 10:
                        score -= 5
                    elif pl < 15:
                        score -= 2
                    if pvp < 1.2:
                        score -= 4
                    elif pvp < 1.8:
                        score -= 2
                    if dy > 6:
                        score -= 3
                    elif dy > 4:
                        score -= 1

                    # Setor (colunas[2])
                    setor_texto = colunas[2].text.strip()[:30] if len(colunas) > 2 else "N/A"

                    dados.append({
                        'ticker': ticker,
                        'preco': cotacao,
                        'pl': pl,
                        'pvp': pvp,
                        'dy': dy,
                        'score': score,
                        'setor': setor_texto
                    })
                except Exception:
                    continue

        df = pd.DataFrame(dados)
        if len(df) > 0:
            df = df.sort_values('score', ascending=True)
        return df

    except Exception as e:
        print(f"Erro na busca: {e}")
        return None

def calcular_suporte_dinamico(preco_atual):
    if preco_atual < 10:
        percentual = 0.15
    elif preco_atual < 30:
        percentual = 0.12
    elif preco_atual < 50:
        percentual = 0.11
    elif preco_atual < 100:
        percentual = 0.10
    else:
        percentual = 0.08

    suporte = preco_atual * (1 - percentual)
    return round(suporte, 2), percentual

def buscar_oportunidades():
    oportunidades = []

    print(f"[{datetime.now()}] Buscando ações...")
    df = buscar_acoes_fundamentus()

    if df is None or len(df) == 0:
        return oportunidades

    print(f"✅ Total de ações saudáveis: {len(df)}")

    df_filtrado = df[df['score'] <= -5]
    if len(df_filtrado) == 0:
        return oportunidades

    print(f"📊 Ações baratas (score <= -5): {len(df_filtrado)}")

    top_acoes = df_filtrado.head(50)

    for _, row in top_acoes.iterrows():
        preco = row['preco']
        suporte, percentual = calcular_suporte_dinamico(preco)
        dist_suporte = ((preco - suporte) / preco) * 100

        if dist_suporte <= 15:
            if dist_suporte <= 3:
                classificacao = "🔴 SUPORTE FORTE - COMPRA IMEDIATA"
            elif dist_suporte <= 6:
                classificacao = "🟡 PRÓXIMO SUPORTE - COMPRA PARCIAL"
            elif dist_suporte <= 10:
                classificacao = "🟢 ACIMA SUPORTE - AGUARDAR"
            else:
                classificacao = "🔵 LONGE DO SUPORTE - MONITORAR"

            oportunidades.append({
                'ticker': row['ticker'],
                'preco': preco,
                'suporte': suporte,
                'distancia': round(dist_suporte, 1),
                'classificacao': classificacao,
                'pl': row['pl'],
                'pvp': row['pvp'],
                'dy': row['dy'],
                'score': row['score'],
                'setor': row['setor']
            })

    oportunidades = sorted(oportunidades, key=lambda x: x['distancia'])
    return oportunidades[:TOP_OPORTUNIDADES]

def enviar_resumo_diario():
    fuso_sp = pytz.timezone('America/Sao_Paulo')
    agora_brasil = datetime.now(fuso_sp)
    data_hoje = agora_brasil.strftime('%d/%m/%Y')

    oportunidades = buscar_oportunidades()

    msg = f"📊 <b>RESUMO DIÁRIO - {data_hoje}</b>\n\n"

    if oportunidades:
        msg += f"🐋 <b>OPORTUNIDADES ({len(oportunidades)})</b>\n\n"

        for i, opp in enumerate(oportunidades, 1):
            if opp['score'] <= -15:
                nivel = "🔴🔴🔴 EXTREMAMENTE BARATA"
            elif opp['score'] <= -10:
                nivel = "🔴🔴 MUITO BARATA"
            elif opp['score'] <= -5:
                nivel = "🟡 BARATA"
            else:
                nivel = ""

            if opp['distancia'] <= 3:
                dist_texto = "🔴 NO SUPORTE - COMPRA IMEDIATA"
            elif opp['distancia'] <= 6:
                dist_texto = "🟡 PRÓXIMO SUPORTE - COMPRA PARCIAL"
            elif opp['distancia'] <= 10:
                dist_texto = "🟢 ACIMA SUPORTE - AGUARDAR"
            else:
                dist_texto = "🔵 LONGE DO SUPORTE - MONITORAR"

            msg += f"<b>{i}. {opp['ticker']}</b>\n"
            msg += f"💰 Preço: R$ {opp['preco']:.2f}\n"
            msg += f"📊 Score: {opp['score']:.1f} {nivel}\n"
            msg += f"📊 P/L: {opp['pl']:.1f}x | P/VP: {opp['pvp']:.2f}x | DY: {opp['dy']:.1f}%\n"
            msg += f"🎯 Suporte: R$ {opp['suporte']:.2f}\n"
            msg += f"📍 Distância: {opp['distancia']:.1f}% - {dist_texto}\n"
            if opp['score'] <= -10:
                msg += f"💡 Ação muito barata! Acompanhe de perto.\n"
            msg += "\n"

        msg += f"📌 <i>Top {len(oportunidades)} ações mais baratas</i>"
    else:
        msg += f"✅ Nenhuma oportunidade encontrada hoje."

    if enviar_telegram(msg):
        print(f"✅ Enviado: {len(oportunidades)} oportunidades")
    else:
        print(f"❌ Falha no envio")

    return oportunidades

def monitorar_continuo():
    fuso_sp = pytz.timezone('America/Sao_Paulo')
    print(f"\n🤖 SCANNER B3 INICIADO")
    print(f"⏰ Envio programado para às {HORARIO_ENVIO}:00 (horário de Brasília)\n")

    while True:
        now = datetime.now(fuso_sp)
        if now.hour == HORARIO_ENVIO and now.minute < 5:
            enviar_resumo_diario()
            time.sleep(60)
        time.sleep(30)

# ============================================
# SERVIDOR WEB (FLASK)
# ============================================
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

# ============================================
# EXECUÇÃO PRINCIPAL
# ============================================
if __name__ == "__main__":
    thread = threading.Thread(target=monitorar_continuo, daemon=True)
    thread.start()
    app.run(host='0.0.0.0', port=8080)
