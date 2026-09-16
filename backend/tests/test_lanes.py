"""Lane membership, which decides what a worker process may take.

The check that matters is exhaustiveness: a job type added without a lane is
the bug this split exists to prevent, and it would show up as work nothing ever
runs rather than as an error.
"""

from app.enums import JobType, Lane, lane_of, types_for


def test_every_job_type_belongs_to_exactly_one_lane():
    fetch = set(types_for(Lane.FETCH))
    download = set(types_for(Lane.DOWNLOAD))

    assert fetch.isdisjoint(download)
    assert fetch | download == {str(job_type) for job_type in JobType}


def test_downloads_are_the_download_lane():
    assert lane_of(JobType.DOWNLOAD_BATCH) is Lane.DOWNLOAD
    assert lane_of(JobType.DOWNLOAD_CHAPTER) is Lane.DOWNLOAD


def test_the_jobs_a_user_waits_on_are_the_fetch_lane():
    for job_type in (JobType.MATCH_SEARCH, JobType.CHAPTER_DISCOVER, JobType.PROGRESS_PUSH):
        assert lane_of(job_type) is Lane.FETCH
