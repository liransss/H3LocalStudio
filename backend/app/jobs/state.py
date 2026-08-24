from __future__ import annotations

from app.models.schemas import JobState


ALLOWED_TRANSITIONS: dict[JobState, set[JobState]] = {
    JobState.QUEUED: {JobState.PREPARING, JobState.CANCELLED, JobState.FAILED},
    JobState.PREPARING: {JobState.RUNNING, JobState.UPSCALING, JobState.CANCELLED, JobState.FAILED, JobState.UPSCALE_FAILED},
    JobState.RUNNING: {JobState.POST_PROCESSING, JobState.COMPLETED, JobState.CANCELLED, JobState.FAILED},
    JobState.UPSCALING: {JobState.POST_PROCESSING, JobState.COMPLETED, JobState.CANCELLED, JobState.UPSCALE_FAILED},
    JobState.POST_PROCESSING: {
        JobState.COMPLETED,
        JobState.CANCELLED,
        JobState.FAILED,
        JobState.UPSCALE_FAILED,
    },
    JobState.COMPLETED: set(),
    JobState.FAILED: set(),
    JobState.UPSCALE_FAILED: set(),
    JobState.CANCELLED: set(),
}


def assert_transition(current: str, target: str) -> None:
    current_state = JobState(current)
    target_state = JobState(target)
    if target_state not in ALLOWED_TRANSITIONS[current_state]:
        raise ValueError(f"Invalid job state transition: {current_state} -> {target_state}")
