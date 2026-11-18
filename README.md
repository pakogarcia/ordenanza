# 🏛️ OrdenanzaCordoba — Bot Inteligente de Oposiciones en Telegram

[![Enviar Test Oposiciones a Telegram](https://github.com/pakogarcia/ordenanza/actions/workflows/enviar_test.yml/badge.svg)](https://github.com/pakogarcia/ordenanza/actions/workflows/enviar_test.yml)
[![Telegram Bot](https://img.shields.io/badge/Telegram-@ordenayuncordoba__bot-26A5E4?logo=telegram&logoColor=white)](https://t.me/ordenayuncordoba_bot)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Google Gemini](https://img.shields.io/badge/IA-Google%20Gemini-8E75B2?logo=googlegemini&logoColor=white)](https://ai.google.dev/)
[![SQLite](https://img.shields.io/badge/Base%20de%20Datos-SQLite-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Security AES-128](https://img.shields.io/badge/Seguridad-AES--128%20Fernet-2EA44F?logo=letsencrypt&logoColor=white)](#%EF%B8%8F-seguridad-y-privacidad-rgpd)

> ✨ **Proyecto creado por [Pako García](https://github.com/pakogarcia)** para el entrenamiento diario de opositores a **Ordenanza / Subalterno del Ayuntamiento de Córdoba** y Administración Pública.

---

## 🎯 ¿Qué hace este proyecto?

**OrdenanzaCordoba** (`@ordenayuncordoba_bot`) es un sistema automatizado en la nube que transforma los documentos oficiales del temario (Constitución Española, Ley 7/1985 de Bases del Régimen Local, ROF RD 2568/1986, TREBEP y Ordenanzas Municipales) en una base de datos estructurada de preceptos legales y envía **baterías diarias de preguntas tipo test interactivas (*Quiz Polls*) en Telegram**, realizando además un **seguimiento adaptativo de los fallos** de los opositores.

---

## 🚀 Características principales

- 📚 **Procesamiento inteligente multitema e inventario (`1_procesar_pdf.py`):**
  Extrae y limpia automáticamente el texto de los archivos PDF con ordenación visual por coordenadas (`sort=True`), detecta artículos (incluidos `bis`, `ter` y artículos con título en línea) y genera un inventario auditable en `inventario_temario.txt`.
- ⚖️ **Motor de preguntas con estilo de Tribunal Oficial (`2_generar_test.py`):**
  Utiliza la API de **Google Gemini** con esquemas estructurados (`Pydantic`) para redactar preguntas ceñidas estrictamente a la literalidad del artículo, con distractores plausibles y longitud homogénea.
- 🔄 **Variedad en cada batería de 5 preguntas:**
  Cada tanda combina automáticamente:
  1. **Preguntas directas** sobre el precepto.
  2. **Preguntas en negativo** (*«Señale la afirmación INCORRECTA»*).
  3. **1 Supuesto práctico (`[Caso práctico]`)** aplicado a las funciones reales de un Ordenanza en dependencias municipales.
- 🧠 **Aprendizaje Adaptativo y Repaso de Fallos (`🔄 [Repaso]`):**
  El bot recoge automáticamente los eventos `poll_answer` de Telegram. Cuando un artículo se falla, queda marcado con prioridad en la base de datos (`fallos_pendientes`) para volver a preguntarse desde otro ángulo en próximas tandas hasta su total asimilación.
- 📊 **Informe Semanal de Rendimiento (Domingos 20:00 h y comando `/estadisticas`):**
  Cada domingo por la noche (o bajo demanda escribiendo `/estadisticas` al bot), cada opositor recibe su análisis individualizado con su porcentaje de aciertos global, **desglose por cada Tema con semáforo (`🟢`, `🟡`, `🔴`)** y la lista exacta de **artículos fallados que debe repasar**.
- 💡 **«TIP DE HOY» al cierre de la jornada:**
  Al finalizar la última tanda del día (20:00 h), el bot envía una píldora de estudio inédita con la idea clave de un artículo, la trampa clásica de examen y una regla mnemotécnica.

---

## 🛡️ Seguridad y Privacidad (RGPD)

El proyecto incorpora un módulo de auditoría continua (`5_auditoria_seguridad.py`) que se ejecuta automáticamente antes de cada subida y en cada ejecución de GitHub Actions:
- 🔒 **Cifrado simétrico AES-128 (`Fernet`):** Todos los nombres de suscriptores almacenados en `temario.db` se guardan cifrados (`ENC:gAAAAAB...`) mediante una clave derivada del secreto de entorno.
- 🕵️ **Enmascaramiento en logs de CI/CD:** Los registros de consola en la nube ocultan los identificadores de usuario (`***XXXX`) para evitar exposición de metadatos.
- 🧹 **Saneamiento y validación estricta:** Limpieza contra inyección de Markdown/caracteres de control, consultas SQL 100 % parametrizadas y purga automática de metadatos antiguos.
- 🔕 **Gestión transparente de altas y bajas:** Soporte nativo para los comandos `/start` (alta/reactivación), `/baja` o `/stop` (pausa inmediata) y desactivación automática ante bloqueos (`HTTP 403`).

---

## ⏰ Horario de envíos automáticos

| Franja | Hora | Contenido del envío |
| :--- | :---: | :--- |
| ☀️ **Mañana** | **09:00 h** | Cabecera de artículos + **5 preguntas tipo test** (incluye refuerzo de fallos `🔄` y 1 caso práctico) |
| 🕑 **Mediodía** | **14:00 h** | Cabecera de artículos + **5 preguntas tipo test** (incluye refuerzo de fallos `🔄` y 1 caso práctico) |
| 🌙 **Noche** | **20:00 h** | Cabecera de artículos + **5 preguntas tipo test** + **💡 TIP DE HOY** *(+ **📊 Informe Semanal** los domingos)* |

---

## 📱 Comandos disponibles en Telegram (`@ordenayuncordoba_bot`)

- **`/start`** — Activa o reactiva la suscripción gratuita a las tandas diarias.
- **`/estadisticas`** (o **`/informe`**) — Solicita tu informe personalizado de aciertos/fallos por tema y artículos a repasar.
- **`/baja`** (o **`/stop`**) — Pausa el envío de cuestionarios en cualquier momento.

---

## 🗂️ Estructura del repositorio

```text
├── .github/workflows/
│   └── enviar_test.yml        # Ejecución en la nube con GitHub Actions + auditoría automática
├── 1_procesar_pdf.py          # Extractor multitema de PDFs hacia SQLite + generador de inventario
├── 2_generar_test.py          # Motor IA, envío de Quiz Polls, repaso de fallos e Informe Semanal
├── 3_ver_suscriptores.py      # Gestión y visualización local descifrada de suscriptores activos
├── 4_ver_estadisticas.py      # Panel local de rendimiento por usuario y artículos pendientes de repaso
├── 5_auditoria_seguridad.py   # Auditoría automatizada de BD, cifrado AES, secretos y repositorio
├── actualizar_temario.bat     # Procesa nuevos PDFs, pasa la auditoría de seguridad y sube a GitHub
├── ver_temario.bat            # Muestra en pantalla el inventario completo de artículos por tema
├── ver_suscriptores.bat       # Muestra el listado de suscriptores activos
├── ver_estadisticas.bat       # Muestra las estadísticas de aciertos/fallos por tema y usuario
├── auditoria_seguridad.bat    # Ejecuta manualmente la auditoría completa de seguridad
├── inventario_temario.txt     # Desglose de los artículos cargados actualmente en la base de datos
├── temario.db                 # Base de datos SQLite con datos de usuarios cifrados
├── requirements.txt           # Dependencias (pymupdf, google-genai, requests, python-dotenv, cryptography)
└── .env.example               # Plantilla de variables de entorno
```

---

<p align="center">
  Desarrollado con ❤️ por <strong>Pako García</strong> para los futuros Ordenanzas del Ayuntamiento de Córdoba.
</p>
