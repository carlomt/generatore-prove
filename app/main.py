# app/main.py
import io
import os
import tempfile
from typing import Optional

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates

from .exam_gen import build_pdf_from_dataframe

app = FastAPI()
templates = Jinja2Templates(directory="app/templates")
generated_exams_count = 0


def parse_optional_int(raw_value: Optional[str], field_name: str) -> Optional[int]:
    if raw_value is None:
        return None

    value = str(raw_value).strip()
    if value == "":
        return None

    try:
        return int(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"{field_name} must be a valid integer") from exc


def parse_required_int(raw_value: str, field_name: str) -> int:
    parsed = parse_optional_int(raw_value, field_name)
    if parsed is None:
        raise HTTPException(status_code=422, detail=f"{field_name} is required")
    return parsed


def read_table(upload: UploadFile) -> pd.DataFrame:
    name = (upload.filename or "").lower()

    content = upload.file.read()
    if not content:
        raise ValueError("Empty file")

    if name.endswith(".xlsx") or name.endswith(".xls"):
        # Excel
        return pd.read_excel(io.BytesIO(content))

    # CSV (prova separatori)
    text = content.decode("utf-8-sig", errors="replace")
    for sep in [";", ",", "\t"]:
        try:
            df = pd.read_csv(io.StringIO(text), sep=sep)
            # euristica: almeno 2 colonne (domanda + risposte)
            if df.shape[1] >= 2:
                return df
        except Exception:
            pass
    # ultimo tentativo default pandas
    return pd.read_csv(io.StringIO(text))


def normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    # Se excel ha intestazioni strane, tieni tutto come valori
    # qui assumiamo: prima colonna = domanda, le altre = risposte
    if df.shape[1] < 2:
        raise ValueError("Need at least 2 columns: question + answers")

    # Rimuovi colonne completamente vuote
    df = df.dropna(axis=1, how="all")

    # Rimuovi righe completamente vuote
    df = df.dropna(axis=0, how="all")

    # Converte NaN in stringa vuota (evita 'nan' nelle risposte)
    df = df.fillna("")
    return df


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "generated_exams_count": generated_exams_count,
        },
    )


@app.post("/generate")
async def generate(
    file: UploadFile = File(...),
    num_exams: str = Form("10"),
    num_questions: Optional[str] = Form(None),
    no_escape: bool = Form(False),
):
    global generated_exams_count

    parsed_num_exams = parse_required_int(num_exams, "num_exams")
    parsed_num_questions = parse_optional_int(num_questions, "num_questions")

    if parsed_num_exams <= 0:
        raise HTTPException(status_code=422, detail="num_exams must be greater than 0")
    if parsed_num_questions is not None and parsed_num_questions <= 0:
        raise HTTPException(status_code=422, detail="num_questions must be greater than 0")

    try:
        df = read_table(file)
        df = normalize_df(df)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    with tempfile.TemporaryDirectory() as tmp:
        try:
            pdf_path = build_pdf_from_dataframe(
                df=df,
                num_exams=parsed_num_exams,
                num_questions=parsed_num_questions,
                seed=None,
                out_dir=tmp,
                basename="compiti",
                escape=(not no_escape),
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        # FastAPI deve servire un file persistente; copiamo in /tmp esterno
        out_pdf = os.path.join(tempfile.gettempdir(), next(tempfile._get_candidate_names()) + "_compiti.pdf")
        with open(pdf_path, "rb") as src, open(out_pdf, "wb") as dst:
            dst.write(src.read())

    generated_exams_count += parsed_num_exams

    return FileResponse(
        out_pdf,
        media_type="application/pdf",
        filename="compiti.pdf",
    )
