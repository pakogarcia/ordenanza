import os
import re
import sqlite3
import pymupdf  # fitz


PDF_CANDIDATES = ["Tema1-Constitucion.pdf", "temario.pdf"]
DB_PATH = "temario.db"
CHUNK_SIZE = 1500
CHUNK_OVERLAP = 200


def obtener_ruta_pdf() -> str:
    """Devuelve la ruta del PDF del temario disponible en la raíz del proyecto."""
    for ruta in PDF_CANDIDATES:
        if os.path.exists(ruta):
            return ruta
    raise FileNotFoundError(
        f"No se encontró ninguno de los archivos esperados: {', '.join(PDF_CANDIDATES)}"
    )


def limpiar_texto_paginas(doc: pymupdf.Document) -> str:
    """Extrae el texto del PDF limpiando encabezados, pies de página y saltos innecesarios."""
    paginas_lineas = []
    posibles_encabezados_pies = {}

    for page in doc:
        lineas = [line.strip() for line in page.get_text("text").splitlines() if line.strip()]
        paginas_lineas.append(lineas)
        if lineas:
            for candidata in (lineas[0], lineas[-1]):
                posibles_encabezados_pies[candidata] = posibles_encabezados_pies.get(candidata, 0) + 1

    # Encabezados o pies que se repiten en al menos 3 páginas
    umbral_repeticion = max(3, len(doc) // 3)
    encabezados_pies_repetidos = {
        linea
        for linea, cuenta in posibles_encabezados_pies.items()
        if cuenta >= umbral_repeticion and not re.match(r"^(?:Art[íi]culo|Art\.)\s+\d+", linea, re.IGNORECASE)
    }

    patron_paginacion = re.compile(
        r"^(?:p[áa]gina\s*\d+(?:\s*de\s*\d+)?|\d+\s*/\s*\d+|-\s*\d+\s*-|\d+)$",
        re.IGNORECASE,
    )
    # Títulos/Capítulos/Secciones estructurales para que no queden pegados al final del artículo previo
    patron_estructura = re.compile(
        r"^(?:T[ÍI]TULO\s+[IVXLCDM0-9]+.*|T[ÍI]TULO\s+PRELIMINAR.*|"
        r"CAP[ÍI]TULO\s+(?:PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|[IVXLCDM0-9]+).*|"
        r"Secci[óo]n\s+\d+\.[ªa].*|"
        r"De la Organizaci[óo]n Territorial del Estado)$",
        re.IGNORECASE,
    )

    lineas_limpias = []
    for lineas in paginas_lineas:
        for idx, linea in enumerate(lineas):
            if (idx == 0 or idx == len(lineas) - 1) and (
                linea in encabezados_pies_repetidos or patron_paginacion.match(linea)
            ):
                continue
            if patron_estructura.match(linea):
                continue
            lineas_limpias.append(linea)

    return "\n".join(lineas_limpias)


def normalizar_espacios_y_saltos(texto: str) -> str:
    """Limpia saltos de línea de maquetación manteniendo saltos entre apartados lógicos."""
    lineas = [re.sub(r"\s+", " ", l).strip() for l in texto.splitlines() if l.strip()]
    if not lineas:
        return ""

    patron_nuevo_apartado = re.compile(
        r"^(?:\d+\.(?:\s|$)|\d+\.[ªaºo]\s|[a-zñ]\)\s|[a-zñ]\.\s|[•\-]\s)"
    )

    resultado = [lineas[0]]
    for linea in lineas[1:]:
        if patron_nuevo_apartado.match(linea):
            resultado.append("\n" + linea)
        elif resultado[-1] in ("•", "-") or re.match(r"^\d+\.$", resultado[-1]):
            resultado[-1] = f"{resultado[-1]} {linea}"
        else:
            resultado[-1] = f"{resultado[-1]} {linea}"

    return "".join(resultado).strip()


def dividir_en_fragmentos(texto: str) -> list[tuple[str, str]]:
    """
    Divide el texto por artículos (ej. 'Artículo 1.', 'Art. 1', 'Artículo 14').
    Si no detecta artículos, lo divide en fragmentos lógicos de ~1.500 caracteres con solapamiento.
    """
    patron_articulo = re.compile(
        r"(?m)^((?:Art[íi]culo|Art\.)\s+\d+(?:\s*(?:bis|ter|quater))?)\.?\s*$",
        re.IGNORECASE,
    )
    coincidencias = list(patron_articulo.finditer(texto))

    # Si no se detectan en líneas propias, buscar también en inicio de línea con texto seguido
    if not coincidencias:
        patron_articulo_inline = re.compile(
            r"(?m)^((?:Art[íi]culo|Art\.)\s+\d+(?:\s*(?:bis|ter|quater))?)\.?\s+",
            re.IGNORECASE,
        )
        coincidencias = list(patron_articulo_inline.finditer(texto))

    fragmentos: list[tuple[str, str]] = []

    if coincidencias:
        for i, match in enumerate(coincidencias):
            ref_bruta = match.group(1).strip()
            # Normalizar referencia a formato 'Artículo X'
            num_match = re.search(r"\d+(?:\s*(?:bis|ter|quater))?", ref_bruta, re.IGNORECASE)
            referencia = f"Artículo {num_match.group(0)}" if num_match else ref_bruta

            inicio_contenido = match.end()
            fin_contenido = coincidencias[i + 1].start() if i + 1 < len(coincidencias) else len(texto)
            contenido_bruto = texto[inicio_contenido:fin_contenido]
            contenido = normalizar_espacios_y_saltos(contenido_bruto)

            if contenido:
                fragmentos.append((referencia, contenido))
    else:
        texto_limpio = normalizar_espacios_y_saltos(texto)
        inicio = 0
        num_frag = 1
        longitud = len(texto_limpio)

        while inicio < longitud:
            fin = min(inicio + CHUNK_SIZE, longitud)
            if fin < longitud:
                # Intentar cortar en el último punto o salto de línea dentro del rango
                ultimo_corte = max(
                    texto_limpio.rfind(". ", inicio + CHUNK_SIZE // 2, fin),
                    texto_limpio.rfind("\n", inicio + CHUNK_SIZE // 2, fin),
                )
                if ultimo_corte != -1:
                    fin = ultimo_corte + 1

            fragmento = texto_limpio[inicio:fin].strip()
            if fragmento:
                fragmentos.append((f"Fragmento {num_frag}", fragmento))
                num_frag += 1

            if fin >= longitud:
                break
            inicio = max(inicio + 1, fin - CHUNK_OVERLAP)

    return fragmentos


def guardar_en_sqlite(fragmentos: list[tuple[str, str]], db_path: str = DB_PATH) -> None:
    """Crea la tabla fragmentos en SQLite y guarda los fragmentos procesados."""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS fragmentos (
                id INTEGER PRIMARY KEY,
                referencia TEXT,
                contenido TEXT,
                veces_usado INTEGER DEFAULT 0
            )
            """
        )
        cursor.execute("DELETE FROM fragmentos")
        cursor.executemany(
            "INSERT INTO fragmentos (referencia, contenido, veces_usado) VALUES (?, ?, 0)",
            fragmentos,
        )
        conn.commit()


def main() -> None:
    ruta_pdf = obtener_ruta_pdf()
    print(f"Procesando archivo PDF: {ruta_pdf}")

    with pymupdf.open(ruta_pdf) as doc:
        texto_limpio = limpiar_texto_paginas(doc)

    fragmentos = dividir_en_fragmentos(texto_limpio)
    guardar_en_sqlite(fragmentos, DB_PATH)

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM fragmentos")
        total = cursor.fetchone()[0]

        cursor.execute("SELECT id, referencia, contenido, veces_usado FROM fragmentos ORDER BY id LIMIT 3")
        primeros_tres = cursor.fetchall()

    print(f"\nTotal de fragmentos guardados en '{DB_PATH}': {total}\n")
    print("=== EJEMPLO DE LOS 3 PRIMEROS FRAGMENTOS ===")
    for fila_id, referencia, contenido, veces_usado in primeros_tres:
        print(f"\n[ID: {fila_id}] Referencia: {referencia} | Veces usado: {veces_usado}")
        print(f"Contenido:\n{contenido}")
        print("-" * 60)


if __name__ == "__main__":
    main()
