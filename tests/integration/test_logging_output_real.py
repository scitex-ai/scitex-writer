"""Real offline controls for launcher levels and uncaptured CLI JSON."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import scitex_writer


def _run(tmp_path, code, level="info", after_import=""):
    home = tmp_path / "home"
    home.mkdir()
    env = {
        "PATH": str(Path(sys.executable).parent) + os.pathsep + os.defpath,
        "HOME": str(home),
        "TMPDIR": str(tmp_path),
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
        "PYTHONPATH": str(Path(scitex_writer.__file__).resolve().parents[1]),
        "PYTHONDONTWRITEBYTECODE": "1",
        "NO_COLOR": "1",
    }
    script = (
        "import sys\nfrom pathlib import Path\n"
        "def guard(event,args):\n"
        "    if event in {'socket.bind','socket.connect','socket.getaddrinfo'}:\n"
        "        raise RuntimeError('logging controls must remain offline')\n"
        "sys.addaudithook(guard)\nimport scitex_logging as logging\n"
        f"logging.configure(level={level!r},enable_file=False,capture_prints=False)\n"
        + after_import
        + "\n"
        + code
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stderr
    return result


@pytest.mark.parametrize("level", ["info", "critical"])
def test_api_json_is_plain_at_the_default_print_capture_setting(tmp_path, level):
    # Arrange
    code = "from scitex_writer._cli.introspect import cmd_api\nassert cmd_api('math',max_depth=0,as_json=True)==0"
    # Act
    result = _run(tmp_path, code, level)
    # Assert
    assert all(
        (
            json.loads(result.stdout) == [{"Name": "math", "Type": "M", "Depth": 0}],
            result.stderr == "",
        )
    ), result.stderr


@pytest.mark.parametrize("level", ["info", "critical"])
def test_actual_mcp_inventory_json_keeps_envelope_at_default_print_capture_setting(
    tmp_path, level
):
    # Arrange
    code = "from scitex_writer._cli.mcp import cmd_list_tools\nassert cmd_list_tools(as_json=True)==0"
    # Act
    result = _run(tmp_path, code, level)
    output = json.loads(result.stdout)
    modules = output["modules"]
    # Assert
    assert all(
        (
            output["name"] == "scitex-writer",
            output["result_envelope"]["type"] == "object",
            output["total"] == sum((item["count"] for item in modules.values())),
            all((item["count"] == len(item["tools"]) for item in modules.values())),
            "writer_compile_manuscript" in modules["compile"]["tools"],
            result.stderr == "",
        )
    ), result.stderr


@pytest.mark.parametrize("level", ["info", "critical"])
def test_banner_honors_late_level_changes_and_remains_single_stream(tmp_path, level):
    # Arrange
    code = f"logging.configure(level='critical',enable_file=False,capture_prints=True)\nserver._print_startup(Path('synthetic'), '127.0.0.1',31291,['127.0.0.1'])\nlogging.configure(level={level!r},enable_file=False,capture_prints=True)\nserver._print_startup(Path('synthetic'), '127.0.0.1',31291,['127.0.0.1'])\nserver._print_startup(Path('synthetic'), '127.0.0.1',31291,['127.0.0.1'])"
    # Act
    result = _run(
        tmp_path, code, level, "from scitex_writer._django import _server as server"
    )
    # Assert
    assert all(
        (
            result.stderr == "",
            all(
                (
                    result.stdout.count("SciTeX Writer GUI: http://127.0.0.1:31291")
                    == 2,
                    result.stdout.count("Project: synthetic") == 2,
                    result.stdout.count("Press Ctrl+C to stop") == 2,
                )
            )
            if level == "info"
            else all((result.stdout == "",)),
        )
    ), result.stderr


@pytest.mark.parametrize("level", ["warning", "critical"])
def test_wildcard_warning_is_thresholded_stderr_with_remedy(tmp_path, level):
    # Arrange
    code = "from scitex_writer._django import _server as server\nserver._print_startup(Path('synthetic'),'0.0.0.0',31291,['0.0.0.0'])"
    # Act
    result = _run(tmp_path, code, level)
    # Assert
    assert all(
        (
            result.stdout == "",
            all(
                (
                    result.stderr.count("SCITEX_WRITER_ALLOWED_HOSTS=") == 1,
                    "400" in result.stderr,
                )
            )
            if level == "warning"
            else all((result.stderr == "",)),
        )
    ), result.stderr


@pytest.mark.parametrize("level", ["warning", "critical"])
def test_degraded_shell_notice_is_visible_diagnostic_with_install_remedy(
    tmp_path, level
):
    # Arrange
    code = "from scitex_writer._django import _server as server\nserver._warn_missing_shell('synthetic missing dependency','pip install synthetic')"
    # Act
    result = _run(tmp_path, code, level)
    # Assert
    assert all(
        (
            result.stdout == "",
            all(
                (
                    "synthetic missing dependency" in result.stderr,
                    "serving bare Django instead" in result.stderr,
                    "pip install synthetic" in result.stderr,
                )
            )
            if level == "warning"
            else all((result.stderr == "",)),
        )
    ), result.stderr


@pytest.mark.parametrize("level", ["info", "critical"])
def test_real_launcher_announces_only_until_django_import_without_starting_server(
    tmp_path, level
):
    # Arrange
    code = (
        "from scitex_writer._django import _server as server\n"
        "class StopBeforeDjango(RuntimeError): pass\n"
        "def no_django(event,args):\n"
        "    if event=='import' and args[0]=='django':\n"
        "        raise StopBeforeDjango('owned logging boundary')\n"
        "    if event=='import' and args[0]=='scitex_sdk':\n"
        "        raise ModuleNotFoundError('owned missing SDK control', name='scitex_sdk')\n"
        "    if event=='subprocess.Popen':\n"
        "        raise AssertionError('launcher must not spawn during this control')\n"
        "sys.addaudithook(no_django)\n"
        "assert 'django' not in sys.modules\n"
        "assert 'scitex_sdk' not in sys.modules\n"
        "try:\n"
        "    server.run('.',host='0.0.0.0',open_browser=False)\n"
        "except StopBeforeDjango:\n"
        "    pass\n"
        "else:\n"
        "    raise AssertionError('did not stop before Django import')"
    )
    # Act
    result = _run(tmp_path, code, level)
    # Assert
    assert all(
        (
            all(
                (
                    result.stdout.count("SciTeX Writer GUI: http://0.0.0.0:") == 1,
                    "Press Ctrl+C to stop" in result.stdout,
                    "SCITEX_WRITER_ALLOWED_HOSTS=" not in result.stdout,
                    "workspace shell is unavailable" not in result.stdout,
                    result.stderr.count("SCITEX_WRITER_ALLOWED_HOSTS=") == 1,
                    result.stderr.count("workspace shell is unavailable") == 1,
                    "uv pip install 'scitex-writer[all]'" in result.stderr,
                )
            )
            if level == "info"
            else all((result.stdout == result.stderr == "",)),
        )
    ), result.stderr
