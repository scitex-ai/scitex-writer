Installation
============

Requirements
------------

- Python 3.10 or higher
- Docker (for container-based LaTeX compilation)

Install from PyPI
-----------------

.. code-block:: bash

    pip install scitex-writer

Install from Source
-------------------

.. code-block:: bash

    git clone https://github.com/ywatanabe1989/scitex-writer.git
    cd scitex-writer
    pip install -e .

For development:

.. code-block:: bash

    pip install -e ".[dev]"

With GUI editor (requires Flask):

.. code-block:: bash

    uv pip install 'scitex-writer[all]'

Docker Setup
------------

SciTeX Writer uses Docker for consistent LaTeX compilation. Make sure Docker is installed and running:

.. code-block:: bash

    # Verify Docker is available
    docker --version

The compilation system will automatically pull the required LaTeX image when needed.

Verification
------------

Verify the installation:

.. code-block:: bash

    scitex-writer --version
    scitex-writer --help
