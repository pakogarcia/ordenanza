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

        total_cache = cursor.execute("SELECT COUNT(*) FROM banco_preguntas").fetchone()[0]

    print("=" * 74)
    print(
        f"  ESTADÍSTICAS INDIVIDUALES ({len(suscriptores)} SUSCRIPTORES | {total_cache} PREGUNTAS EN CACHÉ)"
    )
    print("=" * 74)

    with sqlite3.connect(gen.DB_PATH) as conn:
        cursor = conn.cursor()
        for cid, nombre_cif, _, activo in suscriptores:
            nombre = gen.descifrar_nombre(nombre_cif, bot_token)
            estado = "ACTIVO" if activo == 1 else "BAJA"
            informe = gen.construir_informe_semanal_usuario(cid, nombre, dias=7, db_path=gen.DB_PATH)

            cursor.execute(
                """
                SELECT f.referencia
                FROM fallos_usuario fu
                JOIN fragmentos f ON f.id = fu.fragmento_id
                WHERE fu.chat_id = ? AND fu.pendiente = 1
                ORDER BY fu.ultima_actualizacion DESC
                """,
                (cid,),
            )
            pendientes_user = [r[0] for r in cursor.fetchall()]

            print(f"\n👤 Usuario: {nombre} (ID: {cid} | {estado})")
            print("-" * 74)
            if informe:
                print(informe)
            else:
                print("  (Sin respuestas registradas todavía en los últimos 7 días)")
            print(f"  🔄 Repasos personales pendientes ({len(pendientes_user)}): {', '.join(pendientes_user) if pendientes_user else 'Ninguno'}")

    print("\n" + "=" * 74)


if __name__ == "__main__":
    main()
