from apexquant_migrations.clickhouse import split_sql


def test_split_sql_removes_comments_and_empty_statements() -> None:
    sql = """
-- comment
CREATE DATABASE IF NOT EXISTS test;

CREATE TABLE IF NOT EXISTS test.table (x UInt32) ENGINE = MergeTree ORDER BY x;

-- another comment
"""

    statements = split_sql(sql)

    assert len(statements) == 2
    assert statements[0] == "CREATE DATABASE IF NOT EXISTS test"
    assert statements[1].startswith("CREATE TABLE IF NOT EXISTS test.table")