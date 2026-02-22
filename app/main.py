# app/main.py
import io
import os
import tempfile
from typing import Optional

import pandas as pd
from fastapi import FastAPI, File, Form, UploadFile, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates

from .exam_gen import build_pdf_from_dataframe

app = FastAPI()
templates = Jinja2Templates(directory="app/templates")


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
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/generate")
async def generate(
    file: UploadFile = File(...),
    num_exams: int = Form(10),
    num_questions: Optional[int] = Form(None),
    seed: Optional[int] = Form(None),
    no_escape: bool = Form(False),
):
    df = read_table(file)
    df = normalize_df(df)

    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = build_pdf_from_dataframe(
            df=df,
            num_exams=int(num_exams),
            num_questions=(int(num_questions) if num_questions not in (None, "", "None") else None),
            seed=(int(seed) if seed not in (None, "", "None") else None),
            out_dir=tmp,
            basename="compiti",
            escape=(not no_escape),
        )

        # FastAPI deve servire un file persistente; copiamo in /tmp esterno
        out_pdf = os.path.join(tempfile.gettempdir(), next(tempfile._get_candidate_names()) + "_compiti.pdf")
        with open(pdf_path, "rb") as src, open(out_pdf, "wb") as dst:
            dst.write(src.read())

    return FileResponse(
        out_pdf,
        media_type="application/pdf",
        filename="compiti.pdf",
    )
