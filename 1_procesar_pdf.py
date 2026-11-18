import glob
import os
import re
import sqlite3
import pymupdf  # fitz


DB_PATH = "temario.db"
INVENTARIO_PATH = "inventario_temario.txt"
CHUNK_SIZE = 1500
CHUNK_OVERLAP = 200


def obtener_archivos_pdf() -> list[str]:
    """Devuelve todos los archivos PDF presentes en la raíz del proyecto ordenados por nombre."""
    archivos = sorted(glob.glob("*.pdf"))
    if not archivos:
        raise FileNotFoundError(
            "No se encontró ningún archivo .pdf en la carpeta del proyecto."
        )
    return archivos


def nombre_tema_desde_archivo(ruta_pdf: str) -> str:
    """Genera un nombre legible del tema/ley a partir del nombre del archivo PDF."""
    base = os.path.splitext(os.path.basename(ruta_pdf))[0].strip()
    base_limpio = re.sub(r"[_]+", " ", base)
    base_limpio = re.sub(r"\s*-\s*", " - ", base_limpio)
    return base_limpio


def limpiar_texto_paginas(doc: pymupdf.Document) -> str:
    """Extrae el texto del PDF ordenado visualmente (sort=True) y limpia encabezados y pies."""
    paginas_lineas = []
    posibles_encabezados_pies = {}

    for page in doc:
        # sort=True ordena por coordenadas visuales (arriba a abajo), evitando desorden por cajas/marcos
        lineas = [
            line.strip()
            for line in page.get_text("text", sort=True).splitlines()
            if line.strip()
        ]
        paginas_lineas.append(lineas)
        if lineas:
            for candidata in (lineas[0], lineas[-1]):
                posibles_encabezados_pies[candidata] = (
                    posibles_encabezados_pies.get(candidata, 0) + 1
                )

    umbral_repeticion = max(3, len(doc) // 3)
    encabezados_pies_repetidos = {
        linea
        for linea, cuenta in posibles_encabezados_pies.items()
        if cuenta >= umbral_repeticion
        and not re.match(r"^(?:Art[íi]culo|Art\.)\s+\d+", linea)
    }

    patron_paginacion = re.compile(
        r"^(?:p[áa]gina\s*\d+(?:\s*de\s*\d+)?|\d+\s*/\s*\d+|-\s*\d+\s*-|\d+)$",
        re.IGNORECASE,
    )
    patron_estructura = re.compile(
        r"^(?:T[ÍI]TULO\s+[IVXLCDM0-9]+.*|T[ÍI]TULO\s+PRELIMINAR.*|"
        r"CAP[ÍI]TULO\s+(?:PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|SEXTO|[IVXLCDM0-9]+).*|"
        r"Secci[óo]n\s+\d+\.[ªaºo].*|"
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


def dividir_en_fragmentos(texto: str, nombre_tema: str) -> list[tuple[str, str]]:
    """
    Divide el texto por artículos (tanto si 'Artículo X' va en línea propia como si lleva título
    seguido en la misma línea, ej. 'Artículo 92 bis. Funcionarios...').
    """
    # Detecta 'Artículo X' o 'Art. X' (con mayúscula inicial) al comienzo de línea, con o sin título en la misma línea
    patron_articulo = re.compile(
        r"(?m)^((?:Art[íi]culo|Art\.)\s+\d+(?:\s+(?:bis|ter|quater))?)\.?(?=\s|$)"
    )
    coincidencias = list(patron_articulo.finditer(texto))

    fragmentos: list[tuple[str, str]] = []

    if coincidencias:
        for i, match in enumerate(coincidencias):
            ref_bruta = re.sub(r"\s+", " ", match.group(1).strip())
            num_match = re.search(
                r"\d+(?:\s+(?:bis|ter|quater))?", ref_bruta, re.IGNORECASE
            )
            art_str = f"Artículo {num_match.group(0)}" if num_match else ref_bruta
            referencia = f"{nombre_tema} | {art_str}"

            inicio_contenido = match.end()
            fin_contenido = (
                coincidencias[i + 1].start()
                if i + 1 < len(coincidencias)
                else len(texto)
            )
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
                ultimo_corte = max(
                    texto_limpio.rfind(". ", inicio + CHUNK_SIZE // 2, fin),
                    texto_limpio.rfind("\n", inicio + CHUNK_SIZE // 2, fin),
                )
                if ultimo_corte != -1:
                    fin = ultimo_corte + 1

            fragmento = texto_limpio[inicio:fin].strip()
            if fragmento:
                referencia = f"{nombre_tema} | Fragmento {num_frag}"
                fragmentos.append((referencia, fragmento))
                num_frag += 1

            if fin >= longitud:
                break
            inicio = max(inicio + 1, fin - CHUNK_OVERLAP)

    return fragmentos


def guardar_en_sqlite_preservando_usos(
    todos_los_fragmentos: list[tuple[str, str]],
    db_path: str = DB_PATH,
) -> tuple[int, int]:
    """
    Guarda o actualiza los fragmentos en SQLite conservando el contador `veces_usado`
    y `fallos_pendientes` de los fragmentos que ya existían en la base de datos.
    """
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS fragmentos (
                id INTEGER PRIMARY KEY,
                referencia TEXT,
                contenido TEXT,
                veces_usado INTEGER DEFAULT 0,
                fallos_pendientes INTEGER DEFAULT 0
            )
            """
        )
        # Asegurar que la columna fallos_pendientes exista en bases de datos previas
        columnas = {
            info[1] for info in cursor.execute("PRAGMA table_info(fragmentos)").fetchall()
        }
        if "fallos_pendientes" not in columnas:
            cursor.execute(
                "ALTER TABLE fragmentos ADD COLUMN fallos_pendientes INTEGER DEFAULT 0"
            )

        cursor.execute("SELECT referencia, veces_usado, fallos_pendientes FROM fragmentos")
        usos_previos = {}
        fallos_previos = {}
        for ref_existente, veces, fallos in cursor.fetchall():
            usos_previos[ref_existente] = max(usos_previos.get(ref_existente, 0), veces or 0)
            fallos_previos[ref_existente] = max(
                fallos_previos.get(ref_existente, 0), fallos or 0
            )

        nuevos = 0
        actualizados = 0
        registros_finales = []

        for referencia, contenido in todos_los_fragmentos:
            art_simple = (
                referencia.split(" | ")[-1] if " | " in referencia else referencia
            )
            if referencia in usos_previos:
                veces = usos_previos[referencia]
                fallos = fallos_previos.get(referencia, 0)
                actualizados += 1
            elif "Tema1" in referencia and art_simple in usos_previos:
                veces = usos_previos[art_simple]
                fallos = fallos_previos.get(art_simple, 0)
                actualizados += 1
            else:
                veces = 0
                fallos = 0
                nuevos += 1
            registros_finales.append((referencia, contenido, veces, fallos))

        cursor.execute("DELETE FROM fragmentos")
        cursor.executemany(
            "INSERT INTO fragmentos (referencia, contenido, veces_usado, fallos_pendientes) VALUES (?, ?, ?, ?)",
            registros_finales,
        )
        conn.commit()

    return nuevos, actualizados


def generar_informe_inventario(db_path: str = DB_PATH) -> str:
    """Genera un informe detallado por cada tema con la lista exacta de artículos guardados."""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, referencia, veces_usado FROM fragmentos ORDER BY id ASC")
        filas = cursor.fetchall()

    por_tema: dict[str, list[tuple[int, str, int]]] = {}
    for fid, ref, veces in filas:
        if " | " in ref:
            tema, art = ref.split(" | ", 1)
        else:
            tema, art = "General", ref
        por_tema.setdefault(tema, []).append((fid, art, veces))

    lineas = [
        "=" * 76,
        f"  INVENTARIO DE ARTÍCULOS EN BASE DE DATOS ({len(filas)} FRAGMENTOS TOTALES)",
        "=" * 76,
    ]
    for tema, items in por_tema.items():
        lista_arts = [it[1].replace("Artículo ", "Art. ") for it in items]
        usados = sum(1 for it in items if it[2] > 0)
        lineas.append(f"\n📚 {tema} -> {len(items)} artículos (preguntados al menos 1 vez: {usados})")
        lineas.append("-" * 76)
        # Mostrar en filas de 8 artículos para lectura cómoda
        for i in range(0, len(lista_arts), 8):
            bloque = ", ".join(lista_arts[i : i + 8])
            lineas.append(f"   {bloque}")

    lineas.append("\n" + "=" * 76)
    informe = "\n".join(lineas)

    with open(INVENTARIO_PATH, "w", encoding="utf-8") as f:
        f.write(informe + "\n")

    return informe


def main() -> None:
    archivos_pdf = obtener_archivos_pdf()
    print(f"Archivos PDF detectados ({len(archivos_pdf)}): {', '.join(archivos_pdf)}\n")

    todos_los_fragmentos: list[tuple[str, str]] = []
    for ruta_pdf in archivos_pdf:
        nombre_tema = nombre_tema_desde_archivo(ruta_pdf)
        with pymupdf.open(ruta_pdf) as doc:
            texto_limpio = limpiar_texto_paginas(doc)
        fragmentos_pdf = dividir_en_fragmentos(texto_limpio, nombre_tema)
        print(f"  - {ruta_pdf} -> {len(fragmentos_pdf)} artículos detectados ({nombre_tema})")
        todos_los_fragmentos.extend(fragmentos_pdf)

    nuevos, conservados = guardar_en_sqlite_preservando_usos(todos_los_fragmentos, DB_PATH)

    print(
        f"\n✅ Base de datos '{DB_PATH}' actualizada: {len(todos_los_fragmentos)} artículos totales "
        f"({nuevos} nuevos añadidos, {conservados} ya existentes conservando su historial).\n"
    )

    informe = generar_informe_inventario(DB_PATH)
    print(informe)
    print(f"\n📄 Se ha guardado también este desglose completo en '{INVENTARIO_PATH}'.")


if __name__ == "__main__":
    main()
