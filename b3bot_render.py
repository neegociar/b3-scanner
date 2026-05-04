import requests
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime
import time
import os
import threading

TELEGRAM_TOKEN = "8207229215:AAGNJfXhQm2Xmqzv6XQ8pZ_8Ml-iaZl387Y"
TELEGRAM_CHAT_ID = "5869218072"

DADOS_GRAFICOS_REAIS = {
    "TGMA3": {"suporte": 31.50, "topo": 40.00, "nome": "Tegma"},
    "ENMT4": {"suporte": 48.00, "topo": 60.00, "nome": "Energisa MT"},
    "LEVE3": {"suporte": 28.00, "topo": 36.00, "nome": "Metal Leve"},
    "BMOB3": {"suporte": 22.00, "topo": 27.00, "nome": "Bemobi"},
    "KLBN4": {"suporte": 3.50, "topo": 4.50, "nome": "Klabin"},
    "CPLE3": {"suporte": 10.00, "topo": 18.00, "nome": "Copel"},
    "PETR4": {"suporte": 35.00, "topo": 55.00, "nome": "Petrobras"},
    "VALE3": {"suporte": 60.00, "topo": 120.00, "nome": "Vale"},
    "ODPV3": {"suporte": 11.00, "topo": 15.50, "nome": "Odontoprev"},
    "AGRO3": {"suporte": 15.00, "topo": 22.00, "nome": "BrasilAgro"},
}

INTERVALO_VERIFICACAO = 3600

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
                    
                    if pl < 2 or pl > 30:
                        continue
                    if pvp < 0.3 or pvp > 4:
                        continue
                    if dy > 20:
                        continue
                    
                    score = 0
                    if pl < 12: score -= 3
                    if pvp < 1.5: score -= 3
                    if dy > 5: score -= 2
                    
                    dados.append({
                        'ticker': ticker,
                        'preco': cotacao,
                        'pl': pl,
                        'pvp': pvp,
                        'dy': dy,
                        'score': score
                    })
                except:
                    continue
        
        df = pd.DataFrame(dados)
        return df.sort_values('score', ascending=True)
        
    except Exception as e:
        print(f"Erro na busca: {e}")
        return None

def verificar_posicao(ticker, preco):
    if ticker in DADOS_GRAFICOS_REAIS:
        dados = DADOS_GRAFICOS_REAIS[ticker]
        suporte = dados["suporte"]
        
        dist_suporte = ((preco - suporte) / preco) * 100
        
        if dist_suporte <= 3:
            return "SUPORTE", dist_suporte, "COMPRAR AGORA"
        elif dist_suporte <= 8:
            return "PROXIMO SUPORTE", dist_suporte, "COMPRAR PARCIAL"
        else:
            return "MEIO", dist_suporte, "ANALISAR"
    else:
        return "N/A", 999, "DADOS INDISPONIVEIS"

def monitorar_imediato():
    print(f"[{datetime.now()}] Executando scan...")
    
    df = buscar_acoes_fundamentus()
    oportunidades = 0
    
    if df is not None and len(df) > 0:
        top_baratas = df.head(30)
        
        for _, row in top_baratas.iterrows():
            ticker = row['ticker']
            preco = row['preco']
            posicao, distancia, recomendacao = verificar_posicao(ticker, preco)
            
            if posicao == "SUPORTE":
                oportunidades += 1
                msg = f"""🐋 OPORTUNIDADE B3 - {ticker}

💰 Preco: R$ {preco:.2f}
📊 P/L: {row['pl']:.1f}x
📊 P/VP: {row['pvp']:.2f}x
📊 DY: {row['dy']:.1f}%
📍 Distancia do Suporte: {distancia:.1f}%
🎯 Recomendacao: {recomendacao}"""
                
                enviar_telegram(msg)
                print(f"Alerta enviado: {ticker}")
    
    return oportunidades

def monitorar_continuo():
    print(f"B3 Scanner Iniciado! Verificando a cada {INTERVALO_VERIFICACAO//60} minutos")
    
    while True:
        try:
            oportunidades = monitorar_imediato()
            print(f"Scan concluido. {oportunidades} oportunidades encontradas.")
            time.sleep(INTERVALO_VERIFICACAO)
        except Exception as e:
            print(f"Erro: {e}")
            time.sleep(60)

from flask import Flask
app = Flask(__name__)

@app.route('/')
def health():
    return "B3 Scanner Running!", 200

@app.route('/scan')
def scan_manual():
    oportunidades = monitorar_imediato()
    return f"Scan concluido. {oportunidades} oportunidades encontradas.", 200

# Inicia o monitoramento automaticamente
threading.Thread(target=monitorar_continuo, daemon=True).start()

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)
