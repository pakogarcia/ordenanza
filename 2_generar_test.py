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
    "✅ Tu suscripción está activa. Recibirás automáticamente una batería de *5 preguntas tipo test* "
    "en las tres franjas diarias (*09:00, 14:00 y 20:00 h*) y, al cerrar la última tanda de la noche, el *💡 TIP DE HOY*.\n\n"
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
    """Asegura que existan las tablas `suscriptores` y `tips_enviados` en SQLite."""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
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
        conn.commit()


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
    """Registra la tanda actual como enviada para evitar duplicados en reintentos de cron."""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO tandas_enviadas (clave_tanda) VALUES (?)",
            (clave_tanda,),
        )
        conn.commit()


def sincronizar_suscriptores(
    bot_token: str,
    channel_id_principal: str | None,
    db_path: str = DB_PATH,
) -> list[str]:
    """
    Registra en la tabla `suscriptores` de SQLite a todos los usuarios que hayan pulsado
    /start o escrito al bot, enviándoles una leyenda de bienvenida la primera vez.
    """
    inicializar_tablas_auxiliares(db_path)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        if channel_id_principal and channel_id_principal != "@tu_canal_o_id_numerico_aqui":
            cursor.execute(
                "INSERT OR IGNORE INTO suscriptores (chat_id, nombre) VALUES (?, ?)",
                (str(channel_id_principal).strip(), "Administrador"),
            )

        cursor.execute("SELECT chat_id FROM suscriptores")
        existentes = {fila[0] for fila in cursor.fetchall()}

        try:
            url_updates = f"https://api.telegram.org/bot{bot_token}/getUpdates"
            resp = requests.get(url_updates, timeout=15)
            datos = resp.json()
            if resp.ok and datos.get("ok"):
                for upd in datos.get("result", []):
                    msg = upd.get("message") or upd.get("my_chat_member") or {}
                    chat = msg.get("chat", {})
                    cid = str(chat.get("id", "")).strip()
                    if not cid:
                        continue
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
                        existentes.add(cid)
                        try:
                            requests.post(
                                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                                json={
                                    "chat_id": cid,
                                    "text": MENSAJE_BIENVENIDA,
                                    "parse_mode": "Markdown",
                                },
                                timeout=10,
                            )
                        except Exception:
                            pass
        except Exception as e:
            print(f"[Aviso] No se pudieron consultar nuevos suscriptores en getUpdates: {e}")

        conn.commit()
        cursor.execute("SELECT chat_id FROM suscriptores ORDER BY fecha_alta ASC")
        return [fila[0] for fila in cursor.fetchall()]


def obtener_fragmentos_menos_usados(
    cantidad: int = NUM_PREGUNTAS_POR_TANDA,
    db_path: str = DB_PATH,
) -> list[tuple[int, str, str, int]]:
    """Selecciona `cantidad` fragmentos distintos priorizando los que tienen menor valor en veces_usado."""
    if not os.path.exists(db_path):
        raise FileNotFoundError(
            f"No existe la base de datos '{db_path}'. Ejecuta primero 1_procesar_pdf.py."
        )

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, referencia, contenido, veces_usado
            FROM fragmentos
            ORDER BY veces_usado ASC, RANDOM()
            LIMIT ?
            """,
            (cantidad,),
        )
        filas = cursor.fetchall()

    if not filas:
        raise ValueError(f"La tabla 'fragmentos' en '{db_path}' está vacía.")

    return filas


def incrementar_uso_fragmento(fragmento_id: int, db_path: str = DB_PATH) -> None:
    """Incrementa el contador veces_usado del fragmento utilizado."""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE fragmentos SET veces_usado = veces_usado + 1 WHERE id = ?",
            (fragmento_id,),
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
    max_reintentos_resumen: int = 3,
) -> PreguntaTest:
    """
    Genera una pregunta tipo test con Gemini según la modalidad ('directa', 'negativa' o 'caso_practico')
    y valida/resume longitudes si exceden límites.
    """
    if modalidad == "caso_practico":
        instruccion_modalidad = (
            "de SUPUESTO PRÁCTICO breve aplicado a un Ordenanza/Subalterno del Ayuntamiento de Córdoba "
            "(ej. en conserjería, atención a un ciudadano o dependencia municipal surge una duda o situación práctica "
            "que se resuelve aplicando estrictamente lo dispuesto en este precepto). Empieza el enunciado con '[Caso práctico]'"
        )
    elif modalidad == "negativa":
        instruccion_modalidad = (
            "en negativo (pidiendo señalar la opción INCORRECTA o falsa respecto al precepto)"
        )
    else:
        instruccion_modalidad = (
            "directa (preguntando por la afirmación correcta o literal según el precepto)"
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


def construir_cabecera_tanda(fragmentos: list[tuple[int, str, str, int]]) -> str:
    """Construye el mensaje de cabecera que anuncia la batería de 5 preguntas."""
    hora_utc = datetime.now(timezone.utc).hour
    if hora_utc < 11:
        franja = "☀️ TANDA DE MAÑANA (09:00 h)"
    elif hora_utc < 16:
        franja = "🕑 TANDA DE MEDIODÍA (14:00 h)"
    else:
        franja = "🌙 TANDA DE NOCHE (20:00 h)"

    referencias = ", ".join(f[1] for f in fragmentos)
    return (
        f"📌 *{franja} — {len(fragmentos)} PREGUNTAS*\n"
        f"📚 *Artículos en juego:* {referencias}\n"
        f"🏛️ _Incluye preguntas directas, en negativo y 1 supuesto práctico de Ordenanza._"
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
    frag_id: int,
    referencia: str,
    veces_usado_previo: int,
    test: PreguntaTest,
) -> None:
    """Imprime la pregunta generada formateada por consola para su revisión."""
    letras = ["A", "B", "C", "D"]
    print("=" * 72)
    print(f"  PREGUNTA {num_orden}/{total_tanda} [{modalidad.upper()}]")
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

    # Si es una ejecución programada por cron (GITHUB_EVENT_NAME == 'schedule'),
    # verificar si esta franja ya fue enviada en un disparo previo para no duplicar.
    if os.getenv("GITHUB_EVENT_NAME") == "schedule" and tanda_ya_enviada(clave_tanda, DB_PATH):
        print(f"ℹ️ La tanda '{clave_tanda}' ya fue enviada hoy. Saliendo sin duplicar.")
        return

    destinatarios = []
    if bot_token and bot_token != "tu_bot_token_de_telegram_aqui":
        destinatarios = sincronizar_suscriptores(bot_token, channel_id, DB_PATH)
        print(f"Suscriptores activos detectados: {len(destinatarios)}")

    fragmentos = obtener_fragmentos_menos_usados(NUM_PREGUNTAS_POR_TANDA)
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

    # 1. Primero generamos las 5 preguntas en memoria (~5 segundos en total)
    #    para que la cabecera y las 5 preguntas se envíen todas juntas sin espera.
    preguntas_generadas: list[tuple[int, int, str, int, str, PreguntaTest]] = []
    for idx, (frag_id, referencia, contenido, veces_usado) in enumerate(fragmentos, start=1):
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
        )
        imprimir_resultado_consola(idx, total, modalidad, frag_id, referencia, veces_usado, pregunta_test)
        preguntas_generadas.append((idx, frag_id, referencia, veces_usado, modalidad, pregunta_test))

    # 2. Una vez listas las 5 preguntas, enviamos cabecera + las 5 encuestas seguidas
    omitir_cabecera = os.getenv("OMITIR_CABECERA", "").strip() == "1"
    if destinatarios and not omitir_cabecera:
        for dest_id in destinatarios:
            try:
                enviar_mensaje_telegram(bot_token, dest_id, cabecera)
            except Exception as e:
                print(f"[Aviso] Error enviando cabecera a {dest_id}: {e}")

    for idx, frag_id, referencia, veces_usado, modalidad, pregunta_test in preguntas_generadas:
        if destinatarios:
            enviados_ok = 0
            for dest_id in destinatarios:
                try:
                    enviar_poll_telegram(bot_token, dest_id, pregunta_test)
                    enviados_ok += 1
                except Exception as e:
                    print(f"[Aviso] No se pudo enviar Poll a {dest_id}: {e}")
            print(f"✅ Pregunta {idx}/{total} enviada a {enviados_ok}/{len(destinatarios)} suscriptores.")
            if idx < total:
                time.sleep(1.0)
        incrementar_uso_fragmento(frag_id)

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


if __name__ == "__main__":
    main()
