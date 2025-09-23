import typer, json, requests, os
app = typer.Typer(help="Facehugger CLI for Mother")

DEFAULT_API = os.getenv("MOTHER_API_URL", "http://localhost:8000")

@app.command("nudge")
def nudge_now(title: str, why: str = ""):
    payload = {"routine": title, "why": why, "micro_step": "2-minute start"}
    r = requests.post(f"{DEFAULT_API}/nudge/preview", json=payload, timeout=10)
    r.raise_for_status()
    msg = r.json().get("message", "no message")
    print(msg)

@app.command("demo")
def demo():
    r = requests.get(f"{DEFAULT_API}/nudge/demo", timeout=5)
    r.raise_for_status()
    print(r.json().get("message", "no message"))

if __name__ == "__main__":
    app()
