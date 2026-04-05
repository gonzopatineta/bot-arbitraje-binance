import ccxt
import time
import os

exchange = ccxt.binance()

while True:
    os.system('cls')
    exchange.load_markets()
    futuros = exchange.fetch_funding_rates()
    
    print("=== FUNDING RATES ACTUALES ===")
    print("(Solo los mas interesantes, +15% o -15% anual)\n")
    
    oportunidades = []
    
    for simbolo, data in futuros.items():
        rate = data['fundingRate']
        if rate is not None:
            anual = rate * 3 * 365 * 100
            if abs(anual) >= 15:
                oportunidades.append((simbolo, rate, anual))
    
    oportunidades.sort(key=lambda x: abs(x[2]), reverse=True)
    
    for simbolo, rate, anual in oportunidades:
        signo = "+" if anual > 0 else "-"
        print(f"[{signo}] {simbolo}: {rate:.4%} cada 8hs | {anual:.1f}% anual")
    
    print(f"\nTotal oportunidades: {len(oportunidades)}")
    print("\nActualizando en 60 segundos... (Ctrl+C para detener)")
    time.sleep(60)