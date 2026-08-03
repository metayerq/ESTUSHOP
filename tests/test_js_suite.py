"""
Fait tourner les tests JavaScript depuis pytest, pour qu'UNE commande couvre tout.

Sans ça, `pytest` finirait vert en ignorant silencieusement le tri des écarts — un vert partiel
qui se lit comme un vert complet. Si node est absent, le test est SKIPPÉ et non passé : la
différence entre « vérifié » et « pas vérifié ici » doit rester lisible.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

JS_TESTS = sorted((Path(__file__).parent).glob("test_*.js"))


@pytest.mark.parametrize("script", JS_TESTS, ids=lambda p: p.name)
def test_suite_javascript(script):
    node = shutil.which("node")
    if not node:
        pytest.skip("node absent — le tri des écarts n'est PAS vérifié dans cette exécution")
    r = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"\n{r.stdout}\n{r.stderr}"
