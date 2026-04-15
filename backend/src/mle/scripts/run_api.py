import uvicorn


def run() -> None:
    uvicorn.run("mle.api.app:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    run()

