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
    result = _run(
        tmp_path,
        "from scitex_writer._cli.introspect import cmd_api\n"
        "assert cmd_api('math',max_depth=0,as_json=True)==0",
        level,
    )
    assert json.loads(result.stdout) == [{"Name": "math", "Type": "M", "Depth": 0}]
    assert result.stderr == ""


@pytest.mark.parametrize("level", ["info", "critical"])
def test_actual_mcp_inventory_json_keeps_envelope_at_default_print_capture_setting(
    tmp_path, level
):
    result = _run(
        tmp_path,
        "from scitex_writer._cli.mcp import cmd_list_tools\n"
        "assert cmd_list_tools(as_json=True)==0",
        level,
    )
    output = json.loads(result.stdout)
    assert output["name"] == "scitex-writer"
    assert output["result_envelope"]["type"] == "object"
    modules = output["modules"]
    assert output["total"] == sum(item["count"] for item in modules.values())
    assert all(item["count"] == len(item["tools"]) for item in modules.values())
    assert "writer_compile_manuscript" in modules["compile"]["tools"]
    assert result.stderr == ""


@pytest.mark.parametrize("level", ["info", "critical"])
def test_banner_honors_late_level_changes_and_remains_single_stream(tmp_path, level):
    result = _run(
        tmp_path,
        "logging.configure(level='critical',enable_file=False,capture_prints=True)\n"
        "server._print_startup(Path('synthetic'), '127.0.0.1',31291,['127.0.0.1'])\n"
        f"logging.configure(level={level!r},enable_file=False,capture_prints=True)\n"
        "server._print_startup(Path('synthetic'), '127.0.0.1',31291,['127.0.0.1'])\n"
        "server._print_startup(Path('synthetic'), '127.0.0.1',31291,['127.0.0.1'])",
        level,
        "from scitex_writer._django import _server as server",
    )
    assert result.stderr == ""
    if level == "info":
        assert result.stdout.count("SciTeX Writer GUI: http://127.0.0.1:31291") == 2
        assert result.stdout.count("Project: synthetic") == 2
        assert result.stdout.count("Press Ctrl+C to stop") == 2
    else:
        assert result.stdout == ""


@pytest.mark.parametrize("level", ["warning", "critical"])
def test_wildcard_warning_is_thresholded_stderr_with_remedy(tmp_path, level):
    result = _run(
        tmp_path,
        "from scitex_writer._django import _server as server\n"
        "server._print_startup(Path('synthetic'),'0.0.0.0',31291,['0.0.0.0'])",
        level,
    )
    assert result.stdout == ""
    if level == "warning":
        assert result.stderr.count("SCITEX_WRITER_ALLOWED_HOSTS=") == 1
        assert "400" in result.stderr
    else:
        assert result.stderr == ""


@pytest.mark.parametrize("level", ["warning", "critical"])
def test_degraded_shell_notice_is_visible_diagnostic_with_install_remedy(
    tmp_path, level
):
    result = _run(
        tmp_path,
        "from scitex_writer._django import _server as server\n"
        "server._warn_missing_shell('synthetic missing dependency','pip install synthetic')",
        level,
    )
    assert result.stdout == ""
    if level == "warning":
        assert "synthetic missing dependency" in result.stderr
        assert "serving bare Django instead" in result.stderr
        assert "pip install synthetic" in result.stderr
    else:
        assert result.stderr == ""


@pytest.mark.parametrize("level", ["info", "critical"])
def test_real_launcher_announces_only_until_django_import_without_starting_server(
    tmp_path, level
):
    result = _run(
        tmp_path,
        "from scitex_writer._django import _server as server\n"
        "class StopBeforeDjango(RuntimeError): pass\n"
        "def no_django(event,args):\n"
        "    if event=='import' and args[0]=='django':\n"
        "        raise StopBeforeDjango('owned logging boundary')\n"
        "    if event=='subprocess.Popen':\n"
        "        raise AssertionError('launcher must not spawn during this control')\n"
        "sys.addaudithook(no_django)\n"
        "assert 'django' not in sys.modules\n"
        "try:\n"
        "    server.run('.',host='0.0.0.0',open_browser=False)\n"
        "except StopBeforeDjango:\n"
        "    pass\n"
        "else:\n"
        "    raise AssertionError('did not stop before Django import')",
        level,
    )
    if level == "info":
        assert result.stdout.count("SciTeX Writer GUI: http://0.0.0.0:") == 1
        assert "Press Ctrl+C to stop" in result.stdout
        assert "SCITEX_WRITER_ALLOWED_HOSTS=" not in result.stdout
        assert "workspace shell is unavailable" not in result.stdout
        assert result.stderr.count("SCITEX_WRITER_ALLOWED_HOSTS=") == 1
        assert result.stderr.count("workspace shell is unavailable") == 1
        assert "uv pip install 'scitex-writer[all]'" in result.stderr
    else:
        assert result.stdout == result.stderr == ""
