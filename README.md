# RS Leaders World

Réplica de la consola *RS Leaders* con **selector de país** (25 mercados). Muestra las acciones cuya fuerza relativa (RS) frente al índice de referencia de su país marca un nuevo máximo de 250 sesiones en las últimas 10 sesiones.

## Archivos

| Archivo | Función |
|---|---|
| `index.html` | La web (sin dependencias, lee `data/<pais>.json`) |
| `scanner.py` | Calcula la RS de cada país y escribe los JSON |
| `.github/workflows/scan.yml` | Ejecuta el escáner cada día laborable y publica los datos |
| `requirements.txt` | Dependencias de Python |

## Opción fácil (sin GitHub)

1. Instala Python desde python.org (en Windows marca *Add Python to PATH*).
2. Descomprime la carpeta.
3. Windows: doble clic en `iniciar.bat`. Mac: doble clic en `iniciar.command` (o `python3 iniciar.py`).
4. Elige los países (ej. `es,us,de`) y espera. Se abrirá la web en tu navegador.

Cada vez que quieras datos nuevos, vuelve a ejecutarlo y responde `s`.

## Opción automática (GitHub)

1. Crea un repositorio en GitHub y sube estos archivos tal cual (con la carpeta `.github`).
2. **Settings → Actions → General → Workflow permissions**: marca *Read and write permissions*.
3. **Settings → Pages**: *Deploy from a branch* → `main` → `/ (root)`.
4. **Actions → Escáner RS Leaders → Run workflow**. La primera vez deja `countries` vacío (todos los países, puede tardar 20-60 min) o prueba con `es,us`.
5. Abre `https://TU_USUARIO.github.io/TU_REPO/#es`.

Prueba en local:

```bash
pip install -r requirements.txt
python scanner.py --countries es,de     # genera data/es.json y data/de.json
python -m http.server 8000              # abre http://localhost:8000/#es
```

## Cómo se calcula

- RS = cierre de la acción ÷ cierre del benchmark del país, alineado a las fechas del benchmark.
- Califica si RS > máximo de RS de las 250 sesiones anteriores (excluida la actual) en alguna de las últimas 10 sesiones completadas. Si la sesión de hoy no ha cerrado, se descarta.
- Universo: screener público de TradingView por mercado (acciones comunes y DR). Precios: Yahoo Finance (yfinance).
- Filtros por defecto: EEUU como la web original (precio > 10 $, volumen medio 30d > 30 M$, 350 k acciones en 10d, ADR% > 4). Resto de países, umbrales más bajos (≈ 2 $, 3 M$, 50 k acciones, ADR% > 3), porque sus mercados son más pequeños. Se editan en `PRESETS` dentro de `scanner.py`, y en la web puedes rebajarlos hasta la mitad sin volver a ejecutar nada.
- Los importes se convierten a dólares con tipos de cambio en vivo de Yahoo (con valores de respaldo en `COUNTRIES`).

## Añadir o cambiar un país

En `scanner.py`, añade una entrada a `COUNTRIES` (mercado de TradingView, benchmark de Yahoo, bolsas y sufijos de Yahoo, zona horaria, hora de cierre) y en `index.html` añádelo a `COUNTRIES` con el mismo código.

## Avisos

- TradingView y Yahoo son interfaces públicas no oficiales: pueden cambiar o limitar peticiones. Si un país falla, el resto sigue y el JSON anterior se conserva.
- Algunos tickers de benchmark de Yahoo (p. ej. `PSI20.LS`, `OSEBX.OL`, `^OMX`) pueden cambiar; si un país da "benchmark sin datos", cambia `bench` en `scanner.py`.
- Reino Unido cotiza en peniques (GBX), por eso el precio se muestra en esa unidad.
- Las listas son candidatos a vigilar, no señales de entrada. Solo para investigación.
