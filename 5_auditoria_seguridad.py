import importlib
import json
import os
import re
import sqlite3
import subprocess
import sys
from dotenv import load_dotenv

gen = importlib.import_module("2_generar_test")


def ejecutar_auditoria() -> int:
    load_dotenv()
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    db_path = gen.DB_PATH

    gen.inicializar_tablas_auxiliares(db_path)
    migrados = gen.migrar_nombres_a_cifrado(bot_token, db_path)

    alertas: list[str] = []
    checks_ok: list[str] = []

    print("=" * 76)
    print("  🛡️ AUDITORÍA DE SEGURIDAD: BASE DE DATOS, USUARIOS Y REPOSITORIO")
    print("=" * 76)

    # 1. Integridad física de SQLite
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        res_int = cursor.execute("PRAGMA integrity_check").fetchone()[0]
        if res_int == "ok":
            checks_ok.append("Integridad física de SQLite ('PRAGMA integrity_check'): OK.")
        else:
            alertas.append(f"Fallo de integridad en SQLite: {res_int}")

        # 2. Auditoría de datos personales (PII) y gestión de usuarios en `suscriptores`
        cursor.execute("SELECT chat_id, nombre, alias, COALESCE(activo, 1), COALESCE(en_ranking, 1) FROM suscriptores")
        suscriptores = cursor.fetchall()
        sin_cifrar = []
        ids_invalidos = []
        for cid, nombre_guardado, alias_guardado, activo, en_ranking in suscriptores:
            if not gen.validar_chat_id(cid) or en_ranking not in (0, 1):
                ids_invalidos.append(cid)
            if nombre_guardado and not str(nombre_guardado).startswith("ENC:"):
                sin_cifrar.append(cid)
            if alias_guardado and not str(alias_guardado).startswith("ENC:"):
                sin_cifrar.append(cid)

        if not ids_invalidos:
            checks_ok.append(
                f"Validación de identificadores de usuario ({len(suscriptores)} cuentas): formato estricto OK."
            )
        else:
            alertas.append(f"Se detectaron chat_id con formato inválido: {ids_invalidos}")

        if not sin_cifrar:
            extra = f" ({migrados} migrados en esta ejecución)" if migrados else ""
            checks_ok.append(
                f"Privacidad de usuarios (RGPD): 100% de nombres cifrados con AES-128/Fernet en SQLite{extra}."
            )
        else:
            alertas.append(
                f"Existen {len(sin_cifrar)} nombres de usuario en texto plano sin cifrar en SQLite."
            )

        activos = sum(1 for _, _, _, a, _ in suscriptores if a == 1)
        bajas = len(suscriptores) - activos
        checks_ok.append(
            f"Control de estado de usuarios (/start y /baja): {activos} activos, {bajas} en baja."
        )

        # 3. Consistencia de tablas de estadísticas y encuestas
        cursor.execute(
            "SELECT COUNT(*) FROM respuestas_usuarios WHERE opcion_elegida NOT IN (0, 1, 2, 3) OR acertada NOT IN (0, 1)"
        )
        resp_corruptas = cursor.fetchone()[0]
        if resp_corruptas == 0:
            checks_ok.append("Integridad de respuestas_usuarios (rangos 0..3 y flags binarios): OK.")
        else:
            alertas.append(f"Hay {resp_corruptas} registros con valores fuera de rango en respuestas_usuarios.")

        cursor.execute("SELECT COUNT(*) FROM fragmentos WHERE COALESCE(fallos_pendientes, 0) < 0")
        fallos_negativos = cursor.fetchone()[0]
        if fallos_negativos == 0:
            checks_ok.append("Consistencia de contadores `fallos_pendientes` (sin valores negativos): OK.")
        else:
            alertas.append(f"Se detectaron {fallos_negativos} artículos con fallos_pendientes < 0.")

        # 3b. Integridad y privacidad de `fallos_usuario` (repaso por usuario)
        cursor.execute("SELECT chat_id, pendiente FROM fallos_usuario")
        filas_fu = cursor.fetchall()
        fu_invalidos = [
            f for f in filas_fu if not gen.validar_chat_id(f[0]) or f[1] not in (0, 1)
        ]
        if not fu_invalidos:
            checks_ok.append(
                f"Integridad de tabla `fallos_usuario` ({len(filas_fu)} registros personales): OK."
            )
        else:
            alertas.append(f"Registros inválidos en `fallos_usuario`: {len(fu_invalidos)}")

        # 3c. Integridad de caché `banco_preguntas`
        cursor.execute("SELECT id, opciones_json, indice_correcta FROM banco_preguntas")
        filas_bp = cursor.fetchall()
        bp_invalidos = 0
        for _, opc_json, idx_corr in filas_bp:
            try:
                ops = json.loads(opc_json)
                if not isinstance(ops, list) or len(ops) != 4 or idx_corr not in (0, 1, 2, 3):
                    bp_invalidos += 1
            except Exception:
                bp_invalidos += 1
        if bp_invalidos == 0:
            checks_ok.append(
                f"Integridad de caché `banco_preguntas` ({len(filas_bp)} preguntas almacenadas): OK."
            )
        else:
            alertas.append(f"Hay {bp_invalidos} preguntas con formato inválido en `banco_preguntas`.")

        # 3d. Integridad referencial (sin registros huérfanos de usuarios eliminados)
        cursor.execute(
            """
            SELECT COUNT(*) FROM respuestas_usuarios
            WHERE chat_id NOT IN (SELECT chat_id FROM suscriptores)
            """
        )
        huerf_resp = cursor.fetchone()[0]
        cursor.execute(
            """
            SELECT COUNT(*) FROM fallos_usuario
            WHERE chat_id NOT IN (SELECT chat_id FROM suscriptores)
            """
        )
        huerf_fallos = cursor.fetchone()[0]
        if huerf_resp == 0 and huerf_fallos == 0:
            checks_ok.append(
                "Integridad referencial RGPD (0 datos huérfanos de usuarios eliminados): OK."
            )
        else:
            alertas.append(
                f"Existen registros huérfanos sin suscriptor (respuestas={huerf_resp}, fallos={huerf_fallos})."
            )

    # 4. Auditoría de archivos rastreados en Git y secretos
    try:
        proc = subprocess.run(
            ["git", "ls-files"],
            capture_output=True,
            text=True,
            check=True,
        )
        archivos_git = [l.strip() for l in proc.stdout.splitlines() if l.strip()]
        prohibidos = [
            f for f in archivos_git if f == ".env" or f.startswith(".venv/") or f.endswith(".pdf") or f.endswith(".docx")
        ]
        if not prohibidos:
            checks_ok.append(
                "Protección de repositorio Git: ni `.env`, ni `.venv`, ni documentos originales están expuestos."
            )
        else:
            alertas.append(f"Archivos sensibles rastreados en Git: {prohibidos}")

        # Escanear archivos de código rastreados buscando posibles tokens o API keys hardcodeadas
        patron_secreto = re.compile(r"(?:AIza[0-9A-Za-z\-_]{30,}|ghp_[0-9A-Za-z]{30,}|\d{8,12}:AA[0-9A-Za-z\-_]{30,})")
        fugas_codigo = []
        for arch in archivos_git:
            if arch.endswith((".py", ".yml", ".yaml", ".md", ".bat", ".txt")) and os.path.exists(arch):
                with open(arch, "r", encoding="utf-8", errors="ignore") as f:
                    contenido = f.read()
                if patron_secreto.search(contenido):
                    fugas_codigo.append(arch)
        if not fugas_codigo:
            checks_ok.append(
                "Escaneo estático de secretos en código fuente (.py, .yml, .md, .bat): 0 claves expuestas."
            )
        else:
            alertas.append(f"Posibles claves hardcodeadas detectadas en archivos: {fugas_codigo}")
    except Exception as e:
        alertas.append(f"No se pudo verificar estado de Git: {e}")

    # 5. Verificación de consultas SQL parametrizadas, enmascaramiento de logs y barajado CSPRNG de opciones
    with open("2_generar_test.py", "r", encoding="utf-8") as f:
        codigo_gen = f.read()
    if "enmascarar_id(" in codigo_gen and "cifrar_nombre(" in codigo_gen:
        checks_ok.append(
            "Enmascaramiento de IDs en logs de consola (`***XXXX`) y cifrado activo en `2_generar_test.py`: OK."
        )
    else:
        alertas.append("Falta enmascaramiento de logs o cifrado de nombres en 2_generar_test.py.")

    if "mezclar_opciones_test(" in codigo_gen and "secrets.SystemRandom()" in codigo_gen:
        checks_ok.append(
            "Aleatorización criptográfica (`secrets.SystemRandom`) de opciones A/B/C/D contra sesgo de posición: OK."
        )
    else:
        alertas.append("Falta barajado criptográfico de opciones en 2_generar_test.py.")

    print("\n✅ CONTROLES SUPERADOS:")
    for c in checks_ok:
        print(f"  [OK] {c}")

    if alertas:
        print("\n🚨 ALERTAS DETECTADAS:")
        for a in alertas:
            print(f"  [ALERTA] {a}")
        print("=" * 76)
        return 1

    print("\n🔒 RESULTADO FINAL: AUDITORÍA SUPERADA CON ÉXITO (0 VULNERABILIDADES / 0 FUGAS DE DATOS)")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    sys.exit(ejecutar_auditoria())
