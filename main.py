import argparse
import arcade
import threading
import time
from game import OnlineClient, SurvivalGame  # type: ignore
from server import GameServer  # type: ignore


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--name", default="")
    args = parser.parse_args()

    if args.server:
        GameServer(host=args.host, port=args.port).start()
        return

    embedded_server = None
    embedded_server_thread = None
    online_client = None
    try:
        online_client = OnlineClient(args.host, args.port, args.name)
        online_client.connect()
        print(f"Verbunden mit Server {args.host}:{args.port}")
    except Exception:
        # Kein Server gefunden: dieser erste Client wird automatisch Host.
        embedded_server = GameServer(host="0.0.0.0", port=args.port)
        embedded_server_thread = threading.Thread(target=embedded_server.start, daemon=True)
        embedded_server_thread.start()
        time.sleep(0.35)
        online_client = OnlineClient("127.0.0.1", args.port, args.name)
        online_client.connect()
        print(f"Dieser Client hostet jetzt auf Port {args.port}.")

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
