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
        filas = cursor.fetchall()

    activos = sum(1 for f in filas if f[3] == 1)
    print("=" * 78)
    print(f"  USUARIOS EN EL BOT (@ordenayuncordoba_bot): {activos} activos / {len(filas)} totales")
    print("=" * 78)
    for idx, (cid, nombre_cif, fecha, activo) in enumerate(filas, start=1):
        nombre = gen.descifrar_nombre(nombre_cif, bot_token)
        estado = "✅ ACTIVO" if activo == 1 else "🔕 BAJA"
        cif_ok = "🔒 AES" if str(nombre_cif).startswith("ENC:") else "⚠️ PLANO"
        print(f"  {idx}. {nombre:<26} | ID: {cid:<11} | {estado} | {cif_ok} | Alta: {fecha}")
    print("=" * 78)


if __name__ == "__main__":
    main()
