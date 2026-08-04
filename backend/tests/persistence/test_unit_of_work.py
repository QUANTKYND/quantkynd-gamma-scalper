import pytest

from app.instruments.ports import UnitOfWorkStateError
from app.persistence.postgres.unit_of_work import PostgresUnitOfWork


class FailingSession:
    def __init__(self) -> None:
        self.rollback_count = 0
        self.close_count = 0

    async def commit(self) -> None:
        raise RuntimeError("commit failed")

    async def rollback(self) -> None:
        self.rollback_count += 1

    async def close(self) -> None:
        self.close_count += 1


@pytest.mark.anyio
async def test_commit_failure_rolls_back_and_closes() -> None:
    session = FailingSession()
    unit_of_work = PostgresUnitOfWork(lambda: session)
    with pytest.raises(RuntimeError, match="commit failed"):
        async with unit_of_work:
            await unit_of_work.commit()
    assert session.rollback_count == 2
    assert session.close_count == 1
    with pytest.raises(UnitOfWorkStateError):
        await unit_of_work.commit()
