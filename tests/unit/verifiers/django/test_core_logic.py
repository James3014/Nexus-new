import unittest
from nexus.verifiers.domain.django.django_core_logic_guard import DjangoCoreLogicGuard

class TestDjangoCoreLogicGuard(unittest.TestCase):
    
    def test_sql_injection_is_blocked(self):
        """驗證：沒有使用 params 的 RawSQL 會被擋下"""
        patch = '''
        def get_user(request):
            user_id = request.GET.get('id')
            return User.objects.raw(f"SELECT * FROM auth_user WHERE id = {user_id}")
        '''
        verdict = DjangoCoreLogicGuard.evaluate("t1", patch)
        self.assertFalse(verdict.passed)
        self.assertEqual(verdict.failure_tags[0].code, "SQL_INJECTION_RISK")

    def test_safe_raw_sql_is_allowed(self):
        """驗證：安全的 Parameterized RawSQL 允許通過"""
        patch = '''
        def get_user(request):
            user_id = request.GET.get('id')
            return User.objects.raw("SELECT * FROM auth_user WHERE id = %s", params=[user_id])
        '''
        verdict = DjangoCoreLogicGuard.evaluate("t2", patch)
        self.assertTrue(verdict.passed)

    def test_middleware_must_return_response(self):
        """驗證：Middleware 如果忘記 return response，會被擋下"""
        patch = '''
        class CustomMiddleware:
            def process_request(self, request):
                request.custom_attr = True
                # Missing return statement!
        '''
        verdict = DjangoCoreLogicGuard.evaluate("t3", patch)
        self.assertFalse(verdict.passed)
        self.assertEqual(verdict.failure_tags[0].code, "MIDDLEWARE_BROKEN_CHAIN")

    def test_view_global_mutation_is_blocked(self):
        """驗證：View 中不應該修改 Global State"""
        patch = '''
        request_count = 0
        
        class MyView(View):
            def get(self, request):
                global request_count
                request_count += 1
                return HttpResponse("OK")
        '''
        verdict = DjangoCoreLogicGuard.evaluate("t4", patch)
        self.assertFalse(verdict.passed)
        self.assertEqual(verdict.failure_tags[0].code, "VIEW_GLOBAL_MUTATION")

if __name__ == "__main__":
    unittest.main()
