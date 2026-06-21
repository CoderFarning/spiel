import argparse
import arcade
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

    online_client = None
    online_client = OnlineClient(args.host, args.port, args.name, args.token)
    online_client.connect()
    print(f"Verbunden mit Server {args.host}:{args.port}")

    _game = SurvivalGame(online_client=online_client)
    arcade.run()
    if online_client:
        online_client.close()


if __name__ == "__main__":
    main()
