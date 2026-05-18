#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import io
import os
import subprocess
from typing import Optional

import numpy as np
import pandas as pd


LATEX_SPECIAL_CHARS = {
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


def escape_latex(value) -> str:
    """
    Escape LaTeX special characters in normal text.

    Use --no-escape if your CSV already contains LaTeX commands that you want
    to preserve.
    """
    if value is None:
        return ""

    if not isinstance(value, str):
        value = str(value)

    return "".join(LATEX_SPECIAL_CHARS.get(ch, ch) for ch in value)


def read_table(path: str) -> pd.DataFrame:
    """
    Read CSV, XLS or XLSX.

    CSV separator is guessed among ; , and tab.
    """
    name = path.lower()

    if name.endswith(".xlsx") or name.endswith(".xls"):
        return pd.read_excel(path)

    with open(path, "rb") as f:
        content = f.read()

    if not content:
        raise ValueError("Empty input file")

    text = content.decode("utf-8-sig", errors="replace")

    for sep in [";", ",", "\t"]:
        try:
            df = pd.read_csv(io.StringIO(text), sep=sep)
            if df.shape[1] >= 2:
                return df
        except Exception:
            pass

    return pd.read_csv(io.StringIO(text))


def normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Expected format:
      first column  = question
      other columns = possible answers

    Empty columns and rows are removed.
    NaN values are converted to empty strings.
    """
    df = df.dropna(axis=1, how="all")
    df = df.dropna(axis=0, how="all")

    if df.shape[1] < 2:
        raise ValueError("Need at least 2 columns: question + answers")

    return df.fillna("")


def exam_label_from_index(exam_idx: int) -> str:
    """
    Convert 1 -> A, 2 -> B, ..., 26 -> Z, 27 -> AA, etc.
    """
    label = ""
    n = exam_idx

    while n > 0:
        n -= 1
        label = chr(ord("A") + (n % 26)) + label
        n //= 26

    return label


def generate_exam_header(
    compito_label: str,
    title: str,
    subtitle: str,
    escape: bool = True,
) -> list[str]:
    def maybe_escape(x: str) -> str:
        return escape_latex(x) if escape else str(x)

    lines = []

    lines.append(r"\begin{center}")
    lines.append(rf"    {{\huge {maybe_escape(title)}}} \\")
    lines.append(rf"    {{\large {maybe_escape(subtitle)}}}\\")
    lines.append(rf"    {{\large Compito {compito_label}}}")
    lines.append(r"\end{center}")
    lines.append("")
    lines.append(r"\begin{table}[!h]")
    lines.append(r"\begin{center}")
    lines.append(r"\begin{tabular}{| c | c | c |}")
    lines.append(r"\hline")
    lines.append(r"\textbf{Nome e Cognome} & \textbf{Matricola} & \textbf{Canale} \\")
    lines.append(r"\hline")
    lines.append(r"    \hspace{9cm} & \hspace{4cm} & \hspace{4cm} \\")
    lines.append(r"    \hspace{9cm} & \hspace{4cm} & \textbf{} \\")
    lines.append(r"\hline")
    lines.append(r"\end{tabular}")
    lines.append(r"\end{center}")
    lines.append(r"\end{table}")
    lines.append("")
    lines.append(
        r"Barrare per ciascuna domanda la risposta ritenuta corretta "
        r"o riempire gli spazi liberi con la parola ritenuta corretta."
    )
    lines.append("")
    lines.append(r"\vspace{0.6cm}")
    lines.append("")

    return lines


def generate_question_block(
    question_number: int,
    question_text: str,
    answers: list[str],
    escape: bool = True,
    answer_labels: bool = True,
) -> list[str]:
    """
    Generate one non-breakable question block.

    The minipage prevents the question title from being left alone at the
    bottom of one page while the question body goes to the next page.
    """
    def maybe_escape(x) -> str:
        return escape_latex(x) if escape else str(x)

    lines = []

    lines.append(r"\par\medskip")
    lines.append(r"\noindent\begin{minipage}{\textwidth}")
    lines.append(rf"\textbf{{Domanda {question_number}.}}")
    lines.append("")
    lines.append(maybe_escape(question_text) + r"\par")
    lines.append("")

    clean_answers = [a for a in answers if str(a).strip() != ""]

    if clean_answers:
        lines.append(r"\begin{itemize}")
        for a_idx, answer in enumerate(clean_answers):
            if answer_labels:
                letter = chr(ord("a") + a_idx)
                lines.append(rf"\item {letter}) {maybe_escape(answer)}")
            else:
                lines.append(rf"\item {maybe_escape(answer)}")
        lines.append(r"\end{itemize}")

    lines.append(r"\end{minipage}")
    lines.append(r"\par\vspace{0.8cm}")
    lines.append("")

    return lines


def generate_content(
    df: pd.DataFrame,
    num_exams: int,
    num_questions: Optional[int],
    seed: Optional[int],
    title: str,
    subtitle: str,
    escape: bool = True,
    answer_labels: bool = True,
) -> str:
    rng = np.random.default_rng(seed)
    content = []

    for exam_idx in range(1, num_exams + 1):
        compito_label = exam_label_from_index(exam_idx)
        last_page_label = f"LastPageExam{compito_label}"

        if exam_idx > 1:
            content.append(r"\clearpage")

        # Restart page numbering for each exam.
        content.append(r"\setcounter{page}{1}")

        # Tell the template which label is the last page for this exam.
        content.append(rf"\setexamlastpagelabel{{{last_page_label}}}")
        content.append("")

        content.extend(
            generate_exam_header(
                compito_label=compito_label,
                title=title,
                subtitle=subtitle,
                escape=escape,
            )
        )

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
                    answer_labels=answer_labels,
                )
            )

        # Label the last page of this exam.
        # The footer uses \pageref{LastPageExamA}, etc.
        content.append(rf"\label{{{last_page_label}}}")
        content.append("")

    return "\n".join(content)


def load_template(template_path: str) -> str:
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    if "{{CONTENT}}" not in template:
        raise ValueError(
            f"Template {template_path!r} does not contain the required {{CONTENT}} placeholder"
        )

    return template


def build_tex_from_template(
    df: pd.DataFrame,
    template_path: str,
    num_exams: int,
    num_questions: Optional[int],
    seed: Optional[int],
    title: str,
    subtitle: str,
    out_dir: str,
    basename: str,
    escape: bool = True,
    answer_labels: bool = True,
) -> str:
    os.makedirs(out_dir, exist_ok=True)

    template = load_template(template_path)

    content = generate_content(
        df=df,
        num_exams=num_exams,
        num_questions=num_questions,
        seed=seed,
        title=title,
        subtitle=subtitle,
        escape=escape,
        answer_labels=answer_labels,
    )

    tex = template.replace("{{CONTENT}}", content)

    tex_path = os.path.join(out_dir, f"{basename}.tex")

    with open(tex_path, "w", encoding="utf-8") as f:
        f.write(tex)

    return tex_path


def compile_latex_to_pdf(tex_path: str, output_dir: str, runs: int = 2) -> None:
    """
    Compile LaTeX.

    Two runs are needed to resolve page references such as:
      Pag. 1 di 4

    encoding/errors avoid crashes when pdflatex writes non-UTF8 messages.
    """
    cmd = [
        "pdflatex",
        "-interaction=nonstopmode",
        "-output-directory",
        output_dir,
        tex_path,
    ]

    last_run = None

    for _ in range(runs):
        last_run = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="latin-1",
            errors="replace",
        )

        if last_run.returncode != 0:
            raise RuntimeError(
                "pdflatex failed\n"
                f"STDOUT:\n{last_run.stdout}\n"
                f"STDERR:\n{last_run.stderr}"
            )

    if last_run is not None:
        unresolved = "??" in last_run.stdout
        if unresolved:
            print(
                "Warning: LaTeX may still contain unresolved references. "
                "Try compiling once more or check the .log file."
            )


def build_pdf_from_template(
    df: pd.DataFrame,
    template_path: str,
    num_exams: int,
    num_questions: Optional[int],
    seed: Optional[int],
    title: str,
    subtitle: str,
    out_dir: str,
    basename: str = "compiti",
    escape: bool = True,
    answer_labels: bool = True,
) -> str:
    tex_path = build_tex_from_template(
        df=df,
        template_path=template_path,
        num_exams=num_exams,
        num_questions=num_questions,
        seed=seed,
        title=title,
        subtitle=subtitle,
        out_dir=out_dir,
        basename=basename,
        escape=escape,
        answer_labels=answer_labels,
    )

    compile_latex_to_pdf(tex_path, out_dir, runs=2)

    pdf_path = os.path.join(out_dir, f"{basename}.pdf")

    if not os.path.exists(pdf_path):
        raise RuntimeError("PDF not produced")

    return pdf_path


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate randomized exam PDFs from a CSV/XLS/XLSX file."
    )

    parser.add_argument(
        "input",
        help="Input CSV, XLS or XLSX file. First column = question; following columns = answers.",
    )

    parser.add_argument(
        "--template",
        default="quiz_style_template.tex",
        help="LaTeX template file containing the {{CONTENT}} placeholder.",
    )

    parser.add_argument(
        "-n",
        "--num-exams",
        type=positive_int,
        default=10,
        help="Number of exam versions to generate.",
    )

    parser.add_argument(
        "-q",
        "--num-questions",
        type=positive_int,
        default=None,
        help="Number of questions per exam. Default: use all questions.",
    )

    parser.add_argument(
        "-o",
        "--output-dir",
        default="output",
        help="Output directory.",
    )

    parser.add_argument(
        "-b",
        "--basename",
        default="compiti",
        help="Base name for .tex and .pdf output files.",
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional random seed for reproducible shuffling.",
    )

    parser.add_argument(
        "--title",
        default="Corso Fisica - Anno Accademico 2025/26",
        help="Title printed at the top of each exam.",
    )

    parser.add_argument(
        "--subtitle",
        default="Quiz in Aula",
        help="Subtitle printed at the top of each exam.",
    )

    parser.add_argument(
        "--no-escape",
        action="store_true",
        help="Do not escape LaTeX special characters in questions and answers.",
    )

    parser.add_argument(
        "--no-answer-labels",
        action="store_true",
        help="Do not add a), b), c) labels before answers.",
    )

    args = parser.parse_args()

    df = read_table(args.input)
    df = normalize_df(df)

    pdf_path = build_pdf_from_template(
        df=df,
        template_path=args.template,
        num_exams=args.num_exams,
        num_questions=args.num_questions,
        seed=args.seed,
        title=args.title,
        subtitle=args.subtitle,
        out_dir=args.output_dir,
        basename=args.basename,
        escape=not args.no_escape,
        answer_labels=not args.no_answer_labels,
    )

    tex_path = os.path.join(args.output_dir, f"{args.basename}.tex")

    print(f"TEX generato: {tex_path}")
    print(f"PDF generato: {pdf_path}")


if __name__ == "__main__":
    main()
