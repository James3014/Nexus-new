import unittest
from nexus.verifiers.domain.django.django_core_logic_guard import DjangoCoreLogicGuard

class TestDjangoCoreExtended(unittest.TestCase):
    """
    [v27.3 T1] 延伸 Django_Core_Logic 的測試邊界
    補足 Transaction, Model State, 以及 Async Request 的殘留題驗證
    """
    def test_transaction_atomic_missing(self):
        """驗證：涉及多表操作時，若未包裝在 transaction.atomic() 下應被警告"""
        patch = '''
        def update_user_profile(user, data):
            user.email = data['email']
            user.save()
            Profile.objects.create(user=user, bio=data['bio'])
        '''
        verdict = DjangoCoreLogicGuard.evaluate("ext1", patch)
        self.assertFalse(verdict.passed, "Should fail because transaction.atomic is missing")
        self.assertEqual(verdict.failure_tags[0].code, "MISSING_TRANSACTION")

    def test_sync_to_async_unsafe(self):
        """驗證：在 async def view 內部直接調用同步 ORM 應被阻斷"""
        patch = '''
        async def my_view(request):
            # Dangerous sync call inside async context
            user = User.objects.get(id=1) 
            return HttpResponse(user.name)
        '''
        verdict = DjangoCoreLogicGuard.evaluate("ext2", patch)
        self.assertFalse(verdict.passed)
        self.assertEqual(verdict.failure_tags[0].code, "SYNC_IN_ASYNC_CONTEXT")

if __name__ == "__main__":
    unittest.main()
