import argparse
import sys
import threading
from pathlib import Path
import traceback

import arcade

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from CLIENT.game import OnlineClient, SurvivalGame  # type: ignore
    from SERVER.server import GameServer  # type: ignore
except ImportError:
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

    online_client = OnlineClient(args.host, args.port, args.name, args.token)
    connect_error = {"message": ""}

    def connect_in_background():
        try:
            online_client.connect()
            print(f"Verbunden mit Server {args.host}:{args.port}")
        except Exception as exc:
            connect_error["message"] = str(exc)
            print(f"Server nicht erreichbar: {exc}")

    threading.Thread(target=connect_in_background, daemon=True).start()
    try:
        _game = SurvivalGame(online_client=online_client)
        arcade.run()
    except Exception:
        traceback.print_exc()
        raise
    finally:
        online_client.close()


if __name__ == "__main__":
    main()
