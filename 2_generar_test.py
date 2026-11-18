from datetime import datetime, timezone
import json
import os
import random
import sqlite3
import sys
import time
import requests
from dotenv import load_dotenv
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, Field


DB_PATH = "temario.db"
EJEMPLOS_PATH = "ejemplos_clase.txt"
NUM_PREGUNTAS_POR_TANDA = int(os.getenv("NUM_PREGUNTAS", "5"))
MAX_REPASOS_POR_TANDA = 2
FALLBACK_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3.6-flash",
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.5-flash",
]

# Límites máximos permitidos por Telegram Poll (modo quiz)
TELEGRAM_MAX_PREGUNTA = 300
TELEGRAM_MAX_OPCION = 100
TELEGRAM_MAX_EXPLICACION = 200

MENSAJE_BIENVENIDA = (
    "👋 ¡Bienvenido/a a *OrdenanzaCordoba* (`@ordenayuncordoba_bot`), "
    "el bot de estudio creado por *Pako García*!\n\n"
    "✅ Tu suscripción está activa. Recibirás automáticamente:\n"
    "• *5 preguntas tipo test* en cada franja (*09:00, 14:00 y 20:00 h*).\n"
    "• El *💡 TIP DE HOY* cada noche a las 20:00 h.\n"
    "• Un *📊 Informe Semanal* los domingos por la noche con tus estadísticas por tema y los artículos que más necesitas repasar (además, los artículos fallados se vuelven a preguntar en días siguientes para afianzarlos).\n\n"
    "🧭 *¿Cómo responder a los tests?*\n"
    "1️⃣ Toca directamente la opción que creas correcta.\n"
    "2️⃣ Si sale *verde (✅)*, has acertado; si sale *roja (❌)*, verás marcada en verde la opción correcta.\n"
    "3️⃣ Toca el icono de la *bombilla azul (💡)* arriba a la derecha de cada tarjeta para leer la explicación jurídica con el artículo exacto."
)


class PreguntaTest(BaseModel):
    pregunta: str = Field(
        description="Enunciado de la pregunta tipo test (máximo 280 caracteres)."
    )
    opciones: list[str] = Field(
        description="Lista de exactamente 4 opciones de respuesta (máximo 95 caracteres cada una), sin letras iniciales como a), b), etc."
    )
    indice_correcta: int = Field(
        description="Índice entero de 0 a 3 que señala cuál de las 4 opciones es la respuesta correcta."
    )
    explicacion: str = Field(
        description="Explicación jurídica concisa (máximo 190 caracteres) citando el artículo exacto."
    )


SYSTEM_INSTRUCTION = """Eres un vocal experto de un Tribunal Calificador de oposiciones de la Administración General del Estado (AGE) y de Ordenanza/Subalterno del Ayuntamiento de Córdoba.
Tu misión es redactar preguntas tipo test oficiales de alta calidad técnica siguiendo estas reglas estrictas:

1. LITERALIDAD NORMATIVA: Básate única y exclusivamente en el texto literal del artículo o fragmento proporcionado. No utilices conocimientos externos ni supongas preceptos no incluidos en el fragmento.
2. ESTILO Y ALTERNANCIA: Redacta con rigor jurídico propio de exámenes oficiales. Alterna según se te pida entre preguntas directas, preguntas en negativo («Señale la afirmación INCORRECTA») y supuestos prácticos aplicados a un Ordenanza del Ayuntamiento de Córdoba.
3. DISTRACTORES PLAUSIBLES: Diseña opciones incorrectas verosímiles empleando trampas clásicas de examen oficial:
   - Alterar plazos, edades o mayorías cercanas (ej. mayoría absoluta por mayoría simple, tres quintos por dos tercios).
   - Intercambiar órganos o sujetos (ej. Gobierno, Cortes Generales, Congreso, Senado, Rey, Tribunal Constitucional, Alcalde, Pleno, ley orgánica por ley ordinaria).
   - Invertir excepciones, condiciones o matices verbales («podrá» por «deberá», «en todo caso» por «en ningún caso», «salvo» por «incluso»).
4. HOMOGENEIDAD FORMAL: Las 4 opciones deben mantener una longitud, estructura sintáctica y tono jurídico muy similares entre sí para que ninguna destaque visualmente. No incluyas prefijos como «a)», «b)», «1.» al inicio de cada opción.
5. LÍMITES ESTRICTOS DE LONGITUD:
   - pregunta: máximo 280 caracteres.
   - opciones: exactamente 4 textos de máximo 95 caracteres cada uno.
   - indice_correcta: entero entre 0 y 3.
   - explicacion: máximo 190 caracteres, citando siempre el artículo exacto de referencia.
"""


def inicializar_tablas_auxiliares(db_path: str = DB_PATH) -> None:
    """Asegura que existan todas las tablas y columnas necesarias para suscriptores, tips y estadísticas."""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        # Asegurar columna fallos_pendientes en fragmentos
        columnas = {
            info[1] for info in cursor.execute("PRAGMA table_info(fragmentos)").fetchall()
        }
        if columnas and "fallos_pendientes" not in columnas:
            cursor.execute(
                "ALTER TABLE fragmentos ADD COLUMN fallos_pendientes INTEGER DEFAULT 0"
            )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS suscriptores (
                chat_id TEXT PRIMARY KEY,
                nombre TEXT,
                fecha_alta TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tips_enviados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fragmento_id INTEGER,
                referencia TEXT,
                tip TEXT,
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tandas_enviadas (
                clave_tanda TEXT PRIMARY KEY,
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS encuestas_enviadas (
                poll_id TEXT PRIMARY KEY,
                chat_id TEXT,
                fragmento_id INTEGER,
                tema TEXT,
                referencia TEXT,
                indice_correcta INTEGER,
                fecha_envio TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS respuestas_usuarios (
                poll_id TEXT,
                chat_id TEXT,
                fragmento_id INTEGER,
                tema TEXT,
                referencia TEXT,
                opcion_elegida INTEGER,
                indice_correcta INTEGER,
                acertada INTEGER,
                fecha_respuesta TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (poll_id, chat_id)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS estado_bot (
                clave TEXT PRIMARY KEY,
                valor TEXT
            )
            """
        )
        conn.commit()


def extraer_tema_de_referencia(referencia: str) -> str:
    """Extrae el nombre del tema a partir de la referencia ('Tema1 - Constitucion | Artículo 14')."""
    if " | " in referencia:
        return referencia.split(" | ", 1)[0].strip()
    return "Temario General"


def obtener_clave_tanda_actual() -> str:
    """Devuelve un identificador único del día y franja actual (ej. '2026-11-16_MEDIODIA')."""
    ahora = datetime.now(timezone.utc)
    fecha_str = ahora.strftime("%Y-%m-%d")
    if ahora.hour < 11:
        franja = "MANANA"
    elif ahora.hour < 16:
        franja = "MEDIODIA"
    else:
        franja = "NOCHE"
    return f"{fecha_str}_{franja}"


def tanda_ya_enviada(clave_tanda: str, db_path: str = DB_PATH) -> bool:
    """Comprueba si la tanda programada de esta franja ya se envió hoy."""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM tandas_enviadas WHERE clave_tanda = ?",
            (clave_tanda,),
        )
        return cursor.fetchone() is not None


def registrar_tanda_enviada(clave_tanda: str, db_path: str = DB_PATH) -> None:
    """Registra la tanda actual como enviada para evitar duplicados."""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO tandas_enviadas (clave_tanda) VALUES (?)",
            (clave_tanda,),
        )
        conn.commit()


def enviar_mensaje_telegram(
    bot_token: str,
    channel_id: str,
    texto: str,
) -> None:
    """Envía un mensaje de texto a un chat o canal de Telegram."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    resp = requests.post(
        url,
        json={
            "chat_id": channel_id,
            "text": texto,
            "parse_mode": "Markdown",
        },
        timeout=20,
    )
    if not resp.ok:
        requests.post(
            url,
            json={
                "chat_id": channel_id,
                "text": texto,
            },
            timeout=20,
        )


def construir_informe_semanal_usuario(
    chat_id: str,
    nombre: str,
    dias: int = 7,
    db_path: str = DB_PATH,
) -> str | None:
    """
    Construye el Informe Semanal de rendimiento de un suscriptor:
    - Total respondidas, aciertos, fallos y % de acierto.
    - Desglose por cada Tema ordenado de peor a mejor resultado.
    - Artículos concretos fallados que debe repasar (y que el bot volverá a preguntar).
    """
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT COUNT(*), SUM(acertada)
            FROM respuestas_usuarios
            WHERE chat_id = ?
              AND fecha_respuesta >= datetime('now', ?)
            """,
            (str(chat_id), f"-{dias} days"),
        )
        fila_tot = cursor.fetchone()
        total_resp = fila_tot[0] or 0
        aciertos = fila_tot[1] or 0

        if total_resp == 0:
            return None

        fallos = total_resp - aciertos
        pct_global = round((aciertos / total_resp) * 100, 1)

        cursor.execute(
            """
            SELECT tema, COUNT(*) AS tot, SUM(acertada) AS ok
            FROM respuestas_usuarios
            WHERE chat_id = ?
              AND fecha_respuesta >= datetime('now', ?)
            GROUP BY tema
            ORDER BY (CAST(SUM(acertada) AS REAL) / COUNT(*)) ASC, tot DESC
            """,
            (str(chat_id), f"-{dias} days"),
        )
        por_tema = cursor.fetchall()

        cursor.execute(
            """
            SELECT DISTINCT referencia
            FROM respuestas_usuarios
            WHERE chat_id = ?
              AND acertada = 0
              AND fecha_respuesta >= datetime('now', ?)
            ORDER BY fecha_respuesta DESC
            LIMIT 12
            """,
            (str(chat_id), f"-{dias} days"),
        )
        refs_falladas = [r[0] for r in cursor.fetchall()]

    lineas = [
        f"📊 *INFORME SEMANAL DE ESTUDIO — {nombre}*",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"🎯 *Respondidas:* {total_resp} | ✅ *Aciertos:* {aciertos} | ❌ *Fallos:* {fallos} (*{pct_global}%*)",
        "",
        "📚 *Rendimiento por Temas (de mayor a menor prioridad de repaso):*",
    ]

    tema_mas_flojo = None
    for idx, (tema, tot, ok) in enumerate(por_tema):
        ok = ok or 0
        pct = round((ok / tot) * 100, 1)
        if idx == 0 and pct < 80:
            tema_mas_flojo = tema
        if pct >= 80:
            icono = "🟢"
        elif pct >= 60:
            icono = "🟡"
        else:
            icono = "🔴"
        lineas.append(f"  {icono} *{tema}:* {ok}/{tot} aciertos (*{pct}%*)")

    if tema_mas_flojo:
        lineas.append(f"\n🔎 *Tema que más necesitas reforzar:* _{tema_mas_flojo}_")

    if refs_falladas:
        lineas.append("\n⚠️ *Artículos fallados esta semana (marcados para volver a preguntarse):*")
        for ref in refs_falladas:
            lineas.append(f"  • {ref}")
    else:
        lineas.append("\n🏆 *¡Enhorabuena! No has fallado ningún artículo esta semana.*")

    lineas.append(
        "\n🔄 _Los artículos fallados quedan priorizados en la base de datos para volver a salir en próximas tandas hasta su total asimilación._"
    )
    return "\n".join(lineas)


def sincronizar_suscriptores(
    bot_token: str,
    channel_id_principal: str | None,
    db_path: str = DB_PATH,
) -> list[str]:
    """
    Lee `getUpdates` de Telegram para:
    1. Dar de alta nuevos suscriptores (/start o respuestas a encuestas).
    2. Procesar los eventos `poll_answer` registrando aciertos y fallos por tema/artículo
       y marcando `fallos_pendientes` en los artículos fallados para volver a preguntarlos.
    3. Responder al comando `/estadisticas` si algún usuario lo solicita.
    """
    inicializar_tablas_auxiliares(db_path)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        if channel_id_principal and channel_id_principal != "@tu_canal_o_id_numerico_aqui":
            cursor.execute(
                "INSERT OR IGNORE INTO suscriptores (chat_id, nombre) VALUES (?, ?)",
                (str(channel_id_principal).strip(), "Pako García"),
            )

        cursor.execute("SELECT chat_id, nombre FROM suscriptores")
        existentes = {fila[0]: fila[1] for fila in cursor.fetchall()}

        cursor.execute("SELECT valor FROM estado_bot WHERE clave = 'ultimo_update_id'")
        fila_offset = cursor.fetchone()
        offset = int(fila_offset[0]) + 1 if fila_offset else None

        params = {"timeout": 5}
        if offset is not None:
            params["offset"] = offset

        max_update_id = None
        solicitudes_estadisticas = set()

        try:
            url_updates = f"https://api.telegram.org/bot{bot_token}/getUpdates"
            resp = requests.get(url_updates, params=params, timeout=15)
            datos = resp.json()
            if resp.ok and datos.get("ok"):
                for upd in datos.get("result", []):
                    uid = upd.get("update_id")
                    if uid is not None:
                        max_update_id = uid if max_update_id is None else max(max_update_id, uid)

                    # A) Procesar mensajes de texto (/start, /estadisticas, etc.)
                    msg = upd.get("message") or upd.get("my_chat_member") or {}
                    chat = msg.get("chat", {})
                    cid = str(chat.get("id", "")).strip()
                    texto_msg = (msg.get("text") or "").strip().lower()
                    if cid:
                        nombre = (
                            f"{chat.get('first_name', '')} {chat.get('last_name', '')}".strip()
                            or chat.get("title")
                            or chat.get("username")
                            or "Opositor/a"
                        )
                        if cid not in existentes:
                            cursor.execute(
                                "INSERT OR IGNORE INTO suscriptores (chat_id, nombre) VALUES (?, ?)",
                                (cid, nombre),
                            )
                            existentes[cid] = nombre
                            try:
                                enviar_mensaje_telegram(bot_token, cid, MENSAJE_BIENVENIDA)
                            except Exception:
                                pass
                        elif nombre != "Opositor/a" and existentes.get(cid) in ("Administrador", "Opositor/a"):
                            cursor.execute(
                                "UPDATE suscriptores SET nombre = ? WHERE chat_id = ?",
                                (nombre, cid),
                            )
                            existentes[cid] = nombre

                        if texto_msg.startswith("/estadistica") or texto_msg.startswith("/informe"):
                            solicitudes_estadisticas.add(cid)

                    # B) Procesar respuestas a encuestas (poll_answer)
                    poll_ans = upd.get("poll_answer")
                    if poll_ans:
                        poll_id = str(poll_ans.get("poll_id", "")).strip()
                        user_obj = poll_ans.get("user", {})
                        user_id = str(user_obj.get("id", "")).strip()
                        option_ids = poll_ans.get("option_ids", [])

                        if user_id and user_id not in existentes:
                            nombre_u = (
                                f"{user_obj.get('first_name', '')} {user_obj.get('last_name', '')}".strip()
                                or user_obj.get("username")
                                or "Opositor/a"
                            )
                            cursor.execute(
                                "INSERT OR IGNORE INTO suscriptores (chat_id, nombre) VALUES (?, ?)",
                                (user_id, nombre_u),
                            )
                            existentes[user_id] = nombre_u

                        if poll_id and user_id and option_ids:
                            opcion_elegida = int(option_ids[0])
                            cursor.execute(
                                """
                                SELECT fragmento_id, tema, referencia, indice_correcta
                                FROM encuestas_enviadas
                                WHERE poll_id = ?
                                """,
                                (poll_id,),
                            )
                            enc = cursor.fetchone()
                            if enc:
                                frag_id, tema, referencia, indice_correcta = enc
                                acertada = 1 if opcion_elegida == indice_correcta else 0

                                # Verificar si ya se había procesado esta respuesta
                                cursor.execute(
                                    "SELECT 1 FROM respuestas_usuarios WHERE poll_id = ? AND chat_id = ?",
                                    (poll_id, user_id),
                                )
                                if not cursor.fetchone():
                                    cursor.execute(
                                        """
                                        INSERT INTO respuestas_usuarios
                                        (poll_id, chat_id, fragmento_id, tema, referencia, opcion_elegida, indice_correcta, acertada)
                                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                        """,
                                        (
                                            poll_id,
                                            user_id,
                                            frag_id,
                                            tema,
                                            referencia,
                                            opcion_elegida,
                                            indice_correcta,
                                            acertada,
                                        ),
                                    )
                                    # Actualizar contador de fallos_pendientes en el artículo
                                    if acertada == 0:
                                        cursor.execute(
                                            """
                                            UPDATE fragmentos
                                            SET fallos_pendientes = COALESCE(fallos_pendientes, 0) + 1
                                            WHERE id = ?
                                            """,
                                            (frag_id,),
                                        )
                                    else:
                                        cursor.execute(
                                            """
                                            UPDATE fragmentos
                                            SET fallos_pendientes = MAX(0, COALESCE(fallos_pendientes, 0) - 1)
                                            WHERE id = ?
                                            """,
                                            (frag_id,),
                                        )

                if max_update_id is not None:
                    cursor.execute(
                        "INSERT OR REPLACE INTO estado_bot (clave, valor) VALUES ('ultimo_update_id', ?)",
                        (str(max_update_id),),
                    )
        except Exception as e:
            print(f"[Aviso] No se pudieron consultar novedades en getUpdates: {e}")

        conn.commit()

        # Si algún usuario pidió /estadisticas por chat, enviárselas
        for cid_est in solicitudes_estadisticas:
            informe = construir_informe_semanal_usuario(
                cid_est, existentes.get(cid_est, "Opositor/a"), dias=7, db_path=db_path
            )
            if informe:
                enviar_mensaje_telegram(bot_token, cid_est, informe)
            else:
                enviar_mensaje_telegram(
                    bot_token,
                    cid_est,
                    "📊 Aún no hay respuestas registradas en tus últimos 7 días. ¡Responde a las próximas tandas y verás aquí tu análisis por temas!",
                )

        cursor.execute("SELECT chat_id FROM suscriptores ORDER BY fecha_alta ASC")
        return [fila[0] for fila in cursor.fetchall()]


def obtener_fragmentos_para_tanda(
    cantidad: int = NUM_PREGUNTAS_POR_TANDA,
    db_path: str = DB_PATH,
) -> list[tuple[int, str, str, int, bool]]:
    """
    Selecciona los fragmentos de la tanda combinando:
    - Hasta `MAX_REPASOS_POR_TANDA` artículos que tengan `fallos_pendientes > 0`
      (que no hayan salido en las últimas 10 encuestas, para dejar margen de asimilación).
    - El resto de preguntas priorizando los artículos con menor `veces_usado`.
    Devuelve tuplas: (id, referencia, contenido, veces_usado, es_repaso_fallo).
    """
    if not os.path.exists(db_path):
        raise FileNotFoundError(
            f"No existe la base de datos '{db_path}'. Ejecuta primero 1_procesar_pdf.py."
        )

    seleccionados: list[tuple[int, str, str, int, bool]] = []
    ids_usados: set[int] = set()

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        # Evitar repetir artículos que acaben de salir en la última tanda enviada
        cursor.execute(
            """
            SELECT DISTINCT fragmento_id
            FROM encuestas_enviadas
            ORDER BY fecha_envio DESC
            LIMIT 10
            """
        )
        recien_preguntados = {fila[0] for fila in cursor.fetchall() if fila[0] is not None}

        # 1. Buscar hasta MAX_REPASOS_POR_TANDA artículos con fallos pendientes
        cursor.execute(
            """
            SELECT id, referencia, contenido, veces_usado
            FROM fragmentos
            WHERE COALESCE(fallos_pendientes, 0) > 0
            ORDER BY fallos_pendientes DESC, veces_usado ASC, RANDOM()
            """
        )
        for fid, ref, cont, veces in cursor.fetchall():
            if len(seleccionados) >= min(MAX_REPASOS_POR_TANDA, cantidad):
                break
            if fid not in recien_preguntados:
                seleccionados.append((fid, ref, cont, veces, True))
                ids_usados.add(fid)

        # 2. Completar hasta `cantidad` con los artículos menos usados
        faltan = cantidad - len(seleccionados)
        cursor.execute(
            """
            SELECT id, referencia, contenido, veces_usado
            FROM fragmentos
            ORDER BY veces_usado ASC, RANDOM()
            """
        )
        for fid, ref, cont, veces in cursor.fetchall():
            if len(seleccionados) >= cantidad:
                break
            if fid not in ids_usados:
                seleccionados.append((fid, ref, cont, veces, False))
                ids_usados.add(fid)

    if not seleccionados:
        raise ValueError(f"La tabla 'fragmentos' en '{db_path}' está vacía.")

    return seleccionados


def incrementar_uso_fragmento(fragmento_id: int, db_path: str = DB_PATH) -> None:
    """Incrementa el contador veces_usado del fragmento utilizado."""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE fragmentos SET veces_usado = veces_usado + 1 WHERE id = ?",
            (fragmento_id,),
        )
        conn.commit()


def registrar_encuesta_enviada(
    poll_id: str,
    chat_id: str,
    fragmento_id: int,
    referencia: str,
    indice_correcta: int,
    db_path: str = DB_PATH,
) -> None:
    """Guarda los metadatos de cada Poll enviado para poder cruzar luego `poll_answer`."""
    if not poll_id:
        return
    tema = extraer_tema_de_referencia(referencia)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO encuestas_enviadas
            (poll_id, chat_id, fragmento_id, tema, referencia, indice_correcta)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (str(poll_id), str(chat_id), fragmento_id, tema, referencia, indice_correcta),
        )
        conn.commit()


def leer_ejemplos_clase(ruta: str = EJEMPLOS_PATH) -> str:
    """Lee ejemplos_clase.txt si existe para usarlo como referencia de estilo."""
    if os.path.exists(ruta):
        with open(ruta, "r", encoding="utf-8") as f:
            contenido = f.read().strip()
        if contenido:
            return contenido
    return ""


def obtener_errores_longitud(test: PreguntaTest) -> list[str]:
    """Comprueba que ningún campo supere los límites de Telegram (300/100/200)."""
    errores = []
    if len(test.pregunta) > TELEGRAM_MAX_PREGUNTA:
        errores.append(
            f"- 'pregunta' tiene {len(test.pregunta)} caracteres (máximo permitido: {TELEGRAM_MAX_PREGUNTA}, objetivo: <= 280)."
        )
    if len(test.opciones) != 4:
        errores.append(
            f"- 'opciones' tiene {len(test.opciones)} elementos (debe tener exactamente 4)."
        )
    for idx, opcion in enumerate(test.opciones):
        if len(opcion) > TELEGRAM_MAX_OPCION:
            errores.append(
                f"- 'opciones[{idx}]' tiene {len(opcion)} caracteres (máximo permitido: {TELEGRAM_MAX_OPCION}, objetivo: <= 95)."
            )
    if not (0 <= test.indice_correcta <= 3):
        errores.append(
            f"- 'indice_correcta' es {test.indice_correcta} (debe estar entre 0 y 3)."
        )
    if len(test.explicacion) > TELEGRAM_MAX_EXPLICACION:
        errores.append(
            f"- 'explicacion' tiene {len(test.explicacion)} caracteres (máximo permitido: {TELEGRAM_MAX_EXPLICACION}, objetivo: <= 190)."
        )
    return errores


def llamar_gemini(
    client: genai.Client,
    contents: str,
    config: types.GenerateContentConfig,
):
    """Llama a Gemini empezando por los modelos más rápidos y cambiando al instante ante 404/429/503/504."""
    ultimo_error = None
    for modelo in FALLBACK_MODELS:
        try:
            return client.models.generate_content(
                model=modelo,
                contents=contents,
                config=config,
            )
        except (errors.ClientError, errors.ServerError) as e:
            ultimo_error = e
            if getattr(e, "code", None) in (404, 429, 503, 504):
                continue
            raise
    raise ultimo_error


def generar_pregunta_con_gemini(
    client: genai.Client,
    referencia: str,
    contenido: str,
    ejemplos: str,
    modalidad: str = "directa",
    es_repaso: bool = False,
    max_reintentos_resumen: int = 3,
) -> PreguntaTest:
    """
    Genera una pregunta tipo test con Gemini según la modalidad ('directa', 'negativa' o 'caso_practico')
    y valida/resume longitudes si exceden límites.
    """
    prefijo_repaso = "🔄 [Repaso] " if es_repaso else ""
    if modalidad == "caso_practico":
        instruccion_modalidad = (
            "de SUPUESTO PRÁCTICO breve aplicado a un Ordenanza/Subalterno del Ayuntamiento de Córdoba "
            "(ej. en conserjería, atención a un ciudadano o dependencia municipal surge una duda o situación práctica "
            f"que se resuelve aplicando estrictamente lo dispuesto en este precepto). Empieza el enunciado con '{prefijo_repaso}[Caso práctico]'"
        )
    elif modalidad == "negativa":
        instruccion_modalidad = (
            "en negativo (pidiendo señalar la opción INCORRECTA o falsa respecto al precepto)"
            + (f", empezando el enunciado con '{prefijo_repaso}'" if es_repaso else "")
        )
    else:
        instruccion_modalidad = (
            "directa (preguntando por la afirmación correcta o literal según el precepto)"
            + (f", empezando el enunciado con '{prefijo_repaso}'" if es_repaso else "")
        )

    bloque_ejemplos = ""
    if ejemplos:
        bloque_ejemplos = (
            "\nEJEMPLOS DE REFERENCIA DE CLASE (imita su estilo, tono jurídico y nivel de dificultad):\n"
            f"\"\"\"\n{ejemplos}\n\"\"\"\n"
        )

    prompt = f"""Genera una pregunta oficial tipo test de oposición a partir del siguiente fragmento normativo:

REFERENCIA: {referencia}
TEXTO LITERAL:
\"\"\"
{contenido}
\"\"\"
{bloque_ejemplos}
MODALIDAD REQUERIDA EN ESTE TURNO: Redacta una pregunta {instruccion_modalidad}.
Recuerda ajustar las longitudes: pregunta <= 280 caracteres, cada una de las 4 opciones <= 95 caracteres, explicacion <= 190 caracteres citando expresamente '{referencia}'."""

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        response_mime_type="application/json",
        response_schema=PreguntaTest,
        temperature=0.4,
    )

    response = llamar_gemini(
        client=client,
        contents=prompt,
        config=config,
    )
    pregunta_test = PreguntaTest.model_validate_json(response.text)

    intento = 0
    errores = obtener_errores_longitud(pregunta_test)
    while errores and intento < max_reintentos_resumen:
        intento += 1
        print(
            f"[Aviso] Límites de Telegram superados (intento de resumen {intento}/{max_reintentos_resumen}):"
        )
        for err in errores:
            print(f"  {err}")

        prompt_resumen = f"""El siguiente JSON generado supera los límites máximos de caracteres de Telegram:
{json.dumps(pregunta_test.model_dump(), ensure_ascii=False, indent=2)}

Problemas detectados:
{chr(10).join(errores)}

Por favor, resume y acorta los textos afectados manteniendo el rigor jurídico, la referencia exacta a '{referencia}', la homogeneidad de las 4 opciones y el mismo indice_correcta, cumpliendo estrictamente:
- pregunta: máximo 280 caracteres (límite absoluto 300).
- cada opción de opciones: máximo 95 caracteres (límite absoluto 100).
- explicacion: máximo 190 caracteres (límite absoluto 200).

Texto original de referencia ({referencia}):
\"\"\"
{contenido}
\"\"\""""

        response = llamar_gemini(
            client=client,
            contents=prompt_resumen,
            config=config,
        )
        pregunta_test = PreguntaTest.model_validate_json(response.text)
        errores = obtener_errores_longitud(pregunta_test)

    return pregunta_test


def construir_cabecera_tanda(
    fragmentos: list[tuple[int, str, str, int, bool]]
) -> str:
    """Construye el mensaje de cabecera que anuncia la batería de 5 preguntas."""
    hora_utc = datetime.now(timezone.utc).hour
    if hora_utc < 11:
        franja = "☀️ TANDA DE MAÑANA (09:00 h)"
    elif hora_utc < 16:
        franja = "🕑 TANDA DE MEDIODÍA (14:00 h)"
    else:
        franja = "🌙 TANDA DE NOCHE (20:00 h)"

    etiquetas = [
        f"{ref} 🔄" if es_rep else ref for _, ref, _, _, es_rep in fragmentos
    ]
    referencias = ", ".join(etiquetas)
    num_repasos = sum(1 for *_, es_rep in fragmentos if es_rep)
    nota_repaso = (
        f"\n🔄 _Incluye {num_repasos} artículo(s) de refuerzo fallado(s) anteriormente._"
        if num_repasos > 0
        else ""
    )
    return (
        f"📌 *{franja} — {len(fragmentos)} PREGUNTAS*\n"
        f"📚 *Artículos en juego:* {referencias}\n"
        f"🏛️ _Incluye preguntas directas, en negativo y 1 supuesto práctico de Ordenanza._"
        f"{nota_repaso}"
    )


def debe_enviar_tip_hoy() -> bool:
    """
    Determina si corresponde enviar el TIP DE HOY (al final del día en la tanda de las 20:00 h,
    o cuando se fuerza mediante ENVIAR_TIP=1).
    """
    forzar = os.getenv("ENVIAR_TIP", "").strip().lower()
    if forzar in ("1", "true", "si", "sí", "always"):
        return True
    if forzar in ("0", "false", "no"):
        return False
    hora_utc = datetime.now(timezone.utc).hour
    return hora_utc >= 17


def debe_enviar_informe_semanal() -> bool:
    """
    Determina si corresponde enviar el Informe Semanal de estudio (domingos en la tanda de noche
    de las 20:00 h, o si se fuerza con ENVIAR_INFORME_SEMANAL=1).
    """
    forzar = os.getenv("ENVIAR_INFORME_SEMANAL", "").strip().lower()
    if forzar in ("1", "true", "si", "sí", "always"):
        return True
    if forzar in ("0", "false", "no"):
        return False
    ahora = datetime.now(timezone.utc)
    # Domingo (weekday == 6) en la tanda de cierre de noche (hora_utc >= 17)
    return ahora.weekday() == 6 and ahora.hour >= 17


def generar_y_guardar_tip_de_hoy(
    client: genai.Client,
    db_path: str = DB_PATH,
) -> str:
    """
    Selecciona un fragmento sobre el que aún no se haya generado un TIP (o el menos usado para tips),
    consulta los tips anteriores para no repetir nunca la misma idea, y guarda el nuevo TIP en SQLite.
    """
    inicializar_tablas_auxiliares(db_path)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT f.id, f.referencia, f.contenido, COUNT(t.id) AS num_tips
            FROM fragmentos f
            LEFT JOIN tips_enviados t ON f.id = t.fragmento_id
            GROUP BY f.id
            ORDER BY num_tips ASC, RANDOM()
            LIMIT 1
            """
        )
        fila = cursor.fetchone()
        if not fila:
            raise ValueError("No hay fragmentos en la base de datos para generar el TIP DE HOY.")
        frag_id, referencia, contenido, _ = fila

        cursor.execute(
            "SELECT referencia, tip FROM tips_enviados ORDER BY id DESC LIMIT 15"
        )
        tips_recientes = cursor.fetchall()

    resumen_previos = ""
    if tips_recientes:
        lista_previos = "\n".join(f"- [{ref}]: {txt[:120]}..." for ref, txt in tips_recientes)
        resumen_previos = (
            "\nTIPS ENVIADOS EN DÍAS ANTERIORES (NO repitas estas ideas ni estos trucos):\n"
            f"{lista_previos}\n"
        )

    prompt_tip = f"""Redacta una píldora de estudio memorable y directa para opositores de Ordenanza del Ayuntamiento de Córdoba a partir de este precepto del temario:

REFERENCIA: {referencia}
TEXTO LITERAL:
\"\"\"
{contenido}
\"\"\"
{resumen_previos}
INSTRUCCIONES DE FORMATO:
1. Empieza OBLIGATORIAMENTE con esta primera línea exacta:
💡 *TIP DE HOY*
2. En la segunda línea indica en negrita la referencia: *{referencia}*
3. En 3 a 5 líneas claras y muy visuales (usando viñetas cortas), destaca la IDEA FUNDAMENTAL del precepto, la "trampa típica de examen" que suelen poner los tribunales (plazos, mayorías, órgano competente o excepción) y una regla mnemotécnica o clave rápida para no fallarla nunca.
4. No superes los 850 caracteres en total y usa formato Markdown compatible con Telegram (*negrita*, _cursiva_)."""

    config = types.GenerateContentConfig(
        temperature=0.5,
    )
    response = llamar_gemini(client=client, contents=prompt_tip, config=config)
    texto_tip = response.text.strip()
    if not texto_tip.startswith("💡"):
        texto_tip = f"💡 *TIP DE HOY*\n\n{texto_tip}"

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO tips_enviados (fragmento_id, referencia, tip) VALUES (?, ?, ?)",
            (frag_id, referencia, texto_tip),
        )
        conn.commit()

    return texto_tip


def enviar_poll_telegram(
    bot_token: str,
    channel_id: str,
    test: PreguntaTest,
) -> dict:
    """Envía la pregunta tipo test a un chat o canal de Telegram usando sendPoll en modo quiz."""
    url = f"https://api.telegram.org/bot{bot_token}/sendPoll"
    es_canal_o_grupo = str(channel_id).startswith("-") or str(channel_id).startswith("@")

    payload = {
        "chat_id": channel_id,
        "question": test.pregunta,
        "options": test.opciones,
        "type": "quiz",
        "correct_option_id": test.indice_correcta,
        "explanation": test.explicacion,
        "is_anonymous": es_canal_o_grupo,
    }

    resp = requests.post(url, json=payload, timeout=20)
    datos = resp.json()
    if not resp.ok or not datos.get("ok"):
        raise RuntimeError(f"Error al enviar Poll a Telegram ({channel_id}): {datos}")
    return datos


def imprimir_resultado_consola(
    num_orden: int,
    total_tanda: int,
    modalidad: str,
    es_repaso: bool,
    frag_id: int,
    referencia: str,
    veces_usado_previo: int,
    test: PreguntaTest,
) -> None:
    """Imprime la pregunta generada formateada por consola para su revisión."""
    letras = ["A", "B", "C", "D"]
    etiq_repaso = " | REPASO DE FALLO 🔄" if es_repaso else ""
    print("=" * 72)
    print(f"  PREGUNTA {num_orden}/{total_tanda} [{modalidad.upper()}{etiq_repaso}]")
    print("=" * 72)
    print(
        f"Fragmento seleccionado : ID {frag_id} | {referencia} (usos previos: {veces_usado_previo} -> ahora: {veces_usado_previo + 1})"
    )
    print("-" * 72)
    print(f"\nPREGUNTA ({len(test.pregunta)}/{TELEGRAM_MAX_PREGUNTA} caracteres):")
    print(f"  {test.pregunta}\n")
    print("OPCIONES:")
    for idx, opcion in enumerate(test.opciones):
        marcador = "✅" if idx == test.indice_correcta else "  "
        letra = letras[idx] if idx < len(letras) else str(idx)
        print(
            f"  {marcador} {letra}) {opcion}  [{len(opcion)}/{TELEGRAM_MAX_OPCION} chars]"
        )

    letra_correcta = letras[test.indice_correcta]
    print(f"\nRESPUESTA CORRECTA : Opción {letra_correcta} (índice {test.indice_correcta})")
    print(
        f"EXPLICACIÓN ({len(test.explicacion)}/{TELEGRAM_MAX_EXPLICACION} caracteres):"
    )
    print(f"  {test.explicacion}")
    print("=" * 72)


def main() -> None:
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    channel_id = os.getenv("TELEGRAM_CHANNEL_ID")

    if not api_key or api_key == "tu_api_key_de_gemini_aqui":
        print(
            "Error: No se ha configurado GEMINI_API_KEY en .env.",
            file=sys.stderr,
        )
        sys.exit(1)

    inicializar_tablas_auxiliares(DB_PATH)
    clave_tanda = obtener_clave_tanda_actual()

    if os.getenv("GITHUB_EVENT_NAME") == "schedule" and tanda_ya_enviada(clave_tanda, DB_PATH):
        print(f"ℹ️ La tanda '{clave_tanda}' ya fue enviada hoy. Saliendo sin duplicar.")
        return

    destinatarios = []
    if bot_token and bot_token != "tu_bot_token_de_telegram_aqui":
        destinatarios = sincronizar_suscriptores(bot_token, channel_id, DB_PATH)
        print(f"Suscriptores activos detectados: {len(destinatarios)}")

    fragmentos = obtener_fragmentos_para_tanda(NUM_PREGUNTAS_POR_TANDA, DB_PATH)
    ejemplos = leer_ejemplos_clase()
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            timeout=15000,
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )

    total = len(fragmentos)
    cabecera = construir_cabecera_tanda(fragmentos)
    print(f"\nGenerando las {total} preguntas antes de enviar a Telegram...\n")

    # 1. Generar las 5 preguntas en memoria antes de enviarlas
    preguntas_generadas: list[tuple[int, int, str, int, str, bool, PreguntaTest]] = []
    for idx, (frag_id, referencia, contenido, veces_usado, es_repaso) in enumerate(
        fragmentos, start=1
    ):
        if idx == total:
            modalidad = "caso_practico"
        elif idx % 2 == 0:
            modalidad = "negativa"
        else:
            modalidad = "directa"

        pregunta_test = generar_pregunta_con_gemini(
            client=client,
            referencia=referencia,
            contenido=contenido,
            ejemplos=ejemplos,
            modalidad=modalidad,
            es_repaso=es_repaso,
        )
        imprimir_resultado_consola(
            idx, total, modalidad, es_repaso, frag_id, referencia, veces_usado, pregunta_test
        )
        preguntas_generadas.append(
            (idx, frag_id, referencia, veces_usado, modalidad, es_repaso, pregunta_test)
        )

    # 2. Enviar cabecera + las 5 encuestas seguidas y registrar cada poll_id
    omitir_cabecera = os.getenv("OMITIR_CABECERA", "").strip() == "1"
    if destinatarios and not omitir_cabecera:
        for dest_id in destinatarios:
            try:
                enviar_mensaje_telegram(bot_token, dest_id, cabecera)
            except Exception as e:
                print(f"[Aviso] Error enviando cabecera a {dest_id}: {e}")

    for idx, frag_id, referencia, veces_usado, modalidad, es_repaso, pregunta_test in preguntas_generadas:
        if destinatarios:
            enviados_ok = 0
            for dest_id in destinatarios:
                try:
                    res_poll = enviar_poll_telegram(bot_token, dest_id, pregunta_test)
                    poll_id = res_poll.get("result", {}).get("poll", {}).get("id")
                    registrar_encuesta_enviada(
                        poll_id=poll_id,
                        chat_id=dest_id,
                        fragmento_id=frag_id,
                        referencia=referencia,
                        indice_correcta=pregunta_test.indice_correcta,
                        db_path=DB_PATH,
                    )
                    enviados_ok += 1
                except Exception as e:
                    print(f"[Aviso] No se pudo enviar Poll a {dest_id}: {e}")
            print(f"✅ Pregunta {idx}/{total} enviada a {enviados_ok}/{len(destinatarios)} suscriptores.")
            if idx < total:
                time.sleep(1.0)
        incrementar_uso_fragmento(frag_id, DB_PATH)

    registrar_tanda_enviada(clave_tanda, DB_PATH)

    # 3. Al final del día (tanda de las 20:00 h o si se fuerza ENVIAR_TIP=1), enviar el TIP DE HOY
    if debe_enviar_tip_hoy():
        print("\nGenerando 💡 TIP DE HOY (cierre del día)...")
        texto_tip = generar_y_guardar_tip_de_hoy(client=client, db_path=DB_PATH)
        print("\n" + "=" * 72)
        print(texto_tip)
        print("=" * 72 + "\n")

        if destinatarios:
            time.sleep(1.5)
            for dest_id in destinatarios:
                try:
                    enviar_mensaje_telegram(bot_token, dest_id, texto_tip)
                except Exception as e:
                    print(f"[Aviso] Error enviando TIP DE HOY a {dest_id}: {e}")
            print("✅ 💡 TIP DE HOY enviado a todos los suscriptores.")

    # 4. Los domingos por la noche (o si ENVIAR_INFORME_SEMANAL=1), enviar el Informe Semanal a cada usuario
    if debe_enviar_informe_semanal() and destinatarios:
        print("\nGenerando y enviando 📊 INFORMES SEMANALES personalizados...")
        with sqlite3.connect(DB_PATH) as conn:
            nombres_map = dict(conn.execute("SELECT chat_id, nombre FROM suscriptores").fetchall())

        for dest_id in destinatarios:
            informe = construir_informe_semanal_usuario(
                dest_id,
                nombres_map.get(dest_id, "Opositor/a"),
                dias=7,
                db_path=DB_PATH,
            )
            if informe:
                try:
                    enviar_mensaje_telegram(bot_token, dest_id, informe)
                    print(f"  ✅ Informe semanal enviado a {dest_id} ({nombres_map.get(dest_id)})")
                except Exception as e:
                    print(f"  [Aviso] Error enviando informe semanal a {dest_id}: {e}")


if __name__ == "__main__":
    main()
