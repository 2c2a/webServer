"""允许通过 ``python -m app.cli`` 调用 CLI。"""
from app.cli.main import app

if __name__ == "__main__":
    app()
