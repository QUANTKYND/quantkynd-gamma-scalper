import pytest

from app.instruments.ports import UnitOfWorkStateError
from app.persistence.postgres.unit_of_work import PostgresUnitOfWork


class FakeSession:
    def __init__(self, fail_commit: bool = False) -> None:
        self.fail_commit = fail_commit
        self.commit_count = 0
        self.rollback_count = 0
        self.close_count = 0
        self.executed_statements: list[str] = []

    async def execute(self, statement):
        self.executed_statements.append(str(statement))

    async def commit(self) -> None:
        self.commit_count += 1
        if self.fail_commit:
            raise RuntimeError("commit failed")

    async def rollback(self) -> None:
        self.rollback_count += 1

    async def close(self) -> None:
        self.close_count += 1


@pytest.mark.anyio
async def test_default_unit_of_work_uses_repeatable_read() -> None:
    session = FakeSession()
    unit_of_work = PostgresUnitOfWork(lambda: session)

    async with unit_of_work:
        assert session.executed_statements == [
            "SET TRANSACTION ISOLATION LEVEL "
            "REPEATABLE READ"
        ]


@pytest.mark.anyio
async def test_read_only_unit_of_work_uses_repeatable_read_read_only() -> None:
    session = FakeSession()
    unit_of_work = PostgresUnitOfWork(
        lambda: session,
        read_only_repeatable_read=True,
    )

    async with unit_of_work:
        assert session.executed_statements == [
            "SET TRANSACTION ISOLATION LEVEL "
            "REPEATABLE READ READ ONLY"
        ]


@pytest.mark.anyio
async def test_commit_finalizes_repository_and_transaction_access() -> None:
    session = FakeSession()
    unit_of_work = PostgresUnitOfWork(lambda: session)
    async with unit_of_work:
        repository = unit_of_work.catalogues
        await unit_of_work.commit()
        with pytest.raises(UnitOfWorkStateError):
            await repository.get("id")
        with pytest.raises(UnitOfWorkStateError):
            await unit_of_work.commit()
        with pytest.raises(UnitOfWorkStateError):
            await unit_of_work.rollback()
    assert session.commit_count == 1
    assert session.rollback_count == 0
    assert session.close_count == 1


@pytest.mark.anyio
async def test_rollback_finalizes_repository_and_transaction_access() -> None:
    session = FakeSession()
    unit_of_work = PostgresUnitOfWork(lambda: session)
    async with unit_of_work:
        repository = unit_of_work.catalogues
        await unit_of_work.rollback()
        with pytest.raises(UnitOfWorkStateError):
            await repository.get("id")
        with pytest.raises(UnitOfWorkStateError):
            await unit_of_work.commit()
        with pytest.raises(UnitOfWorkStateError):
            await unit_of_work.rollback()
    assert session.rollback_count == 1
    assert session.close_count == 1


@pytest.mark.anyio
async def test_commit_failure_rolls_back_finalizes_and_closes() -> None:
    session = FakeSession(fail_commit=True)
    unit_of_work = PostgresUnitOfWork(lambda: session)
    with pytest.raises(RuntimeError, match="commit failed"):
        async with unit_of_work:
            await unit_of_work.commit()
    assert session.rollback_count == 1
    assert session.close_count == 1
    with pytest.raises(UnitOfWorkStateError):
        await unit_of_work.commit()


@pytest.mark.anyio
async def test_context_exit_without_commit_rolls_back_once() -> None:
    session = FakeSession()
    unit_of_work = PostgresUnitOfWork(lambda: session)
    async with unit_of_work:
        assert unit_of_work.catalogues
    assert session.rollback_count == 1
    assert session.close_count == 1
