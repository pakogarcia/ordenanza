# 🏛️ OrdenanzaCordoba — Bot de Entrenamiento de Oposiciones en Telegram

[![Enviar Test Oposiciones a Telegram](https://github.com/pakogarcia/ordenanza/actions/workflows/enviar_test.yml/badge.svg)](https://github.com/pakogarcia/ordenanza/actions/workflows/enviar_test.yml)
[![Telegram Bot](https://img.shields.io/badge/Telegram-@ordenayuncordoba__bot-26A5E4?logo=telegram&logoColor=white)](https://t.me/ordenayuncordoba_bot)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Google Gemini](https://img.shields.io/badge/IA-Google%20Gemini-8E75B2?logo=googlegemini&logoColor=white)](https://ai.google.dev/)
[![SQLite](https://img.shields.io/badge/Base%20de%20Datos-SQLite-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)

> ✨ **Proyecto creado por [Pako García](https://github.com/pakogarcia)** para el entrenamiento diario de opositores a **Ordenanza / Subalterno del Ayuntamiento de Córdoba** y Administración Pública.

---

## 🎯 ¿Qué hace este proyecto?

**OrdenanzaCordoba** (`@ordenayuncordoba_bot`) es un sistema automatizado que transforma los documentos oficiales del temario (Constitución Española, Ley 7/1985 de Bases del Régimen Local, Reglamentos y Ordenanzas Municipales) en una base de datos estructurada de preceptos legales y genera **baterías diarias de preguntas tipo test interactivas (*Quiz Polls*) en Telegram** con estilo y rigor de Tribunal Calificador oficial.

---

## 🚀 Características principales

- 📚 **Procesamiento inteligente multitema (`1_procesar_pdf.py`):**
  Extrae y limpia automáticamente el texto de los archivos PDF del temario mediante `PyMuPDF`, dividiéndolo por artículos (o bloques lógicos con solapamiento) y etiquetando cada precepto con su ley correspondiente en una base de datos SQLite (`temario.db`).
- ⚖️ **Motor de preguntas con estilo de Tribunal Oficial (`2_generar_test.py`):**
  Utiliza la API de **Google Gemini** con esquemas estructurados (`Pydantic`) para redactar preguntas ceñidas estrictamente a la literalidad del artículo, con distractores plausibles (plazos cercanos, intercambio de órganos, excepciones invertidas) y opciones de longitud homogénea.
- 🔄 **Variedad en cada batería de 5 preguntas:**
  Cada tanda combina automáticamente:
  1. **Preguntas directas** sobre el precepto.
  2. **Preguntas en negativo** (*«Señale la afirmación INCORRECTA»*).
  3. **1 Supuesto práctico (`[Caso práctico]`)** aplicado a las funciones reales de un Ordenanza en dependencias municipales.
- 💡 **«TIP DE HOY» al cierre de la jornada:**
  Al finalizar la última tanda del día (20:00 h), el bot envía una píldora de estudio inédita con la idea clave de un artículo, la trampa clásica de examen y una regla mnemotécnica para no fallarla.
- 👥 **Multisuscriptor automático:**
  Cualquier compañero/a que busque **`@ordenayuncordoba_bot`** en Telegram y pulse **INICIAR (`/start`)** queda registrado automáticamente en la base de datos y empieza a recibir las tandas diarias y un mensaje de bienvenida con instrucciones.
- 🔁 **Rotación sin repeticiones:**
  El sistema prioriza siempre los artículos con menor contador `veces_usado` para garantizar que se repasa todo el temario de forma equilibrada antes de iniciar una nueva vuelta con preguntas nuevas.

---

## ⏰ Horario de envíos automáticos

El flujo de **GitHub Actions** se ejecuta en la nube tres veces al día (hora peninsular española):

| Franja | Hora | Contenido del envío |
| :--- | :---: | :--- |
| ☀️ **Mañana** | **09:00 h** | Cabecera de artículos + **5 preguntas tipo test** (directas, negativas y 1 caso práctico) |
| 🕑 **Mediodía** | **14:00 h** | Cabecera de artículos + **5 preguntas tipo test** (directas, negativas y 1 caso práctico) |
| 🌙 **Noche** | **20:00 h** | Cabecera de artículos + **5 preguntas tipo test** + **💡 TIP DE HOY** |

---

## 📱 ¿Cómo participar desde Telegram?

1. Abre Telegram y busca **`@ordenayuncordoba_bot`** (o entra directamente en **[t.me/ordenayuncordoba_bot](https://t.me/ordenayuncordoba_bot)**).
2. Pulsa el botón **INICIAR (`/start`)**.
3. Cuando recibas cada pregunta:
   - Toca una de las 4 opciones: si se marca en **verde (`✅`)** has acertado; si sale **roja (`❌`)**, verás señalada en verde la respuesta correcta.
   - Toca el icono de la **bombilla azul (`💡`)** arriba a la derecha de cada cuestionario para leer la explicación jurídica citando el artículo exacto.

---

## 🗂️ Estructura del repositorio

```text
├── .github/workflows/
│   └── enviar_test.yml       # Automatización en la nube con GitHub Actions (09:00, 14:00 y 20:00 h)
├── 1_procesar_pdf.py         # Extractor y limpiador multitema de PDFs hacia SQLite
├── 2_generar_test.py         # Generador de preguntas con Gemini + envío de Quiz Polls y TIP DE HOY
├── 3_ver_suscriptores.py     # Consulta y sincronización de compañeros suscritos al bot
├── actualizar_temario.bat    # Script en 1 clic para procesar nuevos PDFs y sincronizar con GitHub
├── ver_suscriptores.bat      # Script en 1 clic para ver el listado de usuarios activos
├── temario.db                # Base de datos SQLite (fragmentos, suscriptores y tips_enviados)
├── requirements.txt          # Dependencias del proyecto (pymupdf, google-genai, requests, python-dotenv)
└── .env.example              # Plantilla de variables de entorno
```

---

## ➕ Cómo añadir nuevos temas al bot

1. Coloca el nuevo archivo `.pdf` en la carpeta raíz del proyecto con un nombre descriptivo (por ejemplo, `Tema4-OrdenanzaMunicipal.pdf`).
2. Haz doble clic en **`actualizar_temario.bat`** (o ejecuta `python 1_procesar_pdf.py`).
3. El script descargará el progreso actual de GitHub, añadirá únicamente los artículos nuevos respetando el contador `veces_usado` de los temas anteriores y subirá la base de datos actualizada.

---

<p align="center">
  Desarrollado con ❤️ por <strong>Pako García</strong> para los futuros Ordenanzas del Ayuntamiento de Córdoba.
</p>
