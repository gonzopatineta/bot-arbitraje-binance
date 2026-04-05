import requests
import hmac
import hashlib
import time
import gspread
from google.oauth2.service_account import Credentials
from config import API_KEY_DEMO, API_SECRET_DEMO, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

def telegram(mensaje):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": mensaje}, timeout=10)
    except Exception as e:
        print(f"Error Telegram: {e}")

BASE_URL = "https://demo-fapi.binance.com"
headers = {"X-MBX-APIKEY": API_KEY_DEMO}

UMBRAL_ANUAL = 50
CAPITAL_USDT = 100
STOP_LOSS_PCT = 5
VOLUMEN_MINIMO = 1000000
MAX_VOLATILIDAD = 10

EXCLUIR = ['SLERFUSDT', 'JELLYJELLY', 'NEIROCTOUSUSDT']

SCOPES = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_file('bot-arbitraje-492116-69f7c9ad5a27.json', scopes=SCOPES)
gc = gspread.authorize(creds)
sheet = gc.open("bot_registro").sheet1

def registrar(fecha, simbolo, funding, accion, ganancia, error=""):
    try:
        sheet.append_row([fecha, simbolo, funding, accion, ganancia, error])
    except Exception as e:
        print(f"Error al registrar en Sheets: {e}")

def firmar(params):
    timestamp = int(time.time() * 1000)
    query = params + f"&timestamp={timestamp}"
    signature = hmac.new(
        API_SECRET_DEMO.encode(),
        query.encode(),
        hashlib.sha256
    ).hexdigest()
    return query + f"&signature={signature}"

def get_balance():
    try:
        url = f"{BASE_URL}/fapi/v2/balance"
        response = requests.get(url, params=firmar(""), headers=headers, timeout=10)
        data = response.json()
        if isinstance(data, list):
            for item in data:
                if item['asset'] == 'USDT':
                    return float(item['availableBalance'])
        return 0
    except Exception as e:
        print(f"Error al obtener balance: {e}")
        fecha = time.strftime('%Y-%m-%d %H:%M:%S')
        registrar(fecha, "-", "-", "ERROR", "-", str(e))
        return 0

def get_stats_simbolo(simbolo):
    try:
        url = f"{BASE_URL}/fapi/v1/ticker/24hr?symbol={simbolo}"
        response = requests.get(url, timeout=10)
        data = response.json()
        volumen = float(data.get('quoteVolume', 0))
        precio_alto = float(data.get('highPrice', 0))
        precio_bajo = float(data.get('lowPrice', 1))
        volatilidad = ((precio_alto - precio_bajo) / precio_bajo) * 100
        return volumen, volatilidad
    except Exception as e:
        print(f"Error al obtener stats de {simbolo}: {e}")
        return 0, 100

def get_mejor_oportunidad():
    try:
        url = f"{BASE_URL}/fapi/v1/premiumIndex"
        response = requests.get(url, timeout=10)
        data = response.json()
        oportunidades = []
        for item in data:
            simbolo = item['symbol']
            if any(ex in simbolo for ex in EXCLUIR):
                continue
            if not simbolo.endswith('USDT'):
                continue
            rate = float(item['lastFundingRate'])
            anual = rate * 3 * 365 * 100
            if anual < UMBRAL_ANUAL:
                continue
            volumen, volatilidad = get_stats_simbolo(simbolo)
            if volumen < VOLUMEN_MINIMO:
                continue
            if volatilidad > MAX_VOLATILIDAD:
                continue
            oportunidades.append((simbolo, rate, anual, volumen, volatilidad))
        oportunidades.sort(key=lambda x: x[2], reverse=True)
        return oportunidades
    except Exception as e:
        print(f"Error al obtener funding rates: {e}")
        fecha = time.strftime('%Y-%m-%d %H:%M:%S')
        registrar(fecha, "-", "-", "ERROR FUNDING", "-", str(e))
        return []

def abrir_short(simbolo, cantidad):
    try:
        url = f"{BASE_URL}/fapi/v1/order"
        params = f"symbol={simbolo}&side=SELL&type=MARKET&quantity={cantidad}"
        response = requests.post(url, params=firmar(params), headers=headers, timeout=10)
        return response.json()
    except Exception as e:
        print(f"Error al abrir short: {e}")
        fecha = time.strftime('%Y-%m-%d %H:%M:%S')
        registrar(fecha, simbolo, "-", "ERROR ABRIR", "-", str(e))
        return {}

def cerrar_short(simbolo, cantidad):
    try:
        url = f"{BASE_URL}/fapi/v1/order"
        params = f"symbol={simbolo}&side=BUY&type=MARKET&quantity={cantidad}&reduceOnly=true"
        response = requests.post(url, params=firmar(params), headers=headers, timeout=10)
        return response.json()
    except Exception as e:
        print(f"Error al cerrar short: {e}")
        fecha = time.strftime('%Y-%m-%d %H:%M:%S')
        registrar(fecha, simbolo, "-", "ERROR CERRAR", "-", str(e))
        return {}

print("=== BOT ARBITRAJE FUNDING RATE - DEMO ===")
print(f"Stop loss: {STOP_LOSS_PCT}% | Volatilidad max: {MAX_VOLATILIDAD}% | Volumen min: {VOLUMEN_MINIMO} USDT\n")
registrar("INICIO", "-", "-", "Bot iniciado con manejo de errores", "-")
telegram("Bot Arbitraje iniciado correctamente")

posicion_abierta = None
balance_inicial = get_balance()
errores_consecutivos = 0

while True:
    try:
        print(f"--- {time.strftime('%H:%M:%S')} ---")
        balance = get_balance()
        ganancia_total = round(balance - balance_inicial, 4)
        print(f"Balance: {balance} USDT | Ganancia total: {ganancia_total} USDT")

        if balance == 0:
            errores_consecutivos += 1
            print(f"Error de conexion #{errores_consecutivos}. Reintentando en 60 segundos...")
            if errores_consecutivos >= 5:
                fecha = time.strftime('%Y-%m-%d %H:%M:%S')
                registrar(fecha, "-", "-", "ALERTA CRITICA", "-", "5 errores consecutivos de conexion")
                errores_consecutivos = 0
            time.sleep(60)
            continue

        errores_consecutivos = 0

        if posicion_abierta is None:
            oportunidades = get_mejor_oportunidad()
            if oportunidades:
                simbolo, rate, anual, volumen, volatilidad = oportunidades[0]
                print(f"\n[MEJOR OPORTUNIDAD] {simbolo}")
                print(f"  Funding: {anual:.1f}% anual")
                print(f"  Volumen 24hs: {volumen:,.0f} USDT")
                print(f"  Volatilidad 24hs: {volatilidad:.1f}%")
                print(f"Abriendo SHORT con {CAPITAL_USDT} USDT...")
                precio_url = f"{BASE_URL}/fapi/v1/ticker/price?symbol={simbolo}"
                precio = float(requests.get(precio_url, timeout=10).json()['price'])
                cantidad = int(CAPITAL_USDT / precio)
                if cantidad == 0:
                    cantidad = 1
                resultado = abrir_short(simbolo, cantidad)
                if 'orderId' in resultado:
                    posicion_abierta = (simbolo, cantidad, rate, balance, precio)
                    fecha = time.strftime('%Y-%m-%d %H:%M:%S')
                    registrar(fecha, simbolo, f"{anual:.1f}%", "ABRIR SHORT", "-")
                    print(f"Posicion abierta!")
                    telegram(f"[OK] Posicion abierta en {simbolo}\nFunding: {anual:.1f}% anual\nCapital: {CAPITAL_USDT} USDT")
                else:
                    print(f"Error: {resultado}")
                    if resultado.get('code') == -4411:
                        EXCLUIR.append(simbolo)
                        print(f"{simbolo} excluido automaticamente.")
            else:
                print("Sin oportunidades. Esperando...")
        else:
            simbolo, cantidad, rate_original, balance_entrada, precio_entrada = posicion_abierta
            precio_actual_url = f"{BASE_URL}/fapi/v1/ticker/price?symbol={simbolo}"
            precio_actual = float(requests.get(precio_actual_url, timeout=10).json()['price'])
            perdida_pct = ((precio_actual - precio_entrada) / precio_entrada) * 100

            oportunidades = get_mejor_oportunidad()
            rate_actual = next((r for s, r, a, v, vol in oportunidades if s == simbolo), 0)
            anual_actual = rate_actual * 3 * 365 * 100

            print(f"\nPosicion: {simbolo} | Funding: {anual_actual:.1f}% | P&L precio: {-perdida_pct:.2f}%")

            if perdida_pct > STOP_LOSS_PCT:
                print(f"STOP LOSS activado! Perdida: {perdida_pct:.2f}%")
                cerrar_short(simbolo, cantidad)
                balance_cierre = get_balance()
                ganancia = round(balance_cierre - balance_entrada, 4)
                fecha = time.strftime('%Y-%m-%d %H:%M:%S')
                registrar(fecha, simbolo, f"{anual_actual:.1f}%", "STOP LOSS", ganancia, f"Perdida precio: {perdida_pct:.2f}%")
                posicion_abierta = None
                print(f"Posicion cerrada por stop loss. Resultado: {ganancia} USDT")
                telegram(f"[STOP] STOP LOSS activado en {simbolo}\nResultado: {ganancia} USDT")

            elif anual_actual < 20:
                print("Funding bajo, cerrando posicion...")
                cerrar_short(simbolo, cantidad)
                balance_cierre = get_balance()
                ganancia = round(balance_cierre - balance_entrada, 4)
                fecha = time.strftime('%Y-%m-%d %H:%M:%S')
                registrar(fecha, simbolo, f"{anual_actual:.1f}%", "CERRAR NORMAL", ganancia)
                posicion_abierta = None
                print(f"Posicion cerrada. Ganancia: {ganancia} USDT")
                telegram(f"[OK] Posicion cerrada en {simbolo}\nGanancia: {ganancia} USDT")

            elif oportunidades and oportunidades[0][0] != simbolo and oportunidades[0][2] > anual_actual * 1.5:
                mejor = oportunidades[0]
                print(f"Rotando a mejor oportunidad: {mejor[0]} ({mejor[2]:.1f}%)")
                cerrar_short(simbolo, cantidad)
                posicion_abierta = None

    except Exception as e:
        print(f"Error inesperado: {e}")
        fecha = time.strftime('%Y-%m-%d %H:%M:%S')
        registrar(fecha, "-", "-", "ERROR INESPERADO", "-", str(e))
        time.sleep(60)
        continue

    print("\nRevisando en 60 segundos...")
    time.sleep(60)
