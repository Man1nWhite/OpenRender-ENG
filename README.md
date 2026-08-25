# OpenRender

> **Tu IA de chat favorita, con control total de una carpeta de tu PC.**
> Convierte DeepSeek, Gemini, Kimi, GLM, Qwen, Arena o Meta AI en un agente real que lee, crea y edita archivos, busca en el código y ejecuta comandos de terminal — todo dentro de la carpeta que tú elijas.

**Versión:** 0.0.1 beta · **Plataforma:** Windows · **Licencia:** GPL-3.0

---

## 🌐 English TL;DR

OpenRender turns your normal AI chat (DeepSeek, Gemini, Kimi, GLM, Qwen, Arena, Meta AI — no API keys) into a coding agent with **full control of a local project folder**: it explores the code, reads/creates/edits files, greps content and runs terminal commands (installs, builds, tests, git), sandboxed to the folder you pick. A browser extension injects commands into the chat; a small local bridge (`OpenRender.exe`) executes them. Load `openrender-extension/` unpacked in Chrome/Edge, run the exe, pick a folder, press **Start agent**. Free, GPL-3.0.

---

## 📖 Índice

1. [Qué es y qué hace](#-qué-es-y-qué-hace)
2. [Cómo funciona (arquitectura)](#-cómo-funciona-arquitectura)
3. [Instalación para usuarios](#-instalación-para-usuarios)
4. [Uso diario](#-uso-diario)
5. [Los 12 comandos del agente](#-los-12-comandos-del-agente)
6. [Seguridad: qué puede y qué no puede hacer](#-seguridad)
7. [Estructura del proyecto](#-estructura-del-proyecto)
8. [Compilar desde fuente](#-compilar-desde-fuente)
9. [Tests](#-tests)
10. [Configuración avanzada](#-configuración-avanzada)
11. [Solución de problemas](#-solución-de-problemas)
12. [Roadmap y limitaciones](#-roadmap-y-limitaciones)
13. [Créditos y licencia](#-créditos-y-licencia)

---

## 🤖 Qué es y qué hace

Los modelos de IA web (DeepSeek, Gemini…) son excelentes programando, pero **no pueden tocar tu disco**: solo escriben texto que tú tienes que copiar y pegar archivo por archivo.

**OpenRender cierra ese hueco.** Es un puente entre el chat y tu disco:

- El modelo escribe **comandos JSON** dentro de su respuesta normal (`{"command": "edit_file", ...}`)
- La **extensión de navegador** detecta esos comandos en la página del chat
- El **puente local** (`OpenRender.exe`) los ejecuta contra tu carpeta
- El resultado vuelve al chat como otro mensaje, y la IA continúa sola

El resultado: pides *"arregla el bug del login y corre los tests"* y la IA explora el proyecto, lee los archivos, aplica los cambios, ejecuta `npm test` y te reporta — sin que toques el teclado.

### Características

| | |
|---|---|
| 📁 Control total de UNA carpeta | Leer, crear, editar, borrar, mover — encerrado en ella |
| 💻 Terminal integrada | Instalar dependencias, compilar, correr tests, usar git |
| 🔎 Búsqueda real | Por nombre (glob) y por contenido (texto o regex) |
| 🧠 Memoria persistente | Notas del proyecto en `PROJECT_MEMORY.md` entre sesiones |
| 🗂️ Multi-proyecto | Historial de carpetas con cambio en 1 clic desde el chat |
| 🔌 Sin API keys | Usa las webs de chat gratis que ya conoces |
| 🔒 Sandboxed | Nada fuera de la carpeta elegida; borrados amplios piden confirmación |
| ➕ MCP extensible | Añade otros servidores MCP (Blender, etc.) como addons |

---

## ⚙️ Cómo funciona (arquitectura)

```
┌─────────────────────────┐
│  Chat web (DeepSeek,    │   El modelo responde con texto +
│  Gemini, Kimi, GLM,     │   comandos JSON dentro de bloques
│  Qwen, Arena, Meta AI)  │   de código
└───────────┬─────────────┘
            │  la extensión lee la página (DOM)
┌───────────▼─────────────┐
│  Extensión Chrome/Edge  │   openrender-extension/
│  - bucle agéntico       │   parser → executor → feedback
│  - UI: barra, chips,    │
│    menú de carpetas     │
└───────────┬─────────────┘
            │  WebSocket ws://127.0.0.1:17613
┌───────────▼─────────────┐
│  Puente local           │   bridge.py  →  dist/OpenRender.exe
│  - lanza servidores MCP │   (PyInstaller: Python incluido)
│  - enruta cada comando  │
│  - selector de carpeta  │
└───────────┬─────────────┘
            │  stdio (JSON-RPC, protocolo MCP)
┌───────────▼─────────────┐
│  Servidor workspace     │   workspace_mcp.py
│  (embebido en el exe)   │   12 herramientas sobre TU carpeta
└───────────┬─────────────┘
            ▼
   📂 Documentos/mi-proyecto/
```

**Flujo de un comando:**

1. Tú pides algo en el chat.
2. La IA responde con un bloque ```json``` tipo `{"command": "read_file", "params": {"path": "src/app.py"}}`.
3. La extensión lo parsea (`core/parser.js`), lo valida contra el catálogo de herramientas y lo envía al puente por WebSocket (`background.js`).
4. El puente lo enruta al servidor correcto y espera el resultado (con reintentos, watchdogs y auto-restart si el servidor murió).
5. El resultado vuelve al chat como mensaje del usuario ("Output of 'read_file': …"), camuflado visualmente como una tarjeta.
6. La IA lo lee y decide el siguiente paso. Y así hasta terminar.

Todo es **local**: ni tu código ni tu carpeta salen de tu máquina (solo viajan al chat lo que la IA lee explícitamente, igual que si pegaras los archivos a mano).

---

## 🚀 Instalación para usuarios

> **Requisitos:** Windows 10/11 x64 + Chrome o Edge. No necesita Python ni nada más (todo va dentro del exe).

### Opción A — Instalador (recomendado)

1. Descarga y ejecuta **`OpenRender-Setup-0.0.1-beta.exe`**
2. Siguiente → Siguiente. Se instala en **`Documentos\OpenRender`**:
   ```
   Documentos\OpenRender\
   ├── OpenRender.exe          ← el programa
   ├── openrender-extension\   ← la extensión
   └── LEEME.txt               ← guía rápida
   ```
   Con accesos directos en escritorio y menú inicio.

### Opción B — Portable

Descarga `OpenRender-0.0.1-beta-windows-x64.zip`, descomprímelo donde quieras. Mismo contenido.

> ℹ️ Windows mostrará un aviso azul ("Windows protegió tu PC") porque el exe no está firmado digitalmente: **Más información → Ejecutar de todas formas**.

### Primera ejecución (asistida)

Al abrir `OpenRender.exe` por primera vez aparece un **tutorial de 3 pasos**:

1. **Cargar la extensión** (única vez): `chrome://extensions` → *Modo de desarrollador* → *Cargar descomprimida* → selecciona la carpeta `openrender-extension`. El tutorial te ofrece abrir esa carpeta automáticamente.
2. Escribe **`s` (Listo)** → se abre el selector para elegir **tu carpeta de proyecto**.
3. Listo. Las siguientes veces entra directo con la carpeta guardada.

---

## 🖱️ Uso diario

| Paso | Acción |
|---|---|
| 1 | Abre **OpenRender.exe** (minimiza la ventana negra — es el puente) |
| 2 | Ve a [chat.deepseek.com](https://chat.deepseek.com) *(recomendado)*, Gemini, [kimi.com](https://www.kimi.com), [chat.z.ai](https://chat.z.ai), [chat.qwen.ai](https://chat.qwen.ai) o [arena.ai](https://arena.ai) |
| 3 | Abre un chat **nuevo** → pulsa **▶ Start agent** en la barra verde sobre el cuadro de texto |
| 4 | Pide lo que quieras. Cada operación aparece como una tarjeta en el chat |

Ejemplos de peticiones reales:

```
"Explora el proyecto y explícame cómo está estructurado"
"Añade validación al formulario de registro y prueba que funciona"
"Este test falla: averigua por qué y arréglalo"
"Crea un endpoint /api/users con tests"
"Sube todos los cambios a un branch nuevo"
"Cambia el nombre de la función procesar() a process_order() en todo el proyecto"
```

**Panel ⌄ de la barra:** cambiar de carpeta de trabajo (historial con 1 clic), **+ Añadir carpeta** (selector nativo), cambiar de IA, prompt personalizado, gestionar servidores MCP addon.

**Cambiar de proyecto:** también puedes tocar otra carpeta del historial en cualquier momento — la IA pasa a trabajar ahí al instante y la anterior queda fuera de su alcance.

---

## 🛠️ Los 12 comandos del agente

La IA solo puede usar estos comandos (los descubre con `list_commands` al empezar):

| Comando | Qué hace |
|---|---|
| `workspace_info` | Vista general: ruta raíz, conteo de archivos, entradas principales |
| `tree` | Árbol de directorios recursivo (ignora `node_modules`, `.git`, etc.) |
| `list_directory` | Listado de una carpeta con tamaños |
| `read_file` | Lee un archivo con líneas numeradas (paginado con offset/limit) |
| `write_file` | Crea un archivo o lo sobrescribe completo |
| `edit_file` | Reemplazo exacto tipo diff: `old_string` → `new_string` (+ `replace_all`) |
| `create_folder` | Crea carpetas (con padres) |
| `delete_path` | Borra archivos/carpetas (destructivo, pide confirmación en scope amplio) |
| `move_path` | Mover o renombrar |
| `search_files` | Busca por nombre con globs (`**/*.py`, `src/**/*.js`…) |
| `grep_files` | Busca DENTRO de archivos (texto o regex, filtrable por glob) |
| `run_command` | Ejecuta comandos de terminal en la raíz (timeout configurable) |

Además mantiene **memoria persistente** en `PROJECT_MEMORY.md`: arquitectura, convenciones, decisiones y preferencias del usuario, compartidas entre todas las sesiones.

---

## 🔒 Seguridad

- **Sandbox estricto:** toda ruta se resuelve dentro de la carpeta elegida. `../`, rutas absolutas externas y unit links fuera → rechazados. La raíz nunca se puede borrar ni mover.
- **Borrados protegidos:** `delete_path` es permanente; el sistema prompt ordena a la IA confirmar contigo antes de cualquier borrado más allá de lo que pediste explícitamente.
- **Solo localhost:** el puente escucha en `127.0.0.1:17613`; nada expuesto a la red.
- **Tú eliges la carpeta:** la IA solo ve lo que esté dentro. Cambias de proyecto = cambia su mundo.
- **Código abierto:** todo lo que ejecuta está en este repo, auditable línea por línea.

Aun así: es una beta con control real de tu disco. **Usa git**, revisa lo que hace y no le des carpetas con secretos (.env, llaves) si no hace falta.

---

## 📂 Estructura del proyecto

```
OpenRender/
├── bridge.py                    # Puente WebSocket ↔ servidores MCP (stdio)
│                                # - selector/tutorial de carpeta (1ª vez)
│                                # - cambio de carpeta en caliente (desde el chat)
│                                # - auto-restart de servidores, watchdogs
│                                # - modo empaquetado: se relanza como worker
├── workspace_mcp.py             # Servidor MCP principal: 12 herramientas de
│                                # archivos+terminal sobre la carpeta elegida
├── config.json                  # Estado local (carpeta activa, historial) - NO se sube
├── config.example.json          # Plantilla de configuración
├── start.bat / MacOS_Start.command  # Lanzadores para desarrollo (sin exe)
│
├── openrender-extension/        # Extensión de navegador (Chrome/Edge, MV3)
│   ├── manifest.json
│   ├── background.js            # WebSocket al puente + caché de estado
│   ├── core/
│   │   ├── main.js              # Bucle agéntico + UI (barra, chips, menú)
│   │   ├── parser.js            # Parser de comandos JSON (tolerante a Markdown)
│   │   └── config.js            # System prompt + notas de herramientas
│   ├── providers/               # Un adaptador DOM por sitio de chat:
│   │   ├── deepseek.js          #   deepseek.js, gemini.js, kimi.js, glm.js,
│   │   ├── gemini.js            #   qwen.js(+qwen-net.js), arena.js, meta.js
│   │   └── …                    #   (selectores, envío, detección de generación)
│   ├── overlay.css              # Estilos de barra/chips/menú
│   └── popup.html/js            # Popup del icono: estado del puente
│
├── build.py                     # Empaqueta el exe (PyInstaller) + zip portable
├── build_installer.bat          # Compila el instalador (Inno Setup)
├── installer/OpenRender-installer.iss
│
├── test_workspace_mcp.py        # 30 pruebas del servidor de archivos
├── test_bridge_e2e.py           # Puente completo por WebSocket (13 checks)
├── test_exe_e2e.py              # El exe empaquetado, end-to-end
└── test_installer.py            # Instalar→arrancar→desinstalar del setup
```

**Detalles de diseño clave:**

- **Protocolo MCP estándar** (JSON-RPC sobre stdio): cualquier servidor MCP puede añadirse como addon desde el panel; el puente agrega sus herramientas y enruta por nombre.
- **Un exe, dos roles:** en modo empaquetado, `bridge.py` se relanza a sí mismo con `--workspace-worker` para servir el workspace embebido.
- **Provider pattern:** `core/main.js` nunca toca el DOM del chat; cada sitio tiene su adaptador. Añadir una nueva IA = un archivo nuevo en `providers/`.
- **Anti-fragilidad del loop:** timeouts duros en cada llamada, reintentos ante caídas transitorias, deduplicación de comandos tras recargas, pausa automática cuando la pestaña pierde el foco.

---

## 🔨 Compilar desde fuente

Requisitos: Python 3.9+ y `pip install pyinstaller pillow`.

```bat
python build.py             rem → dist\OpenRender.exe + release\*.zip
build_installer.bat         rem → installer-output\OpenRender-Setup-*.exe (requiere Inno Setup, gratis)
```

Para probar en desarrollo sin empaquetar: `start.bat` (busca Python solo, instala `websockets` si falta).

---

## ✅ Tests

```bat
python test_workspace_mcp.py   rem protocolo MCP: 30 pruebas (CRUD, grep, seguridad CRLF…)
python test_bridge_e2e.py      rem arranque real del puente + cambio de carpeta en caliente
python test_exe_e2e.py         rem lo mismo contra dist\OpenRender.exe
python test_installer.py       rem instalación silenciosa → arranque → desinstalación
node test-parser.js            rem (en openrender-extension\) parser de comandos
```

---

## ⚙️ Configuración avanzada

**`config.json`** (junto al exe; ver `config.example.json`):

```json
{
  "workspaceFolder": "D:\\proyectos\\mi-app",   // carpeta activa ("" = preguntar)
  "workspaceHistory": ["D:\\proyectos\\mi-app"], // historial del menú (máx 8)
  "mcpServers": {
    "workspace": { "command": "workspace_mcp.py", "args": [] },
    "blender":   { "command": "npx", "args": ["-y", "@alguna/mcp-blender"] }
  }
}
```

| Variable de entorno | Efecto |
|---|---|
| `ZS_WORKSPACE_ROOT` | Fuerza la carpeta de trabajo (se salta el selector) |
| `ZS_BRIDGE_PORT`    | Cambia el puerto del puente (defecto `17613`) |

**Añadir otro servidor MCP** (Blender, Sketchfab…): panel ⌄ → *MCP servers* → nombre + comando de inicio. Se reinicia el puente y sus herramientas aparecen junto a las del workspace.

---

## 🩺 Solución de problemas

| Síntoma | Solución |
|---|---|
| Barra gris "Bridge offline" | La ventana negra está cerrada → abre `OpenRender.exe` |
| Punto amarillo | El puente vive pero aún no hay carpeta → revisa la ventana negra |
| La IA responde en texto, sin comandos | Recuérdale que use los comandos, o abre chat nuevo y Start agent |
| "No response from server" puntual | Reintenta; el puente reintenta solo ante caídas breves |
| Quiero otra carpeta | Panel ⌄ → Project folder → toca otra o "+ Añadir carpeta" |
| Puerto ocupado | Cierra otro OpenRender abierto, o `set ZS_BRIDGE_PORT=17614` antes de abrir |

Logs detallados: ventana del puente y `logs\bridge_debug.log` (junto al exe).

---

## 🗺️ Roadmap y limitaciones

**Beta actual (0.0.1):** Windows only · la extensión debe cargarse a mano (Chrome/Edge no permiten instalar extensiones desde programas externos) · Gemini/Kimi pueden ser inestables en sesiones largas (en Arena usa modo **Direct**) · `run_command` bloquea hasta 10 min máximo.

**Ideas en cola:** firma digital del instalador · publicación en Chrome Web Store · versión macOS/Linux del exe · streaming del output de comandos largos · selección múltiple de carpetas simultáneas.

---

## 💬 Créditos y licencia

OpenRender es un fork fuertemente retrabajado de [ZeroScript Free](https://github.com/sebattfg/ZeroScript-Free) (de agente de Roblox Studio a agente de carpetas locales), que a su vez toma ideas de conexión MCP-addon de [javnpa](https://github.com/javnpa). Gracias a ambos. 🙏

Licencia **GPL-3.0** — ver [LICENSE](LICENSE). Úsalo, modifícalo y compártelo libremente.

---
*Hecho con ❤️ para dejar de copiar y pegar código a mano.*
