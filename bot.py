import requests
import hmac
import hashlib
import time
import json
import os
import gspread
from google.oauth2.service_account import Credentials
from config import API_KEY, API_SECRET, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

# ── Constantes ────────────────────────────────────────────────────────────────

BASE_URL = "https://fapi.binance.com"
headers = {"X-MBX-APIKEY": API_KEY}

STOP_LOSS_PCT   = 5
VOLUMEN_MINIMO  = 1000000
MAX_VOLATILIDAD = 10
INTERVALO_REPORTE = 30

CAPITAL_MINIMO     = 100
CAPITAL_MAXIMO     = 500
UMBRAL_REINVERSION = 50

# ── Modos de operacion ────────────────────────────────────────────────────────
# AGRESIVO:   funding > 500% anual  → entra sin filtro tecnico, capital completo
# MODERADO:   funding 50-300% anual → requiere RSI + EMA favorables, capital al 50%
# SIN OPCION: funding < 50% anual   → no opera

UMBRAL_AGRESIVO  = 300
UMBRAL_MODERADO  = 50
CAPITAL_MODERADO = 0.5

# Parametros analisis tecnico (modo moderado)
RSI_MINIMO  = 45
EMA_PERIODO = 20

EXCLUIR = ['SLERFUSDT', 'JELLYJELLY', 'NEIROCTOUSUSDT']
ESTADO_FILE = '/root/bot_arbitraje/estado.json'

# ── Estado persistente ────────────────────────────────────────────────────────

def cargar_estado():
    if os.path.exists(ESTADO_FILE):
        try:
            with open(ESTADO_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return None

def guardar_estado(balance_inicial, capital_usdt, umbral_siguiente):
    try:
        with open(ESTADO_FILE, 'w') as f:
            json.dump({
                'balance_inicial': balance_inicial,
                'capital_usdt': capital_usdt,
                'umbral_siguiente': umbral_siguiente
            }, f)
    except Exception as e:
        print(f"Error guardando estado: {e}")

# ── Google Sheets ─────────────────────────────────────────────────────────────

SCOPES = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_file('bot-arbitraje-492116-69f7c9ad5a27.json', scopes=SCOPES)
gc = gspread.authorize(creds)
sheet = gc.open("bot_registro").sheet1

try:
    panel = gc.open("bot_registro").worksheet("Panel")
except:
    panel = gc.open("bot_registro").add_worksheet(title="Panel", rows=20, cols=8)
    panel.update(values=[["Ultima actualizacion", "Simbolo", "Funding anual", "P&L precio", "Ganancia acumulada", "Capital operativo", "Modo", "Estado"]], range_name='A1:H1')

def actualizar_panel(fecha, simbolo, anual, pnl_pct, ganancia_acum, capital_usdt, modo, estado):
    try:
        panel.update(values=[[fecha, simbolo, f"{anual:.1f}%", f"{pnl_pct:.2f}%", f"{ganancia_acum:.2f} USDT", f"{capital_usdt:.0f} USDT", modo, estado]], range_name='A2:H2')
    except Exception as e:
        print(f"Error actualizando panel: {e}")

def registrar(fecha, simbolo, funding, accion, ganancia, error=""):
    try:
        sheet.append_row([fecha, simbolo, funding, accion, ganancia, error])
    except Exception as e:
        print(f"Error al registrar en Sheets: {e}")

def registrar_resumen_diario(fecha, ganancia_dia, capital_usdt):
    try:
        sheet.append_row([fecha, "RESUMEN DIA", "-", "GANANCIA DIARIA", f"{ganancia_dia:.2f}", f"Capital operativo: {capital_usdt:.0f} USDT"])
    except Exception as e:
        print(f"Error al registrar resumen diario: {e}")

# ── Analisis tecnico ──────────────────────────────────────────────────────────

def get_velas(simbolo, intervalo="1h", limite=50):
    try:
        url = f"{BASE_URL}/fapi/v1/klines"
        params = f"symbol={simbolo}&interval={intervalo}&limit={limite}"
        response = requests.get(f"{url}?{params}", timeout=10)
        data = response.json()
        cierres = [float(v[4]) for v in data]
        return cierres
    except Exception as e:
        print(f"Error obteniendo velas de {simbolo}: {e}")
        return []

def calcular_rsi(cierres, periodo=14):
    if len(cierres) < periodo + 1:
        return None
    ganancias = []
    perdidas = []
    for i in range(1, periodo + 1):
        diff = cierres[-(periodo + 1 - i + 1)] - cierres[-(periodo + 1 - i + 2)]
        if diff > 0:
            ganancias.append(diff)
            perdidas.append(0)
        else:
            ganancias.append(0)
            perdidas.append(abs(diff))
    avg_gan = sum(ganancias) / periodo
    avg_per = sum(perdidas) / periodo
    if avg_per == 0:
        return 100
    rs = avg_gan / avg_per
    return 100 - (100 / (1 + rs))

def calcular_ema(cierres, periodo=20):
    if len(cierres) < periodo:
        return None
    k = 2 / (periodo + 1)
    ema = sum(cierres[:periodo]) / periodo
    for precio in cierres[periodo:]:
        ema = precio * k + ema * (1 - k)
    return ema

def analisis_tecnico_favorable(simbolo):
    try:
        cierres = get_velas(simbolo, intervalo="1h", limite=50)
        if not cierres:
            return True, None, None, None
        rsi = calcular_rsi(cierres)
        ema = calcular_ema(cierres, EMA_PERIODO)
        precio_actual = cierres[-1]
        if rsi is None or ema is None:
            return True, rsi, ema, precio_actual
        favorable = rsi >= RSI_MINIMO and precio_actual <= ema
        return favorable, rsi, ema, precio_actual
    except Exception as e:
        print(f"Error en analisis tecnico: {e}")
        return True, None, None, None

def determinar_modo(anual):
    if anual >= UMBRAL_AGRESIVO:
        return "AGRESIVO"
    elif anual >= UMBRAL_MODERADO:
        return "MODERADO"
    else:
        return "SIN OPCION"

# ── Binance ───────────────────────────────────────────────────────────────────

def firmar(params):
    timestamp = int(time.time() * 1000)
    query = params + f"&timestamp={timestamp}"
    signature = hmac.new(
            API_SECRET.encode(),
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

def get_ticker_todos():
    """
    FIX N+1: obtiene stats de TODOS los simbolos en un solo request.
    Retorna diccionario {simbolo: {volumen, volatilidad}}.
    """
    try:
        url = f"{BASE_URL}/fapi/v1/ticker/24hr"
        response = requests.get(url, timeout=10)
        data = response.json()
        resultado = {}
        for item in data:
            simbolo = item['symbol']
            volumen = float(item.get('quoteVolume', 0))
            precio_alto = float(item.get('highPrice', 0))
            precio_bajo = float(item.get('lowPrice', 1))
            volatilidad = ((precio_alto - precio_bajo) / precio_bajo) * 100 if precio_bajo > 0 else 0
            resultado[simbolo] = {'volumen': volumen, 'volatilidad': volatilidad}
        return resultado
    except Exception as e:
        print(f"Error obteniendo ticker global: {e}")
        return {}

def get_mejor_oportunidad():
    """
    FIX N+1: usa get_ticker_todos() para cruzar datos en memoria
    en vez de hacer un request por simbolo.
    """
    try:
        # Solo 2 requests en total en vez de N+1
        url_funding = f"{BASE_URL}/fapi/v1/premiumIndex"
        response = requests.get(url_funding, timeout=10)
        funding_data = response.json()

        ticker_data = get_ticker_todos()

        oportunidades = []
        for item in funding_data:
            simbolo = item['symbol']
            if any(ex in simbolo for ex in EXCLUIR):
                continue
            if not simbolo.endswith('USDT'):
                continue
            rate = float(item['lastFundingRate'])
            anual = rate * 3 * 365 * 100
            if anual < UMBRAL_MODERADO:
                continue
            stats = ticker_data.get(simbolo, {})
            volumen = stats.get('volumen', 0)
            volatilidad = stats.get('volatilidad', 100)
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

def get_step_size(simbolo):
    """
    Obtiene el stepSize del simbolo desde exchangeInfo para calcular
    cantidades precisas que Binance acepte.
    """
    try:
        url = f"{BASE_URL}/fapi/v1/exchangeInfo"
        response = requests.get(url, timeout=10)
        data = response.json()
        for s in data.get('symbols', []):
            if s['symbol'] == simbolo:
                for f in s.get('filters', []):
                    if f['filterType'] == 'LOT_SIZE':
                        return float(f['stepSize'])
        return 1.0
    except Exception as e:
        print(f"Error obteniendo stepSize de {simbolo}: {e}")
        return 1.0

def calcular_cantidad(capital, precio, step_size):
    """Calcula la cantidad correcta respetando el stepSize de Binance."""
    cantidad_raw = capital / precio
    cantidad = (cantidad_raw // step_size) * step_size
    # Redondear decimales segun precision del stepSize
    decimales = len(str(step_size).rstrip('0').split('.')[-1]) if '.' in str(step_size) else 0
    cantidad = round(cantidad, decimales)
    return max(cantidad, step_size)

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

def colocar_stop_loss_nativo(simbolo, cantidad, precio_entrada):
    """
    Coloca una orden STOP_MARKET nativa en Binance.
    Se ejecuta en los servidores de Binance sin depender del script.
    """
    try:
        precio_stop = round(precio_entrada * (1 + STOP_LOSS_PCT / 100), 8)
        url = f"{BASE_URL}/fapi/v1/order"
        params = (
            f"symbol={simbolo}"
            f"&side=BUY"
            f"&type=STOP_MARKET"
            f"&quantity={cantidad}"
            f"&stopPrice={precio_stop}"
            f"&reduceOnly=true"
            f"&workingType=MARK_PRICE"
        )
        response = requests.post(url, params=firmar(params), headers=headers, timeout=10)
        resultado = response.json()
        if 'orderId' in resultado:
            print(f"[STOP NATIVO] Orden colocada en {precio_stop:.8f} (stop {STOP_LOSS_PCT}%)")
            return resultado['orderId']
        else:
            print(f"[STOP NATIVO] Error al colocar: {resultado}")
            return None
    except Exception as e:
        print(f"Error colocando stop loss nativo: {e}")
        return None

def cancelar_orden(simbolo, order_id):
    """Cancela una orden abierta por su ID."""
    try:
        if not order_id:
            return
        url = f"{BASE_URL}/fapi/v1/order"
        params = f"symbol={simbolo}&orderId={order_id}"
        requests.delete(url, params=firmar(params), headers=headers, timeout=10)
        print(f"[STOP NATIVO] Orden {order_id} cancelada")
    except Exception as e:
        print(f"Error cancelando orden: {e}")

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

def verificar_stop_ejecutado(simbolo, order_id):
    """Verifica si la orden de stop loss nativo ya fue ejecutada por Binance."""
    try:
        if not order_id:
            return False
        url = f"{BASE_URL}/fapi/v1/order"
        params = f"symbol={simbolo}&orderId={order_id}"
        response = requests.get(url, params=firmar(params), headers=headers, timeout=10)
        data = response.json()
        return data.get('status') in ['FILLED', 'CANCELED', 'EXPIRED']
    except Exception as e:
        print(f"Error verificando stop: {e}")
        return False

# ── Telegram ──────────────────────────────────────────────────────────────────

ultimo_update_id = None

def telegram(mensaje):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": mensaje}, timeout=10)
    except Exception as e:
        print(f"Error Telegram: {e}")

def check_comandos():
    global ultimo_update_id
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
        params = {"timeout": 1, "allowed_updates": ["message"]}
        if ultimo_update_id:
            params["offset"] = ultimo_update_id + 1
        response = requests.get(url, params=params, timeout=5)
        updates = response.json().get("result", [])
        for update in updates:
            ultimo_update_id = update["update_id"]
            msg = update.get("message", {})
            chat_id = str(msg.get("chat", {}).get("id", ""))
            texto = msg.get("text", "").strip().lower()
            if chat_id != str(TELEGRAM_CHAT_ID):
                continue
            procesar_comando(texto)
    except Exception as e:
        print(f"Error polling Telegram: {e}")

def procesar_comando(texto):
    global bot_pausado, posicion_abierta, balance_inicial, CAPITAL_USDT, umbral_siguiente, stop_order_id

    if texto == "/estado":
        balance_actual = get_balance()
        ganancia_total = round(balance_actual - balance_inicial, 2)
        if posicion_abierta is None:
            telegram(
                f"[Estado]\n"
                f"Sin posicion abierta\n"
                f"Balance: {round(balance_actual, 2)} USDT\n"
                f"Ganancia total: {ganancia_total} USDT\n"
                f"Capital operativo: {CAPITAL_USDT:.0f} USDT\n"
                f"Proximo umbral compuesto: {umbral_siguiente} USDT\n"
                f"Modo: {'PAUSADO' if bot_pausado else 'Activo'}"
            )
        else:
            simbolo, cantidad, rate, balance_entrada, precio_entrada = posicion_abierta
            try:
                precio_url = f"{BASE_URL}/fapi/v1/ticker/price?symbol={simbolo}"
                precio_actual = float(requests.get(precio_url, timeout=10).json()['price'])
                perdida_pct = ((precio_actual - precio_entrada) / precio_entrada) * 100
                pnl = round(balance_actual - balance_entrada, 2)
            except:
                perdida_pct = 0
                pnl = 0
            rate_anual = rate * 3 * 365 * 100
            modo = determinar_modo(rate_anual)
            precio_stop = round(precio_entrada * (1 + STOP_LOSS_PCT / 100), 8)
            telegram(
                f"[Estado]\n"
                f"Simbolo: {simbolo}\n"
                f"Funding: {rate_anual:.1f}% anual\n"
                f"Modo: {modo}\n"
                f"P&L precio: {-perdida_pct:.2f}%\n"
                f"Ganancia posicion: {pnl} USDT\n"
                f"Ganancia total: {ganancia_total} USDT\n"
                f"Balance: {round(balance_actual, 2)} USDT\n"
                f"Capital operativo: {CAPITAL_USDT:.0f} USDT\n"
                f"Stop loss nativo: {precio_stop:.8f}\n"
                f"Proximo umbral compuesto: {umbral_siguiente} USDT\n"
                f"Bot: {'PAUSADO' if bot_pausado else 'Activo'}"
            )

    elif texto == "/ganancia":
        balance_actual = get_balance()
        ganancia = round(balance_actual - balance_inicial, 2)
        telegram(
            f"[Ganancia]\n"
            f"Balance inicial: {round(balance_inicial, 2)} USDT\n"
            f"Balance actual: {round(balance_actual, 2)} USDT\n"
            f"Ganancia total: {ganancia} USDT\n"
            f"Capital operativo actual: {CAPITAL_USDT:.0f} USDT"
        )

    elif texto == "/pausa":
        bot_pausado = True
        telegram("[Pausa] Bot pausado. No abrira nuevas posiciones.\nLa posicion actual sigue activa si hay una abierta.")

    elif texto == "/reanudar":
        bot_pausado = False
        telegram("[Reanudar] Bot reactivado. Buscando oportunidades...")

    elif texto == "/cerrar":
        if posicion_abierta is None:
            telegram("No hay posicion abierta para cerrar.")
        else:
            simbolo, cantidad, rate, balance_entrada, precio_entrada = posicion_abierta
            telegram(f"[Cerrar] Cerrando posicion en {simbolo}...")
            cancelar_orden(simbolo, stop_order_id)
            cerrar_short(simbolo, cantidad)
            balance_cierre = get_balance()
            ganancia = round(balance_cierre - balance_entrada, 2)
            fecha = time.strftime('%Y-%m-%d %H:%M:%S')
            registrar(fecha, simbolo, f"{rate * 3 * 365 * 100:.1f}%", "CERRAR MANUAL", ganancia)
            posicion_abierta = None
            stop_order_id = None
            telegram(f"[OK] Posicion cerrada manualmente.\nGanancia: {ganancia} USDT")

    elif texto == "/ayuda":
        telegram(
            "Comandos disponibles:\n"
            "/estado - Situacion actual del bot\n"
            "/ganancia - Ganancia total acumulada\n"
            "/pausa - Pausar nuevas operaciones\n"
            "/reanudar - Reactivar el bot\n"
            "/cerrar - Cerrar posicion actual\n"
            "/ayuda - Ver esta lista"
        )
    else:
        telegram(f"Comando no reconocido: {texto}\nEscribi /ayuda para ver los comandos disponibles.")

# ── Inicio ────────────────────────────────────────────────────────────────────

print("=== BOT ARBITRAJE FUNDING RATE - DEMO ===")
print(f"Stop loss: {STOP_LOSS_PCT}% (nativo Binance) | Volatilidad max: {MAX_VOLATILIDAD}% | Volumen min: {VOLUMEN_MINIMO} USDT")
print(f"Interes compuesto: umbral {UMBRAL_REINVERSION} USDT | techo {CAPITAL_MAXIMO} USDT")
print(f"Modos: Agresivo >={UMBRAL_AGRESIVO}% | Moderado {UMBRAL_MODERADO}-{UMBRAL_AGRESIVO}% (RSI+EMA)\n")

estado = cargar_estado()
balance_actual_inicio = get_balance()

if estado:
    balance_inicial  = estado['balance_inicial']
    CAPITAL_USDT     = estado['capital_usdt']
    umbral_siguiente = estado['umbral_siguiente']
    print(f"Estado restaurado: balance_inicial={balance_inicial:.2f} | capital={CAPITAL_USDT:.0f} | umbral={umbral_siguiente}")
    telegram(f"Bot Arbitraje reiniciado\nCapital operativo: {CAPITAL_USDT:.0f} USDT\nGanancia acumulada: {round(balance_actual_inicio - balance_inicial, 2)} USDT")
else:
    balance_inicial  = balance_actual_inicio
    CAPITAL_USDT     = CAPITAL_MINIMO
    umbral_siguiente = UMBRAL_REINVERSION
    guardar_estado(balance_inicial, CAPITAL_USDT, umbral_siguiente)
    print(f"Primer inicio: balance_inicial={balance_inicial:.2f} | capital={CAPITAL_USDT:.0f}")
    telegram(f"Bot Arbitraje iniciado\nCapital inicial: {CAPITAL_USDT:.0f} USDT\nComandos: /estado /ganancia /pausa /reanudar /cerrar /ayuda")

registrar("INICIO", "-", "-", f"Bot iniciado | capital={CAPITAL_USDT:.0f} USDT", "-")

posicion_abierta     = None
stop_order_id        = None   # ID de la orden stop loss nativa en Binance
errores_consecutivos = 0
ultimo_reporte       = 0
bot_pausado          = False
dia_actual           = time.strftime('%Y-%m-%d')
balance_inicio_dia   = balance_actual_inicio

# ── Loop principal ────────────────────────────────────────────────────────────

while True:
    try:
        check_comandos()

        print(f"--- {time.strftime('%H:%M:%S')} ---")
        balance = get_balance()
        ganancia_total = round(balance - balance_inicial, 2)
        print(f"Balance: {balance:.2f} USDT | Ganancia total: {ganancia_total} USDT | Capital operativo: {CAPITAL_USDT:.0f} USDT")

        # ── Resumen diario ────────────────────────────────────────────────────
        hoy = time.strftime('%Y-%m-%d')
        if hoy != dia_actual:
            ganancia_dia = round(balance - balance_inicio_dia, 2)
            registrar_resumen_diario(dia_actual, ganancia_dia, CAPITAL_USDT)
            telegram(f"[Resumen {dia_actual}]\nGanancia del dia: {ganancia_dia} USDT\nCapital operativo: {CAPITAL_USDT:.0f} USDT\nGanancia total: {ganancia_total} USDT")
            dia_actual = hoy
            balance_inicio_dia = balance

        # ── Interes compuesto ─────────────────────────────────────────────────
        while ganancia_total >= umbral_siguiente and CAPITAL_USDT < CAPITAL_MAXIMO:
            CAPITAL_USDT = min(CAPITAL_USDT + UMBRAL_REINVERSION, CAPITAL_MAXIMO)
            umbral_siguiente += UMBRAL_REINVERSION
            guardar_estado(balance_inicial, CAPITAL_USDT, umbral_siguiente)
            print(f"[INTERES COMPUESTO] Capital subio a {CAPITAL_USDT:.0f} USDT | Proximo umbral: {umbral_siguiente} USDT")
            telegram(f"[Interes compuesto]\nCapital operativo subio a {CAPITAL_USDT:.0f} USDT\nProximo umbral: {umbral_siguiente} USDT")

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
            stop_order_id = None
            actualizar_panel(
                time.strftime('%Y-%m-%d %H:%M:%S'),
                "-", 0, 0, ganancia_total, CAPITAL_USDT, "-",
                "Pausado" if bot_pausado else "Sin posicion abierta"
            )
            if bot_pausado:
                print("Bot pausado. Esperando comando /reanudar...")
            else:
                oportunidades = get_mejor_oportunidad()
                if oportunidades:
                    simbolo, rate, anual, volumen, volatilidad = oportunidades[0]
                    modo = determinar_modo(anual)

                    print(f"\n[MEJOR OPORTUNIDAD] {simbolo} | Modo: {modo}")
                    print(f"  Funding: {anual:.1f}% anual")
                    print(f"  Volumen 24hs: {volumen:,.0f} USDT")
                    print(f"  Volatilidad 24hs: {volatilidad:.1f}%")

                    if modo == "AGRESIVO":
                        capital_op = CAPITAL_USDT
                        puede_operar = True
                        rsi_val = ema_val = None
                    else:
                        capital_op = max(CAPITAL_MINIMO, int(CAPITAL_USDT * CAPITAL_MODERADO))
                        puede_operar, rsi_val, ema_val, _ = analisis_tecnico_favorable(simbolo)
                        if rsi_val:
                            print(f"  RSI: {rsi_val:.1f} | EMA{EMA_PERIODO}: {ema_val:.6f}")

                    if puede_operar:
                        print(f"Abriendo SHORT con {capital_op} USDT... [{modo}]")
                        precio_url = f"{BASE_URL}/fapi/v1/ticker/price?symbol={simbolo}"
                        precio = float(requests.get(precio_url, timeout=10).json()['price'])

                        # Calcular cantidad respetando stepSize
                        step_size = get_step_size(simbolo)
                        cantidad = calcular_cantidad(capital_op, precio, step_size)

                        resultado = abrir_short(simbolo, cantidad)
                        if 'orderId' in resultado:
                            posicion_abierta = (simbolo, cantidad, rate, balance, precio)

                            # Colocar stop loss nativo en Binance
                            stop_order_id = colocar_stop_loss_nativo(simbolo, cantidad, precio)

                            fecha = time.strftime('%Y-%m-%d %H:%M:%S')
                            registrar(fecha, simbolo, f"{anual:.1f}%", f"ABRIR SHORT [{modo}]", f"Capital: {capital_op}")
                            print(f"Posicion abierta con {capital_op} USDT! [{modo}]")
                            rsi_info = f"\nRSI: {rsi_val:.1f} | EMA{EMA_PERIODO}: {ema_val:.6f}" if rsi_val else ""
                            stop_info = f"\nStop loss nativo: {round(precio * (1 + STOP_LOSS_PCT/100), 8)}"
                            telegram(f"[OK] Posicion abierta en {simbolo}\nFunding: {anual:.1f}% anual\nCapital: {capital_op} USDT\nModo: {modo}{rsi_info}{stop_info}")
                            ultimo_reporte = time.time()
                        else:
                            print(f"Error: {resultado}")
                            if resultado.get('code') == -4411:
                                EXCLUIR.append(simbolo)
                                print(f"{simbolo} excluido automaticamente.")
                    else:
                        rsi_info = f"RSI: {rsi_val:.1f}" if rsi_val else "sin datos"
                        print(f"[MODERADO] Condiciones tecnicas no favorables ({rsi_info}). Esperando...")
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
            modo_actual = determinar_modo(anual_actual)

            ganancia_acum = round(balance - balance_entrada, 2)
            print(f"\nPosicion: {simbolo} | Funding: {anual_actual:.1f}% | Modo: {modo_actual} | P&L precio: {-perdida_pct:.2f}%")

            # Verificar si el stop loss nativo ya fue ejecutado por Binance
            if stop_order_id and verificar_stop_ejecutado(simbolo, stop_order_id):
                balance_cierre = get_balance()
                ganancia = round(balance_cierre - balance_entrada, 2)
                fecha = time.strftime('%Y-%m-%d %H:%M:%S')
                registrar(fecha, simbolo, f"{anual_actual:.1f}%", "STOP LOSS NATIVO", ganancia, f"Perdida precio: {perdida_pct:.2f}%")
                actualizar_panel(fecha, simbolo, anual_actual, -perdida_pct, round(balance_cierre - balance_inicial, 2), CAPITAL_USDT, modo_actual, "STOP LOSS")
                posicion_abierta = None
                stop_order_id = None
                print(f"Stop loss nativo ejecutado por Binance. Resultado: {ganancia} USDT")
                telegram(f"[STOP] Stop loss ejecutado por Binance en {simbolo}\nResultado: {ganancia} USDT")
                time.sleep(60)
                continue

            # Actualizar panel cada INTERVALO_REPORTE minutos
            ahora = time.time()
            if ahora - ultimo_reporte >= INTERVALO_REPORTE * 60:
                fecha = time.strftime('%Y-%m-%d %H:%M:%S')
                actualizar_panel(fecha, simbolo, anual_actual, -perdida_pct, ganancia_total, CAPITAL_USDT, modo_actual, "Posicion abierta")
                registrar(fecha, simbolo, f"{anual_actual:.1f}%", "P&L EN CURSO", f"{ganancia_acum:.2f}")
                print(f"[Sheets] P&L actualizado: {ganancia_acum:.2f} USDT")
                ultimo_reporte = ahora

            if anual_actual < 20:
                print("Funding bajo, cerrando posicion...")
                cancelar_orden(simbolo, stop_order_id)
                cerrar_short(simbolo, cantidad)
                balance_cierre = get_balance()
                ganancia = round(balance_cierre - balance_entrada, 2)
                fecha = time.strftime('%Y-%m-%d %H:%M:%S')
                registrar(fecha, simbolo, f"{anual_actual:.1f}%", "CERRAR NORMAL", ganancia)
                actualizar_panel(fecha, simbolo, anual_actual, -perdida_pct, round(balance_cierre - balance_inicial, 2), CAPITAL_USDT, modo_actual, "Cerrado - buscando nueva oportunidad")
                posicion_abierta = None
                stop_order_id = None
                print(f"Posicion cerrada. Ganancia: {ganancia} USDT")
                telegram(f"[OK] Posicion cerrada en {simbolo}\nGanancia: {ganancia} USDT")

            elif oportunidades and oportunidades[0][0] != simbolo and oportunidades[0][2] > anual_actual * 1.5:
                mejor = oportunidades[0]
                print(f"Rotando a mejor oportunidad: {mejor[0]} ({mejor[2]:.1f}%) [{determinar_modo(mejor[2])}]")
                cancelar_orden(simbolo, stop_order_id)
                cerrar_short(simbolo, cantidad)
                posicion_abierta = None
                stop_order_id = None

    except Exception as e:
        print(f"Error inesperado: {e}")
        fecha = time.strftime('%Y-%m-%d %H:%M:%S')
        registrar(fecha, "-", "-", "ERROR INESPERADO", "-", str(e))
        time.sleep(60)
        continue

    print("\nRevisando en 60 segundos...")
    time.sleep(60)
