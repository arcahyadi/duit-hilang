from pathlib import Path

from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def rupiah(value) -> str:
    try:
        return f"Rp {float(value):,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return "Rp 0"


templates.env.filters["rupiah"] = rupiah
