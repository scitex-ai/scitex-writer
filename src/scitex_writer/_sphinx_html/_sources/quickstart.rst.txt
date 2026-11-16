Quick Start
===========

This guide helps you get started with SciTeX Writer.

Clone a Template Project
------------------------

Start by cloning the template project:

.. code-block:: bash

    scitex-writer clone template ./my-manuscript

Or using Python:

.. code-block:: python

    import scitex_writer as sw
    sw.project.clone("template", "./my-manuscript")

Project Structure
-----------------

The cloned project has this structure:

.. code-block:: text

    my-manuscript/
    ├── 00_shared/           # Shared metadata and bibliography
    │   ├── meta/            # Title, authors, keywords
    │   └── bib_files/       # BibTeX files
    ├── 01_manuscript/       # Main manuscript
    │   └── contents/        # Text, figures, tables
    ├── 02_supplementary/    # Supplementary materials
    └── 03_revision/         # Revision with tracked changes

Compile Documents
-----------------

Compile your manuscript to PDF:

.. code-block:: bash

    scitex-writer compile manuscript ./my-manuscript

Or all document types:

.. code-block:: bash

    scitex-writer compile all ./my-manuscript

Using Python:

.. code-block:: python

    import scitex_writer as sw

    # Compile manuscript
    result = sw.compile.manuscript("./my-manuscript")
    print(f"PDF: {result.pdf_path}")

    # Compile all documents
    results = sw.compile.all("./my-manuscript")

Manage Bibliography
-------------------

List, add, or remove bibliography entries:

.. code-block:: bash

    # List entries
    scitex-writer bib list ./my-manuscript

    # Add entry
    scitex-writer bib add ./my-manuscript --key "smith2024" --bibtex "@article{...}"

Using Python:

.. code-block:: python

    import scitex_writer as sw

    entries = sw.bib.list("./my-manuscript")
    sw.bib.add("./my-manuscript", key="smith2024", bibtex="@article{...}")

MCP Server for AI Agents
------------------------

Start the MCP server for AI agent integration:

.. code-block:: bash

    scitex-writer mcp start

This exposes 38 tools for manuscript management via the Model Context Protocol.
