import unittest
from nexus.verifiers.domain.django.django_migration_guard import DjangoMigrationGuard

class TestDjangoMigrationGuard(unittest.TestCase):
    
    def test_irreversible_sql_is_blocked(self):
        """驗證：沒有 reverse_sql 的 RunSQL 會被擋下"""
        patch = '''
        operations = [
            migrations.RunSQL("DROP TABLE important_data;")
        ]
        '''
        verdict = DjangoMigrationGuard.evaluate("t1", patch)
        self.assertFalse(verdict.passed)
        self.assertEqual(verdict.failure_tags[0].code, "IRREVERSIBLE_MIGRATION")

    def test_reversible_sql_is_allowed(self):
        """驗證：安全的雙向 RunSQL 允許通過"""
        patch = '''
        operations = [
            migrations.RunSQL(
                "CREATE INDEX idx_name ON table (name);",
                reverse_sql="DROP INDEX idx_name;"
            )
        ]
        '''
        verdict = DjangoMigrationGuard.evaluate("t2", patch)
        self.assertTrue(verdict.passed)

    def test_first_dependency_requires_initial_flag(self):
        """驗證：只有 initial=True 才能相依於 '__first__'"""
        patch = '''
        dependencies = [
            ('app', '__first__'),
        ]
        '''
        verdict = DjangoMigrationGuard.evaluate("t3", patch)
        self.assertFalse(verdict.passed)
        self.assertEqual(verdict.failure_tags[0].code, "DEPENDENCY_RISK")

    def test_cross_app_dependency_requires_node(self):
        """驗證：跨 App 相依性必須明確宣告 node"""
        patch = '''
        operations = [
            migrations.swappable_dependency(settings.AUTH_USER_MODEL)
        ]
        '''
        verdict = DjangoMigrationGuard.evaluate("t4", patch)
        self.assertFalse(verdict.passed)
        self.assertEqual(verdict.failure_tags[0].code, "CROSS_APP_ORPHAN")

    def test_null_patch_does_not_crash(self):
        """驗證：傳入空的 patch 不會拋出 Exception，而是能安全回傳 verdict"""
        verdict = DjangoMigrationGuard.evaluate("t_null", None)
        self.assertFalse(verdict.passed)
        self.assertEqual(verdict.failure_tags[0].code, "INVALID_PATCH")

if __name__ == "__main__":
    unittest.main()
