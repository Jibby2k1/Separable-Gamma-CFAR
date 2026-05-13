#!/usr/bin/env python3
"""Generate a local API reference from public ``__all__`` exports.

The generator is intentionally import-free for project modules. It reads Python
source with ``ast`` so reference generation does not depend on internet access,
raw data files, optional GPU libraries, or import-time side effects.
"""
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path


DEFAULT_PACKAGE_ROOT = "neurobench"
DEFAULT_OUTPUT = Path("docs/API_REFERENCE.md")


@dataclass(frozen=True)
class ApiEntry:
    package: str
    name: str
    kind: str
    module: str
    signature: str
    summary: str


@dataclass(frozen=True)
class PackageApi:
    module: str
    summary: str
    entries: tuple[ApiEntry, ...]


def _module_name(root: Path, path: Path) -> str:
    return ".".join(path.relative_to(root).with_suffix("").parts)


def _source_tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _summary(docstring: str | None) -> str:
    if not docstring:
        return "No docstring summary available."
    for line in docstring.strip().splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return "No docstring summary available."


def _literal_string_list(node: ast.AST) -> tuple[str, ...]:
    try:
        value = ast.literal_eval(node)
    except (SyntaxError, ValueError):
        return ()
    if isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value):
        return tuple(value)
    return ()


def _public_names(init_tree: ast.Module) -> tuple[str, ...]:
    for node in init_tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets):
            return _literal_string_list(node.value)
    return ()


def _imported_modules(init_tree: ast.Module) -> dict[str, str]:
    modules: dict[str, str] = {}
    for node in init_tree.body:
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        for alias in node.names:
            exported_name = alias.asname or alias.name
            modules[exported_name] = node.module
    return modules


def _definition_nodes(tree: ast.Module) -> dict[str, ast.AST]:
    definitions: dict[str, ast.AST] = {}
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            definitions[node.name] = node
    return definitions


def _function_signature(name: str, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
    signature = f"{prefix}{name}({ast.unparse(node.args)})"
    if node.returns is not None:
        signature += f" -> {ast.unparse(node.returns)}"
    return signature


def _class_signature(name: str, node: ast.ClassDef) -> str:
    for child in node.body:
        if isinstance(child, ast.FunctionDef) and child.name == "__init__":
            args = list(child.args.args)
            if args and args[0].arg == "self":
                child.args.args = args[1:]
            try:
                return f"class {name}({ast.unparse(child.args)})"
            finally:
                child.args.args = args
    return f"class {name}"


def _entry_from_definition(package: str, module: str, name: str, node: ast.AST) -> ApiEntry:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return ApiEntry(
            package=package,
            name=name,
            kind="function",
            module=module,
            signature=_function_signature(name, node),
            summary=_summary(ast.get_docstring(node)),
        )
    if isinstance(node, ast.ClassDef):
        return ApiEntry(
            package=package,
            name=name,
            kind="class",
            module=module,
            signature=_class_signature(name, node),
            summary=_summary(ast.get_docstring(node)),
        )
    return ApiEntry(
        package=package,
        name=name,
        kind="object",
        module=module,
        signature=name,
        summary="No docstring summary available.",
    )


def _submodule_entry(root: Path, package: str, package_dir: Path, name: str) -> ApiEntry | None:
    module_path = package_dir / f"{name}.py"
    init_path = package_dir / name / "__init__.py"
    if module_path.exists():
        module = _module_name(root, module_path)
        summary = _summary(ast.get_docstring(_source_tree(module_path)))
        return ApiEntry(package, name, "module", module, module, summary)
    if init_path.exists():
        module = _module_name(root, init_path)
        summary = _summary(ast.get_docstring(_source_tree(init_path)))
        return ApiEntry(package, name, "module", module, module, summary)
    return None


def _module_path(root: Path, module: str) -> Path:
    return root.joinpath(*module.split(".")).with_suffix(".py")


def _find_definition_in_package(root: Path, package_dir: Path, name: str) -> tuple[str, ast.AST] | None:
    for path in sorted(package_dir.rglob("*.py")):
        if path.name == "__init__.py":
            continue
        definitions = _definition_nodes(_source_tree(path))
        if name in definitions:
            return _module_name(root, path), definitions[name]
    return None


def collect_public_api(root: Path, package_root: str = DEFAULT_PACKAGE_ROOT) -> tuple[PackageApi, ...]:
    """Collect public package exports without importing project modules."""
    root = root.resolve()
    package_root_dir = root / package_root
    packages: list[PackageApi] = []

    for init_path in sorted(package_root_dir.rglob("__init__.py")):
        package_dir = init_path.parent
        package = _module_name(root, init_path).removesuffix(".__init__")
        init_tree = _source_tree(init_path)
        public_names = _public_names(init_tree)
        if not public_names:
            continue

        imported_modules = _imported_modules(init_tree)
        entries: list[ApiEntry] = []
        for name in public_names:
            entry: ApiEntry | None = None
            imported_module = imported_modules.get(name)
            if imported_module:
                path = _module_path(root, imported_module)
                if path.exists():
                    definition = _definition_nodes(_source_tree(path)).get(name)
                    if definition is not None:
                        entry = _entry_from_definition(package, imported_module, name, definition)

            if entry is None:
                entry = _submodule_entry(root, package, package_dir, name)

            if entry is None:
                found = _find_definition_in_package(root, package_dir, name)
                if found is not None:
                    module, definition = found
                    entry = _entry_from_definition(package, module, name, definition)

            if entry is None:
                entry = ApiEntry(package, name, "object", package, name, "Exported by __all__.")

            entries.append(entry)

        packages.append(
            PackageApi(
                module=package,
                summary=_summary(ast.get_docstring(init_tree)),
                entries=tuple(sorted(entries, key=lambda item: item.name.lower())),
            )
        )

    return tuple(packages)


def render_reference(packages: tuple[PackageApi, ...]) -> str:
    """Render a deterministic Markdown API reference."""
    lines: list[str] = [
        "# Neurobench API Reference",
        "",
        "Generated by `python tools/generate_api_reference.py`.",
        "",
        (
            "This reference is built from local source files only. It uses package "
            "`__all__` declarations plus AST-parsed docstrings and signatures, so "
            "it does not need internet access, raw video data, or optional runtime imports."
        ),
        "",
    ]

    for package in packages:
        lines.extend([f"## `{package.module}`", "", package.summary, ""])
        for entry in package.entries:
            lines.extend(
                [
                    f"### `{entry.name}`",
                    "",
                    f"- Kind: `{entry.kind}`",
                    f"- Source: `{entry.module}`",
                    f"- Signature: `{entry.signature}`",
                    f"- Summary: {entry.summary}",
                    "",
                ]
            )

    return "\n".join(lines).rstrip() + "\n"


def write_reference(root: Path, output: Path, package_root: str = DEFAULT_PACKAGE_ROOT) -> Path:
    packages = collect_public_api(root, package_root=package_root)
    rendered = render_reference(packages)
    output_path = output if output.is_absolute() else root / output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")
    return output_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--package-root", default=DEFAULT_PACKAGE_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    output = write_reference(args.root, args.output, package_root=args.package_root)
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
