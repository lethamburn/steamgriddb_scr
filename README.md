# SteamGridDB Homogenizer

Aplicación web local (Flask + JS vanilla) para descargar en bloque el arte de
tu biblioteca de Steam desde [SteamGridDB](https://www.steamgriddb.com/),
respetando una lista de autores preferidos que tú controlas, y generando una
carpeta `grid_output/` lista para copiar a `userdata/<steamid3>/config/grid/`
en cualquier dispositivo (este PC, la Steam Deck, etc.).

## Qué hace

- Detecta automáticamente tu biblioteca de Steam instalada (rutas típicas de
  Windows/Linux/Mac + bibliotecas adicionales vía `libraryfolders.vdf`).
- Te deja pegar tu API key de SteamGridDB (solo vive en tu navegador).
- Te deja gestionar una lista de autores preferidos, en orden de prioridad,
  con drag & drop.
- Descarga en bloque grid vertical, grid horizontal, hero, logo e icono para
  cada juego, aplicando esta lógica por cada tipo de asset:
  1. Prueba el primer autor de tu lista. Si tiene algo para ese juego, se usa
     su asset con mejor puntuación.
  2. Si no, prueba el siguiente autor de la lista, y así sucesivamente.
  3. Si ninguno de tu lista tiene nada para ese juego, se usa el asset con
     mejor puntuación de **todos** los disponibles (fallback), para que
     ningún juego se quede sin portada.
- Genera `grid_output/` con el naming exacto que espera Steam.
- Muestra progreso en vivo y un resumen final (autores preferidos vs.
  fallback vs. juegos sin coincidencia).

## Qué NO hace (importante)

**La API pública de SteamGridDB no tiene ningún endpoint para listar o
buscar autores por popularidad.** No existe un "ranking de autores"
consultable vía API. Por eso:

- Esta app **no** trae una lista precargada de "autores más populares" —
  eso sería inventar datos que la API no proporciona.
- Tú eres quien gestiona la lista de autores preferidos: escribes el nombre
  de usuario tal como aparece en steamgriddb.com y lo añades a tu lista de
  prioridad.
- Como referencia (no como ranking oficial), puedes explorar la colección
  ["Best Artists"](https://www.steamgriddb.com/collection/3505), curada
  manualmente por la comunidad, para encontrar nombres de autores cuyo
  estilo te guste.

Tampoco descarga arte para juegos que no están instalados localmente (ver
[Roadmap](#roadmap)), ni se integra con Decky Loader ni con la Steam Deck
directamente: solo genera la carpeta en este PC para que la copies tú.

## Interfaz

La interfaz es una única página con cinco secciones, en este orden:

1. **API key de SteamGridDB** — campo para pegarla + botón "Validar".
2. **Biblioteca de Steam** — botón "Detectar biblioteca" (+ ruta manual
   opcional) y contador de juegos encontrados.
3. **Autores preferidos** — añadir/quitar/reordenar (drag & drop) por
   prioridad.
4. **Opciones de descarga** — qué tipos de arte, estilo opcional de grids,
   y si saltar los archivos ya existentes.
5. **Generar carpeta** — botón de inicio, barra de progreso, log en vivo
   (juego actual, qué autor se usó por cada asset) y resumen final.
6. **Galería** — previsualización en miniatura de las imágenes de
   `grid_output/`. Se rellena en vivo mientras avanza la descarga (con
   badge de si vino de un autor preferido o de fallback) y también carga lo
   que ya hubiera de ejecuciones anteriores al abrir la página. Clic en una
   miniatura para verla a tamaño completo.

## Instalación y ejecución

Requiere Python 3.9+.

```bash
git clone <url-de-este-repositorio>
cd steamgriddb-homogenizer
python -m venv venv
source venv/bin/activate        # en Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Abre `http://127.0.0.1:5000` en tu navegador.

## Cómo conseguir la API key

1. Crea una cuenta en [steamgriddb.com](https://www.steamgriddb.com/).
2. Ve a [steamgriddb.com/profile/preferences/api](https://www.steamgriddb.com/profile/preferences/api).
3. Genera una API key y pégala en el primer campo de la interfaz.

**La API key nunca se guarda en el servidor ni en disco.** Vive únicamente en
el `localStorage` de tu navegador y se envía en cada petición al backend
local (`http://127.0.0.1:5000`), que la reenvía tal cual a la API oficial de
SteamGridDB dentro de la cabecera `Authorization` y no la persiste en ningún
sitio: ni en archivos, ni en logs, ni en la carpeta `grid_output/`. Antes de
subir cambios a este repositorio siempre puedes comprobarlo tú mismo con
`git status` y `grep -r "steamgriddb" .` en busca de claves filtradas.

## Cómo funciona el orden de prioridad y el fallback

Para cada juego y cada tipo de asset seleccionado (grid vertical, grid
horizontal, hero, logo, icono):

1. Se consultan todos los assets disponibles en SteamGridDB para ese juego y
   tipo (aplicando el filtro de estilo si lo has elegido para los grids).
2. Se recorre tu lista de autores preferidos **en orden**. En cuanto un autor
   tiene al menos un asset para ese juego/tipo, se elige el suyo con mejor
   puntuación (`score`) y se detiene la búsqueda.
3. Si ningún autor de tu lista tiene nada, se elige el asset con mejor
   puntuación entre **todos** los disponibles, venga de quien venga
   (fallback). Así nunca se queda un juego sin portada si SteamGridDB tiene
   algo para él.
4. Si SteamGridDB no tiene ningún asset de ese tipo para el juego, se salta
   ese asset y se sigue con el resto.

El log en vivo indica, por cada asset descargado, si vino de un autor
preferido o del fallback, y qué autor fue.

## Naming de archivos

Dentro de `grid_output/`, en la raíz del proyecto:

| Tipo             | Nombre de archivo      |
|------------------|-------------------------|
| Grid vertical    | `<appid>p.<ext>`        |
| Grid horizontal  | `<appid>.<ext>`         |
| Hero             | `<appid>_hero.<ext>`    |
| Logo             | `<appid>_logo.<ext>`    |
| Icono            | `<appid>_icon.<ext>`    |

`<ext>` se toma de la extensión real del archivo devuelto por SteamGridDB
(normalmente `.png` o `.jpg`).

## Copiar `grid_output/` a otros dispositivos (incluida la Steam Deck)

1. Cierra Steam en el dispositivo de destino.
2. Localiza tu `steamid3` (la carpeta numérica bajo `userdata/` de esa
   instalación de Steam, o consúltalo en un sitio como
   [steamidfinder.com](https://www.steamidfinder.com/)).
3. Copia **el contenido** de `grid_output/` a
   `userdata/<steamid3>/config/grid/` en ese dispositivo (créala si no
   existe). En la Steam Deck puedes hacerlo por red local, USB o una
   herramienta de sincronización de tu elección.
4. Reinicia Steam. Las portadas personalizadas deberían aparecer.

## Tests

```bash
pytest
```

Incluye tests para el parseo de `appmanifest_*.acf` y `libraryfolders.vdf`
(formato VDF/KeyValues de Valve), incluyendo un escenario de biblioteca
principal + biblioteca adicional en otro disco.

## Roadmap (fuera de alcance de esta versión)

- Soporte para juegos no instalados localmente, usando la Steam Web API para
  listar la biblioteca completa de una cuenta sin depender de los
  `appmanifest_*.acf` locales.
- Empaquetado como ejecutable (.exe/.app) para no depender de Python.
- Integración directa con Decky Loader / Steam Deck (sincronización sin
  copiar archivos a mano).

## Stack técnico

- **Backend**: Python + Flask + `requests`, sin dependencias raras.
- **Frontend**: HTML + CSS + JavaScript vanilla servido por el propio
  Flask, con `fetch()` y polling simple a `/api/download/status` (sin
  websockets). El reordenado de autores usa la API nativa de drag & drop de
  HTML5, sin librerías externas.

## Licencia

MIT. Ver [LICENSE](LICENSE).
