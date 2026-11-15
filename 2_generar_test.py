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
MODEL_NAME = "gemini-2.5-flash"
FALLBACK_MODELS = [
    "gemini-2.5-flash",
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
]

# Límites máximos permitidos por Telegram Poll (modo quiz)
TELEGRAM_MAX_PREGUNTA = 300
TELEGRAM_MAX_OPCION = 100
TELEGRAM_MAX_EXPLICACION = 200


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


SYSTEM_INSTRUCTION = """Eres un vocal experto de un Tribunal Calificador de oposiciones de la Administración General del Estado (AGE).
Tu misión es redactar preguntas tipo test oficiales de alta calidad técnica siguiendo estas reglas estrictas:

1. LITERALIDAD NORMATIVA: Básate única y exclusivamente en el texto literal del artículo o fragmento proporcionado. No utilices conocimientos externos ni supongas preceptos no incluidos en el fragmento.
2. ESTILO Y ALTERNANCIA: Redacta con rigor jurídico propio de exámenes oficiales del INAP. Alterna entre preguntas directas (ej. «Según el artículo X de la Constitución Española...») y preguntas en negativo (ej. «Conforme al artículo X de la Constitución Española, señale la afirmación INCORRECTA:»).
3. DISTRACTORES PLAUSIBLES: Diseña opciones incorrectas verosímiles empleando trampas clásicas de examen oficial:
   - Alterar plazos, edades o mayorías cercanas (ej. mayoría absoluta por mayoría simple, tres quintos por dos tercios).
   - Intercambiar órganos o sujetos (ej. Gobierno, Cortes Generales, Congreso, Senado, Rey, Tribunal Constitucional, ley orgánica por ley ordinaria).
   - Invertir excepciones, condiciones o matices verbales («podrá» por «deberá», «en todo caso» por «en ningún caso», «salvo» por «incluso»).
4. HOMOGENEIDAD FORMAL: Las 4 opciones deben mantener una longitud, estructura sintáctica y tono jurídico muy similares entre sí para que ninguna destaque visualmente. No incluyas prefijos como «a)», «b)», «1.» al inicio de cada opción.
5. LÍMITES ESTRICTOS DE LONGITUD:
   - pregunta: máximo 280 caracteres.
   - opciones: exactamente 4 textos de máximo 95 caracteres cada uno.
   - indice_correcta: entero entre 0 y 3.
   - explicacion: máximo 190 caracteres, citando siempre el artículo exacto de referencia.
"""


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
    """Llama a Gemini con respaldo automático ante modelos retirados (404) o picos de demanda (503)."""
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
            if getattr(e, "code", None) in (404, 429, 503):
                continue
            raise
    raise ultimo_error


def generar_pregunta_con_gemini(
    client: genai.Client,
    referencia: str,
    contenido: str,
    ejemplos: str,
    es_negativa: bool | None = None,
    max_reintentos_resumen: int = 3,
) -> PreguntaTest:
    """Genera una pregunta tipo test con Gemini y valida/resume longitudes si exceden límites."""
    if es_negativa is None:
        es_negativa = random.choice([False, True])

    modalidad_sugerida = (
        "en negativo (pidiendo señalar la opción INCORRECTA o falsa respecto al precepto)"
        if es_negativa
        else "directa (preguntando por la afirmación correcta o literal según el precepto)"
    )

    bloque_ejemplos = ""
    if ejemplos:
        bloque_ejemplos = (
            "\nEJEMPLOS DE REFERENCIA DE CLASE (imita su estilo, tono jurídico y nivel de dificultad):\n"
            f"\"\"\"\n{ejemplos}\n\"\"\"\n"
        )

    prompt = f"""Genera una pregunta oficial tipo test de oposición (AGE) a partir del siguiente fragmento normativo:

REFERENCIA: {referencia}
TEXTO LITERAL:
\"\"\"
{contenido}
\"\"\"
{bloque_ejemplos}
MODALIDAD REQUERIDA EN ESTE TURNO: Redacta una pregunta {modalidad_sugerida}.
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

    # Validar límites de Telegram (300/100/200); si se superan, pedir a Gemini que lo resuma
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


def enviar_poll_telegram(
    bot_token: str,
    channel_id: str,
    test: PreguntaTest,
) -> dict:
    """Envía la pregunta tipo test a Telegram usando el método sendPoll en modo quiz."""
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
        raise RuntimeError(f"Error al enviar Poll a Telegram: {datos}")
    return datos


def imprimir_resultado_consola(
    num_orden: int,
    total_tanda: int,
    frag_id: int,
    referencia: str,
    veces_usado_previo: int,
    test: PreguntaTest,
) -> None:
    """Imprime la pregunta generada formateada por consola para su revisión."""
    letras = ["A", "B", "C", "D"]
    print("=" * 72)
    print(f"  PREGUNTA {num_orden}/{total_tanda} TIPO TEST (ESTILO OFICIAL AGE)")
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

    fragmentos = obtener_fragmentos_menos_usados(NUM_PREGUNTAS_POR_TANDA)
    ejemplos = leer_ejemplos_clase()
    client = genai.Client(api_key=api_key)

    total = len(fragmentos)
    print(f"Generando batería de {total} preguntas tipo test...\n")

    for idx, (frag_id, referencia, contenido, veces_usado) in enumerate(fragmentos, start=1):
        # Alternar preguntas directas y en negativo dentro de la batería de 5
        es_negativa = (idx % 2 == 0)
        pregunta_test = generar_pregunta_con_gemini(
            client=client,
            referencia=referencia,
            contenido=contenido,
            ejemplos=ejemplos,
            es_negativa=es_negativa,
        )

        imprimir_resultado_consola(idx, total, frag_id, referencia, veces_usado, pregunta_test)

        if bot_token and channel_id and bot_token != "tu_bot_token_de_telegram_aqui":
            resultado_tg = enviar_poll_telegram(bot_token, channel_id, pregunta_test)
            poll_msg_id = resultado_tg.get("result", {}).get("message_id")
            print(f"✅ Pregunta {idx}/{total} enviada a Telegram (message_id: {poll_msg_id}).\n")
            if idx < total:
                time.sleep(1.5)
        else:
            print("ℹ️ Credenciales de Telegram no configuradas; solo se mostró por consola.\n")

        incrementar_uso_fragmento(frag_id)


if __name__ == "__main__":
    main()
