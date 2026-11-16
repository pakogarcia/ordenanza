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
            "SELECT chat_id, nombre, fecha_alta FROM suscriptores ORDER BY fecha_alta ASC"
        )
        filas = cursor.fetchall()

    print("=" * 68)
    print(f"  USUARIOS ACTIVOS EN EL BOT (@ordenayuncordoba_bot): {len(filas)}")
    print("=" * 68)
    for idx, (cid, nombre, fecha) in enumerate(filas, start=1):
        print(f"  {idx}. {nombre:<28} | ID: {cid:<12} | Alta: {fecha}")
    print("=" * 68)


if __name__ == "__main__":
    main()
