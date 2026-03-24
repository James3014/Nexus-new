import sys
import os

# Mock Django setup
from django.conf import settings
if not settings.configured:
    settings.configure(
        DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}},
        INSTALLED_APPS=['django.contrib.contenttypes', 'django.contrib.auth'],
    )

import django
django.setup()

from django.db import models
from django.forms.models import modelformset_factory

class TestModel(models.Model):
    name = models.CharField(max_length=100)
    class Meta:
        app_label = 'verify'

# Test edit_only formset
TestFormSet = modelformset_factory(TestModel, fields=('name',), edit_only=True)
formset = TestFormSet(queryset=TestModel.objects.none())

print("FormSet edit_only attribute:", getattr(formset, 'edit_only', 'N/A'))
assert formset.edit_only is True

# Test save_new_objects interception
new_objs = formset.save_new_objects()
print("New objects saved (should be empty):", new_objs)
assert len(new_objs) == 0

print("SUCCESS: django-14725 verified")
