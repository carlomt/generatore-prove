# app/exam_gen.py
# -*- coding: utf-8 -*-

import os
import subprocess
import numpy as np
import pandas as pd


def escape_latex(s: str) -> str:
    if not isinstance(s, str):
        s = str(s)
    repl = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(repl.get(ch, ch) for ch in s)


def generate_single_tex_all_exams(
    df: pd.DataFrame,
    num_exams: int,
    num_questions: int | None = None,
    base_seed: int | None = None,
    escape: bool = True,
) -> str:
    def maybe_escape(x: str) -> str:
        return escape_latex(x) if escape else x

    latex = []
    latex.append(r"\documentclass[a4paper,12pt]{article}")
    latex.append(r"\usepackage[utf8]{inputenc}")
    latex.append(r"\usepackage[T1]{fontenc}")
    latex.append(r"\usepackage{amsmath}")
    latex.append(r"\usepackage{enumitem}")
    latex.append(r"\usepackage{geometry}")
    latex.append(r"\geometry{a4paper, margin=1in}")
    latex.append(r"\usepackage{lmodern}")
    latex.append(r"\begin{document}")

    rng = np.random.default_rng(base_seed)

    for exam_idx in range(1, num_exams + 1):
        question_order = rng.permutation(len(df))
        exam_df = df.iloc[question_order].reset_index(drop=True)
        if num_questions is not None and num_questions < len(exam_df):
            exam_df = exam_df.head(num_questions)

        latex.append(rf"\section*{{Compito {exam_idx}}}")
        latex.append(r"\vspace{0.2cm}")

        for q_idx, row in exam_df.iterrows():
            question_text = maybe_escape(row.iloc[0])

            answers = [row.iloc[j] for j in range(1, len(row))]
            answer_order = rng.permutation(len(answers))
            answers_series = pd.Series([answers[idx] for idx in answer_order])

            latex.append(rf"\subsection*{{Domanda {q_idx+1}}}")
            latex.append(question_text + r"\par")
            latex.append(r"\begin{enumerate}[label=\Alph*.]")
            for a in answers_series.tolist():
                latex.append(r"\item " + maybe_escape(a))
            latex.append(r"\end{enumerate}")
            latex.append(r"\vspace{0.35cm}")

        if exam_idx != num_exams:
            latex.append(r"\newpage")

    latex.append(r"\end{document}")
    return "\n".join(latex)


def compile_latex_to_pdf(tex_path: str, output_dir: str) -> None:
    cmd = [
        "pdflatex",
        "-interaction=nonstopmode",
        "-output-directory", output_dir,
        tex_path
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"pdflatex failed\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}")


def build_pdf_from_dataframe(
    df: pd.DataFrame,
    num_exams: int,
    num_questions: int | None,
    seed: int | None,
    out_dir: str,
    basename: str = "compiti",
    escape: bool = True,
) -> str:
    os.makedirs(out_dir, exist_ok=True)

    tex = generate_single_tex_all_exams(
        df=df,
        num_exams=num_exams,
        num_questions=num_questions,
        base_seed=seed,
        escape=escape,
    )

    tex_path = os.path.join(out_dir, f"{basename}.tex")
    with open(tex_path, "w", encoding="utf-8") as f:
        f.write(tex)

    compile_latex_to_pdf(tex_path, out_dir)

    pdf_path = os.path.join(out_dir, f"{basename}.pdf")
    if not os.path.exists(pdf_path):
        raise RuntimeError("PDF not produced")

    # Cleanup minimo
    for ext in [".aux", ".log", ".out", ".toc", ".fls", ".fdb_latexmk"]:
        p = os.path.join(out_dir, f"{basename}{ext}")
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass

    return pdf_path
