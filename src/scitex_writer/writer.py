#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_writer/writer.py

"""
Writer class for manuscript LaTeX compilation.

Provides object-oriented interface to scitex-writer functionality.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Callable, Optional

from scitex_logging import getLogger

from ._compile import (
    CompilationResult,
    compile_manuscript,
    compile_revision,
    compile_supplementary,
)
from ._dataclasses import ManuscriptTree, RevisionTree, SupplementaryTree
from ._dataclasses.config import DOC_TYPE_DIRS
from ._dataclasses.tree import ScriptsTree, SharedTree
from ._project._create import clone_writer_project
from ._utils._watch import watch_manuscript

logger = getLogger(__name__)


def _find_git_root(project_dir: Path) -> Optional[Path]:
    """Find git root for project directory."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
    except Exception:
        pass
    return None


class Writer:
    """LaTeX manuscript compiler."""

    def __init__(
        self,
        project_dir: Path,
        name: Optional[str] = None,
        git_strategy: Optional[str] = "child",
        branch: Optional[str] = None,
        tag: Optional[str] = None,
    ):
        """
        Initialize for project directory.

        If directory doesn't exist, creates new project.

        Parameters
        ----------
        project_dir : Path
            Path to project directory.
        name : str, optional
            Project name (used if creating new project).
        git_strategy : str, optional
            Git initialization strategy:
            - 'child': Create isolated git in project directory (default)
            - 'parent': Use parent git repository
            - 'origin': Preserve template's original git history
            - None or 'none': Disable git initialization
        branch : str, optional
            Specific branch of template repository to clone.
            If None, clones the default branch. Mutually exclusive with tag.
        tag : str, optional
            Specific tag/release of template repository to clone.
            If None, clones the default branch. Mutually exclusive with branch.
        """
        self.project_name = name or Path(project_dir).name
        self.project_dir = Path(project_dir)
        self.git_strategy = git_strategy
        self.branch = branch
        self.tag = tag

        ref_info = ""
        if branch:
            ref_info = f" (branch: {branch})"
        elif tag:
            ref_info = f" (tag: {tag})"
        logger.info(
            f"Writer: Initializing with:\n"
            f"    Project Name: {self.project_name}\n"
            f"    Project Directory: {self.project_dir.absolute()}\n"
            f"    Git Strategy: {self.git_strategy}{ref_info}..."
        )

        # Create or attach to project
        self.project_dir = self._attach_or_create_project(name)

        # Find git root (may be the project dir or a parent)
        self.git_root = _find_git_root(self.project_dir) or self.project_dir

        # Document accessors (pass git_root for efficiency)
        self.shared = SharedTree(self.project_dir / "00_shared", git_root=self.git_root)
        self.manuscript = ManuscriptTree(
            self.project_dir / "01_manuscript", git_root=self.git_root
        )
        self.supplementary = SupplementaryTree(
            self.project_dir / "02_supplementary", git_root=self.git_root
        )
        self.revision = RevisionTree(
            self.project_dir / "03_revision", git_root=self.git_root
        )
        self.scripts = ScriptsTree(self.project_dir / "scripts", git_root=self.git_root)

        logger.info(f"Writer: Initialization complete for {self.project_name}")

    def _attach_or_create_project(self, name: Optional[str] = None) -> Path:
        """
        Create new project or attach to existing one.

        If project directory doesn't exist, creates it based on git_strategy:
        - 'child': Full template with git initialization
        - 'parent'/'None': Minimal directory structure

        Parameters
        ----------
        name : str, optional
            Project name (used if creating new project).

        Returns
        -------
        Path
            Path to the project directory.
        """
        if self.project_dir.exists():
            logger.info(
                f"Writer: Attached to existing project at {self.project_dir.absolute()}"
            )
            # Verify existing project structure
            self._verify_project_structure()
            return self.project_dir

        project_name = name or self.project_dir.name

        logger.info(
            f"Writer: Creating new project '{project_name}' at {self.project_dir.absolute()}"
        )

        # Initialize project directory structure
        success = clone_writer_project(
            str(self.project_dir), self.git_strategy, self.branch, self.tag
        )

        if not success:
            logger.error(
                f"Writer: Failed to initialize project directory for {project_name}"
            )
            raise RuntimeError(
                f"Could not create project directory at {self.project_dir}"
            )

        # Verify project directory was created
        if not self.project_dir.exists():
            logger.error(
                f"Writer: Project directory {self.project_dir} was not created"
            )
            raise RuntimeError(f"Project directory {self.project_dir} was not created")

        logger.info(
            f"Writer: Successfully created project at {self.project_dir.absolute()}"
        )
        return self.project_dir

    def _verify_project_structure(self) -> None:
        """
        Verify attached project has expected structure.

        Checks:
        - Required directories exist (01_manuscript, 02_supplementary, 03_revision)

        Raises
        ------
        RuntimeError
            If structure is invalid.
        """
        required_dirs = [
            self.project_dir / "01_manuscript",
            self.project_dir / "02_supplementary",
            self.project_dir / "03_revision",
        ]

        for dir_path in required_dirs:
            if not dir_path.exists():
                logger.error(f"Writer: Expected directory missing: {dir_path}")
                raise RuntimeError(
                    f"Project structure invalid: missing {dir_path.name} directory"
                )

        logger.info(
            f"Writer: Project structure verified at {self.project_dir.absolute()}"
        )

    def compile_manuscript(
        self,
        timeout: int = 300,
        log_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        runner: Optional[Callable[..., CompilationResult]] = None,
    ) -> CompilationResult:
        """
        Compile manuscript to PDF with optional live callbacks.

        Runs scripts/shell/compile_manuscript.sh with configured settings.

        Parameters
        ----------
        timeout : int, optional
            Maximum compilation time in seconds (default: 300).
        log_callback : callable, optional
            Called with each log line: log_callback("Running pdflatex...").
        progress_callback : callable, optional
            Called with progress: progress_callback(50, "Pass 2/3").

        Returns
        -------
        CompilationResult
            With success status, PDF path, and errors/warnings.

        Examples
        --------
        >>> writer = Writer(Path("my_paper"))
        >>> result = writer.compile_manuscript()
        >>> if result.success:
        ...     print(f"PDF created: {result.output_pdf}")

        ``runner`` is the underlying compile implementation; it defaults
        to :func:`scitex_writer._compile.compile_manuscript`. Exposed so
        callers and tests can supply an alternate implementation without
        patching module internals.
        """
        runner = runner or compile_manuscript
        return runner(
            self.project_dir,
            timeout=timeout,
            log_callback=log_callback,
            progress_callback=progress_callback,
        )

    def compile_supplementary(
        self,
        timeout: int = 300,
        log_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        runner: Optional[Callable[..., CompilationResult]] = None,
    ) -> CompilationResult:
        """
        Compile supplementary materials to PDF with optional live callbacks.

        Runs scripts/shell/compile_supplementary.sh with configured settings.

        Parameters
        ----------
        timeout : int, optional
            Maximum compilation time in seconds (default: 300).
        log_callback : callable, optional
            Called with each log line.
        progress_callback : callable, optional
            Called with progress updates.

        Returns
        -------
        CompilationResult
            With success status, PDF path, and errors/warnings.

        Examples
        --------
        >>> writer = Writer(Path("my_paper"))
        >>> result = writer.compile_supplementary()
        >>> if result.success:
        ...     print(f"PDF created: {result.output_pdf}")

        ``runner`` defaults to
        :func:`scitex_writer._compile.compile_supplementary`; exposed for
        injection without patching module internals.
        """
        runner = runner or compile_supplementary
        return runner(
            self.project_dir,
            timeout=timeout,
            log_callback=log_callback,
            progress_callback=progress_callback,
        )

    def compile_revision(
        self,
        track_changes: bool = False,
        timeout: int = 300,
        log_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        runner: Optional[Callable[..., CompilationResult]] = None,
    ) -> CompilationResult:
        """
        Compile revision document with optional change tracking and live callbacks.

        Runs scripts/shell/compile_revision.sh with configured settings.

        Parameters
        ----------
        track_changes : bool, optional
            Enable change tracking in compiled PDF (default: False).
        timeout : int, optional
            Maximum compilation time in seconds (default: 300).
        log_callback : callable, optional
            Called with each log line.
        progress_callback : callable, optional
            Called with progress updates.

        Returns
        -------
        CompilationResult
            With success status, PDF path, and errors/warnings.

        Examples
        --------
        >>> writer = Writer(Path("my_paper"))
        >>> result = writer.compile_revision(track_changes=True)
        >>> if result.success:
        ...     print(f"Revision PDF: {result.output_pdf}")

        ``runner`` defaults to
        :func:`scitex_writer._compile.compile_revision`; exposed for
        injection without patching module internals.
        """
        runner = runner or compile_revision
        return runner(
            self.project_dir,
            track_changes=track_changes,
            timeout=timeout,
            log_callback=log_callback,
            progress_callback=progress_callback,
        )

    def get_section(self, section_name: str, doc_type: str = "manuscript"):
        """Get a DocumentSection by name and document type.

        Parameters
        ----------
        section_name : str
            Section name (e.g., 'abstract', 'introduction', 'title').
        doc_type : str
            Document type: 'shared', 'manuscript', 'supplementary', or 'revision'.

        Returns
        -------
        DocumentSection
            Section object with .read(), .write(), .commit(), .history(), .diff().

        Raises
        ------
        ValueError
            If doc_type is unknown or section_name not found.
        """
        doc_map = {
            "shared": self.shared,
            "manuscript": self.manuscript,
            "supplementary": self.supplementary,
            "revision": self.revision,
        }
        if doc_type not in doc_map:
            raise ValueError(
                f"Unknown doc_type: {doc_type}. Valid: {list(doc_map.keys())}"
            )

        doc = doc_map[doc_type]
        if doc_type == "shared":
            if not hasattr(doc, section_name):
                raise ValueError(
                    f"Section '{section_name}' not in shared. "
                    f"Available: {self._list_sections(doc)}"
                )
            return getattr(doc, section_name)
        else:
            if not hasattr(doc.contents, section_name):
                raise ValueError(
                    f"Section '{section_name}' not in {doc_type}. "
                    f"Available: {self._list_sections(doc.contents)}"
                )
            return getattr(doc.contents, section_name)

    def read_section(self, section_name: str, doc_type: str = "manuscript") -> str:
        """Read a section's content as string.

        Parameters
        ----------
        section_name : str
            Section name (e.g., 'abstract', 'introduction').
        doc_type : str
            Document type: 'shared', 'manuscript', 'supplementary', or 'revision'.

        Returns
        -------
        str
            Section content. Empty string if section file is empty or missing.

        Examples
        --------
        >>> writer = Writer(Path("my_paper"))
        >>> text = writer.read_section("abstract")
        >>> text = writer.read_section("title", "shared")
        """
        section = self.get_section(section_name, doc_type)
        content = section.read()
        if isinstance(content, list):
            content = "\n".join(content)
        return content or ""

    def write_section(
        self, section_name: str, content: str, doc_type: str = "manuscript"
    ) -> bool:
        """Write content to a section.

        Parameters
        ----------
        section_name : str
            Section name (e.g., 'abstract', 'introduction').
        content : str
            Content to write.
        doc_type : str
            Document type: 'shared', 'manuscript', 'supplementary', or 'revision'.

        Returns
        -------
        bool
            True if write succeeded.

        Examples
        --------
        >>> writer = Writer(Path("my_paper"))
        >>> writer.write_section("abstract", "New abstract text.")
        True
        """
        section = self.get_section(section_name, doc_type)
        return section.write(content)

    def _list_sections(self, tree_or_contents) -> list:
        """List available section names from a tree or contents object."""
        return [
            attr
            for attr in dir(tree_or_contents)
            if not attr.startswith("_")
            and hasattr(getattr(tree_or_contents, attr, None), "path")
        ]

    def watch(
        self,
        on_compile: Optional[Callable] = None,
        runner: Optional[Callable] = None,
    ) -> None:
        """Auto-recompile on file changes.

        ``runner`` defaults to
        :func:`scitex_writer._utils._watch.watch_manuscript`; exposed for
        injection without patching module internals.
        """
        runner = runner or watch_manuscript
        runner(self.project_dir, on_compile=on_compile)

    def get_pdf(self, doc_type: str = "manuscript") -> Optional[Path]:
        """Get output PDF path (Read)."""
        pdf = self.project_dir / DOC_TYPE_DIRS[doc_type] / f"{doc_type}.pdf"
        return pdf if pdf.exists() else None

    def delete(self) -> bool:
        """Delete project directory (Delete)."""
        try:
            logger.warning(
                f"Writer: Deleting project directory at {self.project_dir.absolute()}"
            )
            shutil.rmtree(self.project_dir)
            logger.info(
                f"Writer: Successfully deleted project at {self.project_dir.absolute()}"
            )
            return True
        except Exception as e:
            logger.error(
                f"Writer: Failed to delete project directory at {self.project_dir.absolute()}: {e}"
            )
            return False


__all__ = ["Writer"]

# EOF
