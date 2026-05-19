import argparse
import arcade
import threading
import time
from game import OnlineClient, SurvivalGame  # type: ignore
from server import GameServer  # type: ignore

CENTRAL_SERVER_HOST = "127.0.0.1"
CENTRAL_SERVER_PORT = 8765


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", action="store_true")
    parser.add_argument("--host", default=CENTRAL_SERVER_HOST)
    parser.add_argument("--port", type=int, default=CENTRAL_SERVER_PORT)
    parser.add_argument("--name", default="")
    parser.add_argument("--token", default="FAULI-PLAY-2026")
    args = parser.parse_args()

    if args.server:
        # Für weltweiten Zugriff: --host 0.0.0.0 starten.
        GameServer(host=args.host, port=args.port, join_token=args.token).start()
        return

    embedded_server = None
    embedded_server_thread = None
    online_client = None
    try:
        online_client = OnlineClient(args.host, args.port, args.name, args.token)
        online_client.connect()
        print(f"Verbunden mit Server {args.host}:{args.port}")
    except Exception:
        # Wenn kein Server läuft, lokal automatisch hosten, damit es immer klappt.
        embedded_server = GameServer(host="0.0.0.0", port=args.port, join_token=args.token)
        embedded_server_thread = threading.Thread(target=embedded_server.start, daemon=True)
        embedded_server_thread.start()
        time.sleep(0.35)
        online_client = OnlineClient("127.0.0.1", args.port, args.name, args.token)
        online_client.connect()
        print(f"Lokaler Server gestartet auf Port {args.port}.")

    _game = SurvivalGame(online_client=online_client)
    arcade.run()
    if online_client:
        online_client.close()
    if embedded_server:
        embedded_server.stop()
    if embedded_server_thread and embedded_server_thread.is_alive():
        embedded_server_thread.join(timeout=0.5)


if __name__ == "__main__":
    main()
