"""Migration history checks; real SQL and rollback are covered by test_postgres."""
import unittest
from unittest.mock import Mock
import schema_migrations as schema


class MigrationHistoryTests(unittest.TestCase):
    def setUp(self):
        self.db = Mock()
        self.db.execute.return_value = []
        self.baseline = schema.MIGRATIONS[0]

    def applied(self, **changes):
        return {"version": 1, "name": self.baseline.name, "checksum": self.baseline.checksum,
                "applied_at": "fixed", **changes}

    def run_history(self, history):
        from unittest.mock import patch
        with patch.object(schema, "schema_status", return_value=history):
            return schema.migrate(self.db)

    def test_matching_history_does_not_reexecute_migration(self):
        self.assertEqual(self.run_history([{"version": m.version, "name": m.name, "checksum": m.checksum} for m in schema.MIGRATIONS]), schema.LATEST_VERSION)
        self.assertFalse(any(call.args[0] in [m.sql for m in schema.MIGRATIONS] for call in self.db.execute.call_args_list))

    def test_baseline_history_runs_only_pending_migrations(self):
        self.assertEqual(self.run_history([self.applied()]), schema.LATEST_VERSION)
        executed = [call.args[0] for call in self.db.execute.call_args_list]
        self.assertNotIn(self.baseline.sql, executed)
        for pending in schema.MIGRATIONS[1:]:
            self.assertEqual(executed.count(pending.sql), 1)

    def test_edited_migration_is_rejected(self):
        with self.assertRaises(schema.MigrationError):
            self.run_history([self.applied(checksum="changed")])

    def test_renamed_migration_is_rejected(self):
        with self.assertRaises(schema.MigrationError):
            self.run_history([self.applied(name="changed")])

    def test_newer_database_is_rejected(self):
        with self.assertRaises(schema.MigrationError):
            self.run_history([self.applied(), self.applied(version=schema.LATEST_VERSION + 1)])

    def test_missing_history_version_is_rejected(self):
        with self.assertRaises(schema.MigrationError):
            self.run_history([self.applied(version=schema.LATEST_VERSION + 1)])

    def test_nonconsecutive_plan_is_rejected(self):
        with self.assertRaises(schema.MigrationError):
            schema.migrate(self.db, (schema.Migration(2, "invalid", "SELECT 1"),))
        self.db.execute.assert_not_called()

    def test_empty_migration_is_rejected(self):
        with self.assertRaises(schema.MigrationError):
            schema.migrate(self.db, (schema.Migration(1, "invalid", " "),))

    def test_autocommit_connection_cannot_run_partial_migrations(self):
        self.db.autocommit = True
        with self.assertRaises(schema.MigrationError):
            schema.migrate(self.db)
        self.db.execute.assert_not_called()

    def test_incompatible_legacy_columns_are_rejected(self):
        with self.assertRaises(schema.MigrationError):
            schema.validate_baseline(self.db)


if __name__ == "__main__":
    unittest.main()
