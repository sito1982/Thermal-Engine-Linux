#!/usr/bin/env python3
"""Verify that generated Markdown representations match the Python sources."""

from __future__ import annotations

import sys
from pathlib import Path

from generate_code_markdown import (
    EXPECTED_SOURCE_COUNT,
    GENERAL_INDEX,
    PROJECT_ROOT,
    expected_documents,
    relative_to_root,
    stale_markdown_documents,
)

CODE_INDEX_LINK = "[[codigo/00 - Índice de código]]"


def main() -> int:
    try:
        documents = expected_documents(PROJECT_ROOT)
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    module_paths = [path for path in documents if path.name.endswith(".py.md")]
    errors: list[str] = []
    if len(module_paths) != EXPECTED_SOURCE_COUNT:
        errors.append(
            f"Se esperaban {EXPECTED_SOURCE_COUNT} representaciones de módulos, "
            f"pero se calcularon {len(module_paths)}."
        )

    for path, expected_content in sorted(documents.items(), key=lambda item: item[0].as_posix()):
        relative_path = relative_to_root(path, PROJECT_ROOT)
        if not path.is_file():
            errors.append(f"Falta: {relative_path}")
            continue
        try:
            actual_content = path.read_text(encoding="utf-8")
        except OSError as error:
            errors.append(f"No se pudo leer {relative_path}: {error}")
            continue
        if actual_content != expected_content:
            errors.append(f"Desincronizado: {relative_path}")

    for path in stale_markdown_documents(set(documents), PROJECT_ROOT):
        errors.append(f"Documento obsoleto: {relative_to_root(path, PROJECT_ROOT)}")

    if not GENERAL_INDEX.is_file():
        errors.append(f"Falta el índice general: {relative_to_root(GENERAL_INDEX, PROJECT_ROOT)}")
    else:
        try:
            general_index_content = GENERAL_INDEX.read_text(encoding="utf-8")
        except OSError as error:
            errors.append(f"No se pudo leer el índice general: {error}")
        else:
            if CODE_INDEX_LINK not in general_index_content:
                errors.append(
                    f"Falta el enlace {CODE_INDEX_LINK} en "
                    f"{relative_to_root(GENERAL_INDEX, PROJECT_ROOT)}"
                )

    if errors:
        print("VALIDACIÓN FALLIDA:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(
        f"Validación correcta: {EXPECTED_SOURCE_COUNT} módulos, "
        "sus representaciones Markdown y los índices están sincronizados."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
