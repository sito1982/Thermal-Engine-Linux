#!/usr/bin/env python3
"""Generate complete Markdown representations of the project's Python modules."""

from __future__ import annotations

import argparse
import ast
import hashlib
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CODE_DOCS_DIR = PROJECT_ROOT / "docs" / "codigo"
GENERAL_INDEX = PROJECT_ROOT / "docs" / "00 - Índice.md"
EXPECTED_SOURCE_COUNT = 50

EXCLUDED_DIR_NAMES = {
    ".claude",
    ".git",
    ".obsidian",
    ".venv",
    "__pycache__",
    "docs",
    "tests",
    "venv",
}
EXCLUDED_SOURCE_PATHS = {
    Path("scripts/generate_code_markdown.py"),
    Path("scripts/render_lcd_preview.py"),
    Path("scripts/verify_code_markdown.py"),
}


@dataclass(frozen=True)
class SourceDocument:
    """A Python source file and its deterministic Markdown representation."""

    source_path: Path
    relative_path: Path
    markdown_path: Path
    content: str


def source_line_count(source: str) -> int:
    """Return the conventional line count for source text."""
    if not source:
        return 0
    return source.count("\n") + (0 if source.endswith("\n") else 1)


def find_python_sources(project_root: Path = PROJECT_ROOT) -> list[Path]:
    """Find project Python modules while excluding generated and local directories."""
    source_paths: list[Path] = []
    for path in project_root.rglob("*.py"):
        relative_path = path.relative_to(project_root)
        if any(part in EXCLUDED_DIR_NAMES for part in relative_path.parts):
            continue
        if relative_path in EXCLUDED_SOURCE_PATHS:
            continue
        source_paths.append(path)

    source_paths.sort(key=lambda path: path.relative_to(project_root).as_posix())
    return source_paths


def markdown_path_for(source_path: Path, project_root: Path = PROJECT_ROOT) -> Path:
    """Return the mirror-path Markdown representation for a source module."""
    return project_root / "docs" / "codigo" / (source_path.relative_to(project_root).as_posix() + ".md")


def _format_import(node: ast.Import | ast.ImportFrom) -> str:
    if isinstance(node, ast.Import):
        return "import " + ", ".join(
            alias.name if alias.asname is None else f"{alias.name} as {alias.asname}"
            for alias in node.names
        )

    module = "." * node.level + (node.module or "")
    imported_names = ", ".join(
        alias.name if alias.asname is None else f"{alias.name} as {alias.asname}"
        for alias in node.names
    )
    return f"from {module} import {imported_names}"


def extract_structure(source: str, source_label: str) -> tuple[str | None, list[str], list[str], list[str]]:
    """Extract direct module-level declarations without interpreting their behavior."""
    try:
        tree = ast.parse(source, filename=source_label)
    except SyntaxError as error:
        raise ValueError(f"No se pudo analizar {source_label}: {error}") from error

    docstring_source: str | None = None
    if tree.body:
        first_node = tree.body[0]
        if (
            isinstance(first_node, ast.Expr)
            and isinstance(first_node.value, ast.Constant)
            and isinstance(first_node.value.value, str)
        ):
            docstring_source = ast.get_source_segment(source, first_node)
            if docstring_source is None:
                raise ValueError(f"No se pudo extraer el docstring de {source_label}")

    imports = [
        _format_import(node)
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    classes = [node.name for node in tree.body if isinstance(node, ast.ClassDef)]
    functions = [
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    return docstring_source, imports, classes, functions


def code_fence_for(source: str) -> str:
    """Choose a backtick fence that cannot be closed by the source content."""
    runs = re.findall(r"`+", source)
    longest_run = max((len(run) for run in runs), default=0)
    return "`" * max(3, longest_run + 1)


def _markdown_list(items: list[str], empty_message: str) -> list[str]:
    if not items:
        return [empty_message]
    return [f"- `{item}`" for item in items]


def render_module_markdown(source_path: Path, project_root: Path = PROJECT_ROOT) -> str:
    """Render one complete, deterministic Markdown document from a Python module."""
    relative_path = source_path.relative_to(project_root)
    try:
        source_bytes = source_path.read_bytes()
        source = source_bytes.decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError(f"No se pudo leer {relative_path.as_posix()}: {error}") from error

    source_label = relative_path.as_posix()
    docstring_source, imports, classes, functions = extract_structure(source, source_label)
    digest = hashlib.sha256(source_bytes).hexdigest()
    markdown_path = markdown_path_for(source_path, project_root)
    source_link = Path(os.path.relpath(source_path, markdown_path.parent)).as_posix()
    fence = code_fence_for(source)

    lines = [
        "---",
        "generated: true",
        f'source_path: "{source_label}"',
        f"source_sha256: {digest}",
        f"source_bytes: {len(source_bytes)}",
        f"source_lines: {source_line_count(source)}",
        'generated_by: "scripts/generate_code_markdown.py"',
        "---",
        "",
        f"# Código: `{source_label}`",
        "",
        "> [!info] Representación generada",
        "> Este documento se genera a partir del archivo Python original. "
        f"[{source_label}]({source_link}) es la fuente de verdad.",
        "",
    ]

    if docstring_source is not None:
        lines.extend(
            [
                "## Docstring de módulo",
                "",
                f"{fence}python",
                docstring_source,
                fence,
                "",
            ]
        )

    lines.extend(
        [
            "## Estructura extraída",
            "",
            "Las listas siguientes se extraen mecánicamente del nivel superior del módulo; no interpretan el comportamiento del código.",
            "",
            "### Imports directos",
            "",
            *_markdown_list(imports, "Ninguna declaración de importación directa de primer nivel."),
            "",
            "### Clases directas",
            "",
            *_markdown_list(classes, "Ninguna clase declarada directamente en el módulo."),
            "",
            "### Funciones directas",
            "",
            *_markdown_list(functions, "Ninguna función declarada directamente en el módulo."),
            "",
            "## Código fuente íntegro",
            "",
            f"{fence}python",
        ]
    )
    separator = "" if source.endswith("\n") else "\n"
    return "\n".join(lines) + "\n" + source + separator + fence + "\n"


def module_link(relative_path: Path) -> str:
    """Return an Obsidian wikilink to a mirrored module representation."""
    note_path = relative_path.as_posix()
    return f"[[{note_path}|`{note_path}`]]"


def render_code_index(source_paths: list[Path], project_root: Path = PROJECT_ROOT) -> str:
    """Render the deterministic index for all generated code documents."""
    relative_paths = [path.relative_to(project_root) for path in source_paths]
    root_modules = [path for path in relative_paths if len(path.parts) == 1]
    custom_elements = [path for path in relative_paths if path.parts[0] == "elements"]
    script_utilities = [path for path in relative_paths if path.parts[0] == "scripts"]
    other_modules = [
        path
        for path in relative_paths
        if path not in root_modules + custom_elements + script_utilities
    ]

    lines = [
        "---",
        "generated: true",
        f"source_count: {len(relative_paths)}",
        'generated_by: "scripts/generate_code_markdown.py"',
        "---",
        "",
        "# Índice de código",
        "",
        "> [!info] Representaciones íntegras",
        "> Cada enlace lleva a una nota generada que contiene el código Python completo y metadatos mecánicos. Los archivos `.py` originales siguen siendo las fuentes de verdad.",
        "",
        "## Regeneración y comprobación",
        "",
        "```bash",
        "python3 scripts/generate_code_markdown.py",
        "python3 scripts/verify_code_markdown.py",
        "```",
        "",
        "## Módulos de la aplicación",
        "",
        *[f"- {module_link(path)}" for path in root_modules],
        "",
        "## Elementos extensibles",
        "",
        *[f"- {module_link(path)}" for path in custom_elements],
        "",
        "## Utilidades de scripts",
        "",
        *[f"- {module_link(path)}" for path in script_utilities],
    ]
    if other_modules:
        lines.extend(
            [
                "",
                "## Otros módulos",
                "",
                *[f"- {module_link(path)}" for path in other_modules],
            ]
        )
    lines.append("")
    return "\n".join(lines)


def expected_documents(project_root: Path = PROJECT_ROOT) -> dict[Path, str]:
    """Build every expected generated document in memory."""
    source_paths = find_python_sources(project_root)
    if len(source_paths) != EXPECTED_SOURCE_COUNT:
        raise ValueError(
            f"Se esperaban {EXPECTED_SOURCE_COUNT} módulos Python, "
            f"pero se encontraron {len(source_paths)}. Revise la política de exclusión."
        )

    documents = {
        markdown_path_for(source_path, project_root): render_module_markdown(source_path, project_root)
        for source_path in source_paths
    }
    documents[project_root / "docs" / "codigo" / "00 - Índice de código.md"] = render_code_index(
        source_paths, project_root
    )
    return documents


def stale_markdown_documents(expected_paths: set[Path], project_root: Path = PROJECT_ROOT) -> list[Path]:
    """Return generated-looking module documents without a corresponding expected path."""
    code_docs_dir = project_root / "docs" / "codigo"
    if not code_docs_dir.exists():
        return []
    return sorted(
        (path for path in code_docs_dir.rglob("*.py.md") if path not in expected_paths),
        key=lambda path: path.as_posix(),
    )


def write_documents(documents: dict[Path, str]) -> tuple[list[Path], list[Path]]:
    """Write only new or changed generated documents; never delete stale files."""
    written: list[Path] = []
    unchanged: list[Path] = []
    for path, content in sorted(documents.items(), key=lambda item: item[0].as_posix()):
        if path.is_file() and path.read_text(encoding="utf-8") == content:
            unchanged.append(path)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written, unchanged


def relative_to_root(path: Path, project_root: Path = PROJECT_ROOT) -> str:
    """Format a project-relative path for terminal output."""
    return path.relative_to(project_root).as_posix()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Genera representaciones Markdown completas del código Python."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="muestra los documentos que se generarían sin escribirlos",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="comprueba que los documentos generados están sincronizados sin escribirlos",
    )
    arguments = parser.parse_args()
    if arguments.dry_run and arguments.check:
        parser.error("--dry-run y --check no se pueden usar simultáneamente")

    try:
        documents = expected_documents()
        expected_paths = set(documents)
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    if arguments.dry_run:
        print(f"Se generarían {len(documents)} documentos:")
        for path in sorted(documents, key=lambda document: document.as_posix()):
            print(f"- {relative_to_root(path)}")
        return 0

    if arguments.check:
        changed = [
            path
            for path, content in documents.items()
            if not path.is_file() or path.read_text(encoding="utf-8") != content
        ]
        stale = stale_markdown_documents(expected_paths)
        if not changed and not stale:
            print(f"Correcto: {len(documents) - 1} módulos y el índice están sincronizados.")
            return 0
        for path in changed:
            print(f"Desincronizado o ausente: {relative_to_root(path)}", file=sys.stderr)
        for path in stale:
            print(f"Documento obsoleto: {relative_to_root(path)}", file=sys.stderr)
        return 1

    written, unchanged = write_documents(documents)
    stale = stale_markdown_documents(expected_paths)
    print(f"Documentos escritos: {len(written)}; sin cambios: {len(unchanged)}.")
    for path in written:
        print(f"- {relative_to_root(path)}")
    if stale:
        print("No se eliminan documentos obsoletos automáticamente:", file=sys.stderr)
        for path in stale:
            print(f"- {relative_to_root(path)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
