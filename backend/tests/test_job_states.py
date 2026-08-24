import pytest

from app.jobs.state import assert_transition


def test_valid_job_state_transition():
    assert_transition("queued", "preparing")
    assert_transition("running", "post-processing")
    assert_transition("post-processing", "completed")


def test_terminal_job_cannot_restart():
    with pytest.raises(ValueError):
        assert_transition("completed", "running")

