from aios.cli.app import app
from aios.infrastructure.path_codec import configure_utf8_stdio

if __name__ == "__main__":
    # The stdio setup must run before the CLI writes anything: without it the
    # Windows console codepage corrupts the JSON the DSH plugin reads.
    configure_utf8_stdio()
    app()
