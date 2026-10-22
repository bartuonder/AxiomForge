import csv
import io
import random

from e2b_code_interpreter import Sandbox

from app.config import E2B_API_KEY


class SandboxCodeError(RuntimeError):
    pass

DATA_PATH = "/home/user/data.csv"
RUN_TIMEOUT_SECONDS = 240
SANDBOX_LIFETIME_SECONDS = 300


def build_csv(csv_schema: str) -> str:
    columns = []
    for part in csv_schema.split(","):
        piece = part.strip()
        if not piece:
            continue
        if ":" in piece:
            name, kind = piece.split(":", 1)
            columns.append((name.strip(), kind.strip().lower()))
        else:
            columns.append((piece, "float"))
    if len(columns) < 2:
        raise ValueError("csv schema needs features and a target column")
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([name for name, _ in columns])
    rng = random.Random(0)
    for index in range(80):
        row = []
        for position, (_, kind) in enumerate(columns):
            if position == len(columns) - 1:
                row.append(index % 2)
            elif kind.startswith("int"):
                row.append(rng.randint(0, 40))
            elif kind.startswith("str") or kind in {"category", "object"}:
                row.append(rng.choice(["a", "b"]))
            else:
                row.append(round(rng.random() * 100, 3))
        writer.writerow(row)
    return buffer.getvalue()


def run_classification(code: str, csv_schema: str) -> str:
    if not E2B_API_KEY:
        raise RuntimeError("E2B_API_KEY is missing")
    csv_text = build_csv(csv_schema)
    sandbox = Sandbox.create(api_key=E2B_API_KEY, timeout=SANDBOX_LIFETIME_SECONDS)
    try:
        sandbox.files.write(DATA_PATH, csv_text)
        execution = sandbox.run_code(code, timeout=RUN_TIMEOUT_SECONDS)
    finally:
        sandbox.kill()
    if execution.error is not None:
        raise SandboxCodeError(
            f"{execution.error.name}: {execution.error.value}\n{execution.error.traceback}"
        )
    return "\n".join(execution.logs.stdout)
