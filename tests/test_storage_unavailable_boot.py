"""Regression coverage for browsers where Web Storage is unavailable.

Some embedded/privacy-hardened browser contexts expose ``window.localStorage`` or
``window.sessionStorage`` as throwing accessors. Hermes WebUI uses storage during
classic-script boot, so the first inline script must install safe bindings before
later scripts read/write preferences.
"""
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = (REPO_ROOT / "static" / "index.html").read_text(encoding="utf-8")
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node not on PATH")


def _inline_scripts():
    return re.findall(r"<script>(.*?)</script>", INDEX_HTML, flags=re.DOTALL)


def _first_storage_script():
    scripts = _inline_scripts()
    assert scripts, "index.html must have inline boot scripts"
    for script in scripts:
        if "localStorage" in script or "sessionStorage" in script:
            return script
    raise AssertionError("index.html must bootstrap Web Storage before static scripts")


def test_first_storage_script_installs_safe_storage_bindings_when_native_storage_throws():
    first_storage_script = _first_storage_script()
    driver = textwrap.dedent(
        f"""
        const vm = require('vm');
        const sandbox = {{
          window: {{}},
          document: {{
            documentElement: {{ dataset: {{}}, classList: {{ add() {{}}, remove() {{}} }} }},
            querySelectorAll() {{ return []; }},
          }},
        }};
        for (const target of [sandbox, sandbox.window]) {{
          Object.defineProperty(target, 'localStorage', {{
            configurable: true,
            get() {{ throw new Error('blocked localStorage'); }},
          }});
          Object.defineProperty(target, 'sessionStorage', {{
            configurable: true,
            get() {{ throw new Error('blocked sessionStorage'); }},
          }});
        }}
        sandbox.window.matchMedia = () => ({{matches:false}});
        vm.createContext(sandbox);
        vm.runInContext({first_storage_script!r}, sandbox, {{filename: 'index.html:first-storage-inline'}});
        vm.runInContext(`
          localStorage.setItem('theme', 'dark');
          sessionStorage.setItem('checked', '1');
          if (localStorage.getItem('theme') !== 'dark') throw new Error('fallback localStorage did not round-trip');
          if (sessionStorage.getItem('checked') !== '1') throw new Error('fallback sessionStorage did not round-trip');
          localStorage.removeItem('theme');
          sessionStorage.removeItem('checked');
          if (localStorage.getItem('theme') !== null) throw new Error('fallback localStorage remove failed');
          if (sessionStorage.getItem('checked') !== null) throw new Error('fallback sessionStorage remove failed');
        `, sandbox, {{filename: 'storage-probe.js'}});
        """
    )
    assert NODE is not None
    result = subprocess.run([NODE, "-e", driver], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_safe_storage_falls_back_when_native_storage_methods_throw():
    first_storage_script = _first_storage_script()
    driver = textwrap.dedent(
        f"""
        const vm = require('vm');
        function throwingStorage() {{
          return {{
            get length() {{ return 0; }},
            key() {{ return null; }},
            getItem() {{ return null; }},
            setItem() {{ throw new Error('native setItem blocked'); }},
            removeItem() {{ throw new Error('native removeItem blocked'); }},
            clear() {{ throw new Error('native clear blocked'); }},
          }};
        }}
        const sandbox = {{
          window: {{ localStorage: throwingStorage(), sessionStorage: throwingStorage() }},
          document: {{
            documentElement: {{ dataset: {{}}, classList: {{ add() {{}}, remove() {{}} }} }},
            querySelectorAll() {{ return []; }},
          }},
        }};
        sandbox.window.matchMedia = () => ({{matches:false}});
        vm.createContext(sandbox);
        vm.runInContext({first_storage_script!r}, sandbox, {{filename: 'index.html:first-storage-inline'}});
        vm.runInContext(`
          localStorage.setItem('theme', 'dark');
          sessionStorage.setItem('checked', '1');
          if (localStorage.getItem('theme') !== 'dark') throw new Error('fallback did not take over after native setItem threw');
          if (sessionStorage.getItem('checked') !== '1') throw new Error('session fallback did not take over after native setItem threw');
          localStorage.removeItem('theme');
          if (localStorage.getItem('theme') !== null) throw new Error('fallback remove failed after native removeItem threw');
          localStorage.setItem('__proto__', 'safe');
          if (localStorage.getItem('__proto__') !== 'safe') throw new Error('fallback must preserve Storage string keys');
          localStorage.clear();
          if (localStorage.getItem('__proto__') !== null) throw new Error('fallback clear failed after native clear threw');
          localStorage.setItem('', 'empty');
          if (localStorage.getItem('') !== 'empty') throw new Error('fallback must preserve empty string keys');
          if (localStorage.key(0) !== '') throw new Error('fallback key(0) must return empty string keys');
          if (localStorage.length !== 1) throw new Error('fallback length must count empty string keys');
        `, sandbox, {{filename: 'storage-method-throw-probe.js'}});
        """
    )
    assert NODE is not None
    result = subprocess.run([NODE, "-e", driver], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_safe_storage_bootstrap_precedes_other_inline_localstorage_reads():
    first_storage_script = _first_storage_script()
    assert "function _createHermesSafeStorage" in first_storage_script
    assert "let localStorage" in first_storage_script
    assert "let sessionStorage" in first_storage_script
    assert INDEX_HTML.find("function _createHermesSafeStorage") < INDEX_HTML.find("localStorage.getItem('hermes-theme')")
