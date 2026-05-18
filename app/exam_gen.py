# -*- coding: utf-8 -*-

import os
import subprocess
from typing import Optional

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


def exam_label_from_index(exam_idx: int) -> str:
    label = ""
    n = exam_idx
    while n > 0:
        n -= 1
        label = chr(ord("A") + (n % 26)) + label
        n //= 26
    return label


def generate_question_block(
    question_number: int,
    question_text: str,
    answers: list[str],
    escape: bool = True,
) -> list[str]:
    def maybe_escape(x: str) -> str:
        return escape_latex(x) if escape else str(x)

    lines = []
    lines.append(r"\par\medskip")
    lines.append(r"\noindent\begin{minipage}{\textwidth}")
    lines.append(rf"\textbf{{Domanda {question_number}.}}")
    lines.append(maybe_escape(question_text) + r"\par")
    lines.append("")

    clean_answers = [a for a in answers if str(a).strip() != ""]
    if clean_answers:
        lines.append(r"\begin{itemize}")
        for a_idx, answer in enumerate(clean_answers):
            letter = chr(ord("a") + a_idx)
            lines.append(rf"\item {letter}) {maybe_escape(answer)}")
        lines.append(r"\end{itemize}")

    lines.append(r"\end{minipage}")
    lines.append(r"\par\vspace{0.8cm}")
    lines.append("")
    return lines


def load_template(template_path: str) -> str:
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()
    if "{{CONTENT}}" not in template:
        raise ValueError(
            f"Template {template_path!r} does not contain the required {{CONTENT}} placeholder"
        )
    return template


def generate_content(
    df: pd.DataFrame,
    num_exams: int,
    num_questions: Optional[int],
    seed: Optional[int],
    escape: bool,
) -> str:
    rng = np.random.default_rng(seed)
    content: list[str] = []

    for exam_idx in range(1, num_exams + 1):
        compito_label = exam_label_from_index(exam_idx)
        last_page_label = f"LastPageExam{compito_label}"

        if exam_idx > 1:
            content.append(r"\clearpage")

        content.append(r"\setcounter{page}{1}")
        content.append(rf"\setexamlastpagelabel{{{last_page_label}}}")
        content.append("")
        content.append(rf"\section*{{Compito {compito_label}}}")
        content.append(r"\vspace{0.2cm}")

        question_order = rng.permutation(len(df))
        exam_df = df.iloc[question_order].reset_index(drop=True)
        if num_questions is not None and num_questions < len(exam_df):
            exam_df = exam_df.head(num_questions)

        for q_idx, row in exam_df.iterrows():
            question_text = row.iloc[0]
            answers = [row.iloc[j] for j in range(1, len(row)) if str(row.iloc[j]).strip() != ""]
            answer_order = rng.permutation(len(answers)) if answers else []
            shuffled_answers = [answers[idx] for idx in answer_order]

            content.extend(
                generate_question_block(
                    question_number=q_idx + 1,
                    question_text=question_text,
                    answers=shuffled_answers,
                    escape=escape,
                )
            )

        content.append(rf"\label{{{last_page_label}}}")
        content.append("")

    return "\n".join(content)


def compile_latex_to_pdf(tex_path: str, output_dir: str) -> None:
    tex_name = os.path.basename(os.path.abspath(tex_path))
    output_abs = os.path.abspath(output_dir)

    cmd = [
        "latexmk",
        "-pdf",
        "-interaction=nonstopmode",
        "-halt-on-error",
        tex_name,
    ]
    r = subprocess.run(
        cmd,
        cwd=output_abs,
        capture_output=True,
        text=True,
        encoding="latin-1",
        errors="replace",
    )
    if r.returncode != 0:
        raise RuntimeError(f"latexmk/pdflatex failed\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}")


def build_pdf_from_dataframe(
    df: pd.DataFrame,
    num_exams: int,
    num_questions: int | None,
    seed: int | None,
    out_dir: str,
    template_path: str,
    basename: str = "compiti",
    escape: bool = True,
) -> str:
    os.makedirs(out_dir, exist_ok=True)

    template = load_template(template_path)
    content = generate_content(
        df=df,
        num_exams=num_exams,
        num_questions=num_questions,
        seed=seed,
        escape=escape,
    )
    tex = template.replace("{{CONTENT}}", content)

    tex_path = os.path.join(out_dir, f"{basename}.tex")
    with open(tex_path, "w", encoding="utf-8") as f:
        f.write(tex)

    compile_latex_to_pdf(tex_path, out_dir)

    pdf_path = os.path.join(out_dir, f"{basename}.pdf")
    if not os.path.exists(pdf_path):
        raise RuntimeError("PDF not produced")

    for ext in [".aux", ".log", ".out", ".toc", ".fls", ".fdb_latexmk"]:
        p = os.path.join(out_dir, f"{basename}{ext}")
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass

    return pdf_path
