#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_writer/_utils/_verify_tree_structure.py

"""Project structure validation for writer module.

Leverages dataclass verify_structure() methods for validation."""

from __future__ import annotations

from pathlib import Path

from scitex_logging import getLogger

from .._dataclasses import (
    ConfigTree,
    ManuscriptTree,
    RevisionTree,
    ScriptsTree,
    SharedTree,
    SupplementaryTree,
)

logger = getLogger(__name__)

# Parameters
TREE_VALIDATORS = {
    "config": {"dir_name": "config", "tree_class": ConfigTree},
    "00_shared": {"dir_name": "00_shared", "tree_class": SharedTree},
    "01_manuscript": {
        "dir_name": "01_manuscript",
        "tree_class": ManuscriptTree,
    },
    "02_supplementary": {
        "dir_name": "02_supplementary",
        "tree_class": SupplementaryTree,
    },
    "03_revision": {"dir_name": "03_revision", "tree_class": RevisionTree},
    "scripts": {"dir_name": "scripts", "tree_class": ScriptsTree},
}


# Exception classes
class ProjectValidationError(Exception):
    """Raised when project structure is invalid."""

    pass


# 2. Public validation functions
def verify_tree_structure(
    project_dir: Path, func_name="validate_tree_structures"
) -> None:
    """Validates all tree structures in the project directory."""
    logger.info(
        f"{func_name}: Validating tree structures: {Path(project_dir).absolute()}..."
    )
    project_dir = Path(project_dir)
    for dir_name in TREE_VALIDATORS.keys():
        validator_func_name = f"_validate_{dir_name}_structure"
        eval(validator_func_name)(project_dir)
    logger.info(
        f"{func_name}: Validated tree structures: {Path(project_dir).absolute()}"
    )
    return True


# 3. Internal validation functions
def _validate_01_manuscript_structure(project_dir: Path) -> bool:
    """Validates manuscript structure."""
    return _validate_tree_structure_base(
        project_dir, **TREE_VALIDATORS["01_manuscript"]
    )


def _validate_02_supplementary_structure(project_dir: Path) -> bool:
    """Validates supplementary structure."""
    return _validate_tree_structure_base(
        project_dir, **TREE_VALIDATORS["02_supplementary"]
    )


def _validate_03_revision_structure(project_dir: Path) -> bool:
    """Validates revision structure."""
    return _validate_tree_structure_base(project_dir, **TREE_VALIDATORS["03_revision"])


def _validate_config_structure(project_dir: Path) -> bool:
    """Validates config structure."""
    return _validate_tree_structure_base(project_dir, **TREE_VALIDATORS["config"])


def _validate_scripts_structure(project_dir: Path) -> bool:
    """Validates scripts structure."""
    return _validate_tree_structure_base(project_dir, **TREE_VALIDATORS["scripts"])


def _validate_00_shared_structure(project_dir: Path) -> bool:
    """Validates shared structure."""
    return _validate_tree_structure_base(project_dir, **TREE_VALIDATORS["00_shared"])


# 4. Helper functions
def _validate_tree_structure_base(
    project_dir: Path, dir_name: str, tree_class: type = None
) -> bool:
    """Base validation function that checks directory existence and verifies structure using tree class.

    Args:
        project_dir: Root project directory
        dir_name: Name of directory to validate
        tree_class: Tree class with verify_structure method

    Returns
    -------
        True if structure is valid

    Raises
    ------
        ProjectValidationError: If directory missing or structure invalid
    """
    project_dir = Path(project_dir)
    target_dir = project_dir / dir_name
    if not target_dir.exists():
        raise ProjectValidationError(f"Required directory missing: {target_dir}")
    if tree_class is not None:
        doc = tree_class(target_dir, git_root=project_dir)
        is_valid, issues = doc.verify_structure()
        if not is_valid:
            raise ProjectValidationError(
                f"{dir_name} structure invalid:\n"
                + "\n".join(f"  - {issue}" for issue in issues)
            )
    logger.debug(f"{dir_name} structure valid: {project_dir}")
    return True


__all__ = ["verify_tree_structure", "ProjectValidationError"]

# EOF
