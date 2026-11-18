import importlib
import os
import sqlite3
from dotenv import load_dotenv

gen = importlib.import_module("2_generar_test")


def main() -> None:
    load_dotenv()
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    channel_id = os.getenv("TELEGRAM_CHANNEL_ID")

    if bot_token and bot_token != "tu_bot_token_de_telegram_aqui":
        gen.sincronizar_suscriptores(bot_token, channel_id, gen.DB_PATH)

    with sqlite3.connect(gen.DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT chat_id, nombre, fecha_alta, COALESCE(activo, 1) FROM suscriptores ORDER BY fecha_alta ASC"
        )
        suscriptores = cursor.fetchall()

        cursor.execute(
            """
            SELECT referencia, fallos_pendientes, veces_usado
            FROM fragmentos
            WHERE COALESCE(fallos_pendientes, 0) > 0
            ORDER BY fallos_pendientes DESC, id ASC
            """
        )
        articulos_marcados = cursor.fetchall()

    print("=" * 74)
    print(f"  ESTADÍSTICAS DE RENDIMIENTO ({len(suscriptores)} SUSCRIPTORES REGISTRADOS)")
    print("=" * 74)

    for cid, nombre_cif, _, activo in suscriptores:
        nombre = gen.descifrar_nombre(nombre_cif, bot_token)
        estado = "ACTIVO" if activo == 1 else "BAJA"
        informe = gen.construir_informe_semanal_usuario(cid, nombre, dias=7, db_path=gen.DB_PATH)
        print(f"\n👤 Usuario: {nombre} (ID: {cid} | {estado})")
        print("-" * 74)
        if informe:
            print(informe)
        else:
            print("  (Sin respuestas registradas todavía a partir de esta actualización)")

    print("\n" + "=" * 74)
    print(f"  🔄 ARTÍCULOS MARCADOS PARA REPASO ({len(articulos_marcados)} pendientes)")
    print("=" * 74)
    if articulos_marcados:
        for ref, fallos, veces in articulos_marcados:
            print(f"  • {ref:<45} | Fallos pendientes: {fallos} | Usos: {veces}")
    else:
        print("  Ningún artículo pendiente de refuerzo en este momento.")
    print("=" * 74)


if __name__ == "__main__":
    main()
