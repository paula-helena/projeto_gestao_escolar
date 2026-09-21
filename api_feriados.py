import requests

def obter_feriados():
    # URL da BrasilAPI para o ano atual (2026)
    url = "https://brasilapi.com.br/api/feriados/v1/2026"
    
    try:
        resposta = requests.get(url)
        if resposta.status_code == 200:
            feriados_json = resposta.json()
            lista_feriados = []
            
            for item in feriados_json:
                lista_feriados.append({
                    'data': item.get('date'),
                    'nome': item.get('name'),
                    'tipo': 'Feriado Nacional'
                })
            return lista_feriados
    except Exception as e:
        print(f"Erro ao consumir API de feriados: {e}")
    
    return []