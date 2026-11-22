# 🏛️ OrdenanzaCordoba — Bot Inteligente y Gamificado de Oposiciones en Telegram

[![Enviar Test Oposiciones a Telegram](https://github.com/pakogarcia/ordenanza/actions/workflows/enviar_test.yml/badge.svg)](https://github.com/pakogarcia/ordenanza/actions/workflows/enviar_test.yml)
[![Telegram Bot](https://img.shields.io/badge/Telegram-@ordenayuncordoba__bot-26A5E4?logo=telegram&logoColor=white)](https://t.me/ordenayuncordoba_bot)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Google Gemini](https://img.shields.io/badge/IA-Google%20Gemini-8E75B2?logo=googlegemini&logoColor=white)](https://ai.google.dev/)
[![SQLite](https://img.shields.io/badge/Base%20de%20Datos-SQLite-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Security AES-128](https://img.shields.io/badge/Seguridad-AES--128%20Fernet-2EA44F?logo=letsencrypt&logoColor=white)](#%EF%B8%8F-seguridad-y-privacidad-rgpd)

> ✨ **Proyecto creado por [Pako García](https://github.com/pakogarcia)** para el entrenamiento diario de opositores a **Ordenanza / Subalterno del Ayuntamiento de Córdoba** y Administración Pública.

---

## 🎯 ¿Qué hace este proyecto?

**OrdenanzaCordoba** (`@ordenayuncordoba_bot`) es un sistema automatizado en la nube que transforma los documentos oficiales del temario en una base de datos estructurada de preceptos legales y apuntes conceptuales, y envía **baterías diarias de preguntas tipo test interactivas (*Quiz Polls*) en Telegram** adaptadas al nivel real de Ordenanza (Agrupación Profesional), con **repaso personalizado por suscriptor** y **Liga Semanal gamificada**.

---

## 🚀 Características principales

- 📚 **Procesamiento multitema (Leyes con artículos y Apuntes conceptuales) (`1_procesar_pdf.py`):**
  Extrae y limpia el texto de los PDFs con ordenación visual (`sort=True`), detecta artículos (incluidos `bis`/`ter` y títulos en línea) o corta por bloques conceptuales (`Idea clave:`), generando un inventario auditable en `inventario_temario.txt`.
- ⚖️ **Nivel real de Ordenanza + Moldes de exámenes oficiales (`2_generar_test.py` + `ejemplos_clase.txt`):**
  Usa **Google Gemini** con esquemas estructurados (`Pydantic`) situando siempre la norma y el artículo en el enunciado, con barajado criptográfico de las 4 opciones (`secrets.SystemRandom`) para eliminar cualquier sesgo de posición.
- 🔄 **Repaso 100 % Personalizado por Suscriptor (`fallos_usuario` + `banco_preguntas`):**
  Cada opositor tiene su propia cola privada de fallos con **enfriamiento de 48 horas**. Si un usuario falla un artículo, se le vuelve a preguntar solo a él (`🔄 [Repaso]`) reutilizando preguntas no vistas de la caché `banco_preguntas` (coste `0,00 €`).
- 🏆 **Liga Semanal Gamificada (Podio `🥇🥈🥉`, Medallas y Top 3 Artículos Trampa):**
  - Puntuación oficial de examen: **`+1,00` punto por acierto** y **`-0,25` por fallo**.
  - Insignias desbloqueables: **`🎯` Francotirador** (≥ 85 % acierto) y **`🔥` Constancia** (≥ 5 días activos en la semana).
  - **💀 Top 3 Artículos Trampa:** ranking anónimo semanal de los 3 artículos con mayor tasa de error en todo el grupo.
- 📊 **Informe Semanal Individual (Domingos 20:00 h y `/estadisticas`):**
  Desglose privado por cada Tema con semáforo (`🟢`, `🟡`, `🔴`) y listado de los artículos fallados esa semana.
- 💡 **«TIP DE HOY» al cierre de la jornada (20:00 h):**
  Píldora diaria inédita con la idea clave de un precepto, la trampa típica de tribunal y una regla mnemotécnica.

---

## 🛡️ Seguridad y Privacidad (RGPD)

El módulo de auditoría continua (`5_auditoria_seguridad.py`) se ejecuta automáticamente antes de cada subida y en cada ejecución de GitHub Actions:
- 🔒 **Cifrado AES-128 (`Fernet`):** Todos los nombres y alias de suscriptores en `temario.db` se guardan cifrados (`ENC:...`).
- 🏷️ **Privacidad en el Podio Público:** El ranking muestra por defecto solo primer nombre e inicial del apellido (ej. `Pako G.`) y permite usar `/alias` o `/anonimo` en cualquier momento.
- 🕵️ **Enmascaramiento en logs:** Los registros en la nube ocultan los IDs completos (`***XXXX`).
- 🧹 **Saneamiento y SQL parametrizado:** Validación estricta de entradas, limpieza contra inyección de Markdown y purga automática de metadatos de más de 60 días.

---

## ⏰ Horario de envíos automáticos

| Franja | Hora | Contenido del envío |
| :--- | :---: | :--- |
| ☀️ **Mañana** | **09:00 h** | Cabecera personalizada + **5 preguntas** (incluye repasos personales `🔄` + 1 en negativo + 1 caso práctico) |
| 🕑 **Mediodía** | **14:00 h** | Cabecera personalizada + **5 preguntas** (incluye repasos personales `🔄` + 1 en negativo + 1 caso práctico) |
| 🌙 **Noche** | **20:00 h** | Cabecera personalizada + **5 preguntas** + **💡 TIP DE HOY** *(+ **📊 Informe Semanal** y **🏆 Podio de la Liga** los domingos)* |

---

## 📱 Comandos disponibles en Telegram (`@ordenayuncordoba_bot`)

- **`/start`** — Activa o reactiva tu suscripción gratuita.
- **`/estadisticas`** — Recibe tu informe individual de aciertos y fallos por tema.
- **`/ranking`** — Consulta la clasificación provisional de la Liga Semanal y el Top 3 de artículos trampa.
- **`/alias TuApodo`** — Personaliza el nombre con el que apareces en el podio.
- **`/anonimo`** / **`/visible`** — Oculta o vuelve a mostrar tu nombre en el podio público.
- **`/baja`** (o **`/stop`**) — Pausa el envío de tests en cualquier momento.

---

## 🗂️ Estructura del repositorio

```text
├── .github/workflows/
│   └── enviar_test.yml        # Ejecución en la nube (disparada por Google Apps Script) + auditoría
├── 1_procesar_pdf.py          # Extractor multitema (artículos y bloques Idea clave) + inventario
├── 2_generar_test.py          # Motor IA, repaso personalizado, Liga Semanal, Informe y TIP DE HOY
├── 3_ver_suscriptores.py      # Visualización local descifrada de suscriptores activos
├── 4_ver_estadisticas.py      # Panel local de rendimiento individual y repasos pendientes
├── 5_auditoria_seguridad.py   # Auditoría automatizada de BD, cifrado AES, secretos y repositorio
├── ejemplos_clase.txt         # Preguntas reales de convocatorias oficiales de Ordenanza/Conserje
├── actualizar_temario.bat     # Procesa nuevos PDFs, pasa la auditoría de seguridad y sube a GitHub
├── ver_temario.bat            # Muestra el inventario completo de artículos por tema
├── ver_suscriptores.bat       # Muestra el listado de suscriptores activos
├── ver_estadisticas.bat       # Muestra estadísticas individuales y repasos pendientes
├── auditoria_seguridad.bat    # Ejecuta manualmente la auditoría completa de seguridad
├── inventario_temario.txt     # Desglose actualizado de los 10 temas cargados (424 bloques/artículos)
├── temario.db                 # Base de datos SQLite cifrada (usuarios, banco de preguntas y estadísticas)
├── requirements.txt           # Dependencias del proyecto
└── .env.example               # Plantilla de variables de entorno
```

---

<p align="center">
  Desarrollado con ❤️ por <strong>Pako García</strong> para los futuros Ordenanzas del Ayuntamiento de Córdoba.
</p>
