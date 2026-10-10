"""Run the eval suite as part of the normal test run (CI task 19)."""

import pytest

from evals.runner import run_task
from evals.tasks import TASKS


@pytest.mark.parametrize("task", TASKS, ids=[t.id for t in TASKS])
def test_eval_task(task, tmp_path):
    result = run_task(task, tmp_path)
    assert result.passed, result.message
